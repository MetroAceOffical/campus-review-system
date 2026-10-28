"""Configurable six-model experiments; frozen historical experiments stay read-only."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time

from .preparation import prepared, sha, write_json

ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ('lr', 'svm', 'rf', 'cnn', 'bilstm', 'bert')
DEFAULTS = {'seed': 20261028, 'C': 1., 'max_iter': 1000, 'class_weight': 'none', 'n_estimators': 100,
            'max_depth': 20, 'min_samples_leaf': 1, 'epochs': 3, 'batch_size': 32, 'learning_rate': .001,
            'width': 64, 'dropout': .2, 'max_length': 128, 'patience': 2, 'weight_decay': .01,
            'gradient_accumulation': 1, 'device': 'cpu'}


def parameters(family, values):
    if family not in FAMILIES or not isinstance(values, dict) or set(values) - DEFAULTS.keys():
        raise ValueError('模型或参数名称无效')
    cfg = DEFAULTS | values
    bounds = {'seed': (0, 2147483647), 'C': (.0001, 10000), 'max_iter': (10, 20000),
              'n_estimators': (10, 1000), 'max_depth': (1, 100), 'min_samples_leaf': (1, 100),
              'epochs': (1, 30), 'batch_size': (1, 256), 'learning_rate': (.0000001, .1),
              'width': (16, 256), 'dropout': (0, .8), 'max_length': (8, 512), 'patience': (0, 30),
              'weight_decay': (0, 1), 'gradient_accumulation': (1, 32)}
    floats = {'C', 'learning_rate', 'dropout', 'weight_decay'}
    for key, (low, high) in bounds.items():
        value = cfg[key]
        if type(value) not in ((int, float) if key in floats else (int,)) or not low <= value <= high or not math.isfinite(value):
            raise ValueError(f'{key}须在{low}—{high}范围内')
    if cfg['class_weight'] not in ('none', 'balanced') or cfg['device'] not in ('cpu', 'cuda'):
        raise ValueError('类别权重或设备无效')
    if family == 'bert' and cfg['device'] == 'cuda' and cfg['batch_size'] * cfg['max_length'] > 8192:
        raise ValueError('BERT批量×输入长度过大，请降低批量或使用梯度累积')
    return cfg


def legacy():
    # Reuse pure architecture/feature helpers, never invoke the frozen protocol
    # stages or write under validation/. Record their SHA in every model.
    folder = str(ROOT / 'validation/text')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import round2
    return round2


@contextmanager
def compute_slot(runtime, gpu=False):
    import psutil
    folder = Path(runtime) / 'workbench'
    folder.mkdir(parents=True, exist_ok=True)
    stream = (folder / 'compute.lock').open('a+b')
    if stream.tell() == 0:
        stream.write(b'0'); stream.flush()
    stream.seek(0)
    if os.name == 'nt':
        import msvcrt
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            stream.close()
            raise BlockingIOError('其他模型任务正在计算')
    else:
        import fcntl
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise BlockingIOError('其他模型任务正在计算')
    try:
        if gpu:
            # Legacy GPU jobs predate this queue: cooperate with their known
            # entry points rather than terminating any processes.
            names = ('construct_correspondence.py', 'run_campus_stage.py', 'train_text_models.py', 'train_retrieval.py', 'train_correspondence.py')
            for process in psutil.process_iter(['pid', 'cmdline']):
                try:
                    args = process.info['cmdline'] or []
                    if process.pid != os.getpid() and any(Path(arg).name in names for arg in args):
                        raise BlockingIOError('既有GPU任务运行中')
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            import socket
            with socket.socket() as connection:
                connection.settimeout(.3)
                if connection.connect_ex(('127.0.0.1', 18081)) == 0:
                    raise BlockingIOError('在线检测正在占用模型资源')
        yield
    finally:
        stream.close()


def metric_report(rows, scores, family):
    import numpy as np
    from sklearn.metrics import (accuracy_score, precision_recall_fscore_support, f1_score,
                                 confusion_matrix, roc_auc_score, roc_curve, precision_recall_curve,
                                 average_precision_score)
    y = [int(row['label']) for row in rows]
    scores = np.asarray(scores, dtype=float)
    if len(scores) != len(y) or not len(y) or not np.isfinite(scores).all():
        raise ValueError('预测数量或得分无效')
    threshold = 0. if family == 'svm' else .5
    pred = (scores >= threshold).astype(int)
    p, r, f, _ = precision_recall_fscore_support(y, pred, average='binary', zero_division=0)
    result = {'rows': len(y), 'accuracy': float(accuracy_score(y, pred)), 'precision': float(p), 'recall': float(r),
              'f1': float(f), 'macro_f1': float(f1_score(y, pred, labels=[0, 1], average='macro', zero_division=0)),
              'confusionMatrix': confusion_matrix(y, pred, labels=[0, 1]).tolist(), 'threshold': threshold,
              'scoreType': 'margin' if family == 'svm' else 'probability', 'roc_auc': None, 'average_precision': None, 'roc': [], 'pr': []}
    if len(set(y)) == 2:
        fpr, tpr, _ = roc_curve(y, scores)
        pp, rr, _ = precision_recall_curve(y, scores)
        # Bounded plot data; full per-row predictions remain available.
        def sample(x, z):
            ids = np.unique(np.linspace(0, len(x) - 1, min(500, len(x)), dtype=int))
            return [[float(x[i]), float(z[i])] for i in ids]
        result.update(roc_auc=float(roc_auc_score(y, scores)), average_precision=float(average_precision_score(y, scores)), roc=sample(fpr, tpr), pr=sample(rr, pp))
    return result, pred.tolist()


def dependencies():
    return {str(path.relative_to(ROOT)): sha(path) for path in (ROOT / 'validation/text/round2.py', ROOT / 'validation/text/run_validation.py', Path(__file__), Path(__file__).with_name('preparation.py'))}


def train(folder, output, family, values, emit):
    cfg = parameters(family, values)
    manifest, splits = prepared(folder)
    train_rows, dev = splits['train'], splits['validation']
    import numpy as np
    import torch
    import psutil
    random.seed(cfg['seed']); np.random.seed(cfg['seed']); torch.manual_seed(cfg['seed']); torch.set_num_threads(4)
    if cfg['device'] == 'cuda' and family in ('cnn', 'bilstm', 'bert') and not torch.cuda.is_available():
        raise ValueError('CUDA不可用，请选择CPU或检查现有训练环境')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    history = []
    old = legacy()
    emit({'stage': 'FEATURES', 'processed': 0, 'total': len(train_rows), 'family': family})
    if family in ('lr', 'svm', 'rf'):
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import StandardScaler
        vec = TfidfVectorizer(analyzer='char', ngram_range=(1, 2), max_features=20000, dtype=np.float32)
        vec.fit([row[key] for row in train_rows for key in ('sentence1', 'sentence2')])
        scaler = StandardScaler()
        x = scaler.fit_transform(old.feature_matrix(train_rows, vec))
        xd = scaler.transform(old.feature_matrix(dev, vec))
        common = {'random_state': cfg['seed'], 'class_weight': None if cfg['class_weight'] == 'none' else 'balanced'}
        if family == 'lr':
            from sklearn.linear_model import LogisticRegression
            model = LogisticRegression(C=cfg['C'], max_iter=cfg['max_iter'], **common)
        elif family == 'svm':
            from sklearn.svm import LinearSVC
            model = LinearSVC(C=cfg['C'], max_iter=cfg['max_iter'], dual='auto', **common)
        else:
            from sklearn.ensemble import RandomForestClassifier
            model = RandomForestClassifier(n_estimators=cfg['n_estimators'], max_depth=cfg['max_depth'], min_samples_leaf=cfg['min_samples_leaf'], n_jobs=2, warm_start=True, **common)
        y = [int(row['label']) for row in train_rows]
        emit({'stage': 'TRAINING', 'processed': 0, 'total': len(y), 'family': family})
        if family == 'rf':
            for trees in range(10, cfg['n_estimators'] + 10, 10):
                model.n_estimators = min(trees, cfg['n_estimators'])
                model.fit(x, y)
                scores = model.predict_proba(xd)[:, 1]
                met, _ = metric_report(dev, scores, family)
                item = {'trees': model.n_estimators, 'validation': {k: v for k, v in met.items() if k not in ('roc', 'pr')}}
                history.append(item); emit({'stage': 'TRAINING', 'processed': model.n_estimators, 'total': cfg['n_estimators'], **item})
        else:
            model.fit(x, y)
        scores = old.classic_scores(model, xd, family)
        iterations = int(np.max(model.n_iter_)) if hasattr(model, 'n_iter_') else None
        converged = iterations < cfg['max_iter'] if iterations is not None else True
        joblib.dump({'model': model, 'vectorizer': vec, 'scaler': scaler}, output / 'model.joblib')
        loaded = joblib.load(output / 'model.joblib')
        again = old.classic_scores(loaded['model'], loaded['scaler'].transform(old.feature_matrix(dev, loaded['vectorizer'])), family)
        difference = float(np.max(np.abs(scores - again)))
        best_epoch = None
    else:
        scores, history, best_epoch, difference = neural_train(old, train_rows, dev, output, family, cfg, emit)
        iterations = None; converged = True
    met, _ = metric_report(dev, scores, family)
    emit({'stage': 'VALIDATED', 'processed': len(dev), 'total': len(dev), 'validation': met})
    if difference > 1e-5:
        raise ValueError('模型保存重载校验失败')
    write_json(output / 'history.json', history)
    write_json(output / 'train-identities.json', {'sentences': sorted({hashlib.sha256(row[key].encode()).hexdigest() for row in train_rows for key in ('sentence1', 'sentence2')}), 'groups': sorted({row['_partitionGroup'] for row in train_rows})})
    result = {'schemaVersion': 1, 'taskType': 'TRAINING', 'status': 'COMPLETED', 'family': family, 'parameters': cfg,
              'preparationSha256': sha(Path(folder) / 'manifest.json'), 'inputSha256': manifest['inputSha256'],
              'trainRows': len(train_rows), 'validationRows': len(dev), 'validation': met, 'history': history,
              'bestEpoch': best_epoch, 'iterations': iterations, 'converged': converged, 'reloadMaxDifference': difference,
              'elapsedSeconds': time.monotonic() - started, 'rssBytes': psutil.Process().memory_info().rss,
              'dependencies': dependencies(), 'artifacts': {str(p.relative_to(output)).replace('\\', '/'): sha(p) for p in output.rglob('*') if p.is_file()}}
    write_json(output / 'manifest.json', result)
    emit({'stage': 'MODEL_SAVED', 'processed': len(train_rows), 'total': len(train_rows)})
    return result


def encode(rows, family, cfg, vocab=None, tokenizer=None):
    import torch
    if family == 'bert':
        return dict(tokenizer([r['sentence1'] for r in rows], [r['sentence2'] for r in rows], padding='max_length', truncation=True, max_length=cfg['max_length'], return_tensors='pt'))
    result = {}
    for key, target in (('sentence1', 'a'), ('sentence2', 'b')):
        out = torch.zeros((len(rows), cfg['max_length']), dtype=torch.long)
        lengths = []
        for i, row in enumerate(rows):
            tokens = [vocab.get(ch, 1) for ch in row[key][:cfg['max_length']]]
            out[i, :len(tokens)] = torch.tensor(tokens, dtype=torch.long)
            lengths.append(max(1, len(tokens)))
        result[target] = out
        result['l' + target] = torch.tensor(lengths)
    return result


def forward(model, family, data, index, device):
    batch = {key: value[index].to(device) for key, value in data.items()}
    if family == 'bert':
        return model(**batch).logits
    return model(batch['a'], batch['b'], batch['la'], batch['lb'])


def neural_scores(model, family, rows, cfg, vocab=None, tokenizer=None, emit=None):
    import torch
    data = encode(rows, family, cfg, vocab, tokenizer)
    model.eval(); scores = []
    with torch.no_grad():
        for i in range(0, len(rows), cfg['batch_size']):
            logits = forward(model, family, data, slice(i, i + cfg['batch_size']), cfg['device'])
            scores.extend(logits.float().softmax(-1)[:, 1].cpu().tolist())
            if emit:
                emit({'stage': 'PREDICTING', 'processed': min(i + cfg['batch_size'], len(rows)), 'total': len(rows)})
    return scores


def neural_train(old, rows, dev, output, family, cfg, emit):
    import numpy as np
    import torch
    from torch import nn
    vocab = old.make_vocab(rows) if family != 'bert' else None
    tokenizer = None
    if family == 'bert':
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        source = ROOT / 'validation/text/models/bert-base-chinese'
        source_manifest = json.loads((ROOT / 'validation/text/evidence/bert-source-manifest.json').read_text(encoding='utf-8'))
        if any(sha(source / item['file']) != item['sha256'] for item in source_manifest):
            raise ValueError('BERT基础权重校验失败')
        tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(source, num_labels=2, local_files_only=True)
        tokenizer.save_pretrained(output / 'bert')
    else:
        model = old.SentencePairNet(family, len(vocab) + 2, cfg['width'])
        model.head[2] = nn.Dropout(cfg['dropout'])
        write_json(output / 'vocab.json', vocab)
    model.to(cfg['device'])
    data = encode(rows, family, cfg, vocab, tokenizer)
    labels = torch.tensor([int(row['label']) for row in rows], device=cfg['device'])
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg['learning_rate'], weight_decay=cfg['weight_decay'])
    gen = torch.Generator().manual_seed(cfg['seed'])
    monitor = next(parameter for parameter in model.parameters() if parameter.requires_grad)
    before = monitor.detach().cpu().clone()
    best, best_epoch, stale = -1., 0, 0
    history = []
    for epoch in range(1, cfg['epochs'] + 1):
        model.train(); order = torch.randperm(len(rows), generator=gen); total_loss = 0.; seen = 0
        steps = math.ceil(len(rows) / cfg['batch_size']); optimizer.zero_grad(set_to_none=True)
        for step, begin in enumerate(range(0, len(rows), cfg['batch_size']), 1):
            index = order[begin:begin + cfg['batch_size']]
            logits = forward(model, family, data, index, cfg['device'])
            loss = nn.functional.cross_entropy(logits, labels[index.to(cfg['device'])])
            if not torch.isfinite(loss):
                raise ValueError('训练损失非有限值，请检查数据和学习率')
            window_start = ((step - 1) // cfg['gradient_accumulation']) * cfg['gradient_accumulation']
            window_size = min(cfg['gradient_accumulation'], steps - window_start)
            (loss / window_size).backward()
            if step % cfg['gradient_accumulation'] == 0 or step == steps:
                nn.utils.clip_grad_norm_(model.parameters(), 1.); optimizer.step(); optimizer.zero_grad(set_to_none=True)
            value = float(loss.item()); total_loss += value * len(index); seen += len(index)
            emit({'stage': 'TRAINING', 'epoch': epoch, 'epochs': cfg['epochs'], 'step': step, 'steps': steps, 'loss': value, 'learningRate': cfg['learning_rate'], 'processed': seen, 'total': len(rows)})
        scores = neural_scores(model, family, dev, cfg, vocab, tokenizer)
        met, _ = metric_report(dev, scores, family)
        item = {'epoch': epoch, 'loss': total_loss / seen, 'validation': {k: v for k, v in met.items() if k not in ('roc', 'pr')}}
        history.append(item); emit({'stage': 'EPOCH', **item})
        if met['macro_f1'] > best + .0001:
            best = met['macro_f1']; best_epoch = epoch; stale = 0
            torch.save(model.state_dict(), output / 'best.pt')
        else:
            stale += 1
        # A checkpoint is written before advertising resumable state. A later
        # UI may offer resume only against this exact data/config identity.
        torch.save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(), 'epoch': epoch,
                    'generator': gen.get_state(), 'torch_rng': torch.get_rng_state(), 'numpy_rng': np.random.get_state(),
                    'python_rng': random.getstate(), 'parameters': cfg, 'history': history}, output / 'last-checkpoint.pt')
        write_json(output / 'history.json', history)
        if cfg['patience'] and stale >= cfg['patience']:
            break
    if torch.equal(before, monitor.detach().cpu()):
        raise ValueError('模型参数没有更新')
    model.load_state_dict(torch.load(output / 'best.pt', map_location=cfg['device'], weights_only=True))
    reference = np.asarray(neural_scores(model, family, dev, cfg, vocab, tokenizer))
    if family == 'bert':
        model.save_pretrained(output / 'bert')
        from transformers import AutoModelForSequenceClassification
        again = AutoModelForSequenceClassification.from_pretrained(output / 'bert', local_files_only=True).to(cfg['device'])
    else:
        again = old.SentencePairNet(family, len(vocab) + 2, cfg['width']).to(cfg['device'])
        again.load_state_dict(torch.load(output / 'best.pt', map_location=cfg['device'], weights_only=True))
    actual = np.asarray(neural_scores(again, family, dev, cfg, vocab, tokenizer))
    return reference, history, best_epoch, float(np.max(np.abs(reference - actual)))


def load_model(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('taskType') != 'TRAINING' or manifest.get('status') != 'COMPLETED':
        raise ValueError('模型尚未训练完成')
    for name, digest in manifest['artifacts'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path) != digest:
            raise ValueError('模型产物校验失败')
    for name, digest in manifest['dependencies'].items():
        if name.startswith('validation/') and sha(ROOT / name) != digest:
            raise ValueError('模型执行代码已变化，请使用匹配版本或重新训练')
    return manifest


def predict(folder, rows, emit, device_override=None):
    import numpy as np
    folder = Path(folder); manifest = load_model(folder)
    family, cfg = manifest['family'], dict(manifest['parameters'])
    if device_override is not None:
        cfg['device'] = device_override
    if not rows or len(rows) > 100000 or any(not isinstance(row.get(k), str) or not row[k].strip() or len(row[k]) > 1000000 for row in rows for k in ('sentence1', 'sentence2')):
        raise ValueError('请提供有效的待预测句对，最多100000条')
    if family in ('lr', 'svm', 'rf'):
        import joblib
        bundle = joblib.load(folder / 'model.joblib')
        score = []
        for i in range(0, len(rows), 1000):
            batch = rows[i:i + 1000]
            x = bundle['scaler'].transform(legacy().feature_matrix(batch, bundle['vectorizer']))
            score.extend(legacy().classic_scores(bundle['model'], x, family).tolist())
            emit({'stage': 'PREDICTING', 'processed': min(i + 1000, len(rows)), 'total': len(rows)})
    else:
        import torch
        torch.set_num_threads(4)
        vocab = None; tokenizer = None
        if family == 'bert':
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(folder / 'bert', local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(folder / 'bert', local_files_only=True)
        else:
            vocab = json.loads((folder / 'vocab.json').read_text(encoding='utf-8'))
            model = legacy().SentencePairNet(family, len(vocab) + 2, cfg['width'])
            model.load_state_dict(torch.load(folder / 'best.pt', map_location='cpu', weights_only=True))
        model.to(cfg['device'])
        score = neural_scores(model, family, rows, cfg, vocab, tokenizer, emit)
    if not np.isfinite(score).all():
        raise ValueError('预测得分无效')
    threshold = 0. if family == 'svm' else .5
    return [{'id': row.get('id', str(i + 1)), 'sentence1': row['sentence1'], 'sentence2': row['sentence2'], 'score': float(s), 'predicted': int(s >= threshold), 'scoreType': 'margin' if family == 'svm' else 'probability', **({'label': int(row['label'])} if 'label' in row else {})} for i, (row, s) in enumerate(zip(rows, score))]


def evaluate(model_folder, prepared_folder, output, emit):
    _, splits = prepared(prepared_folder)
    model = load_model(model_folder)
    identities = json.loads((Path(model_folder) / 'train-identities.json').read_text(encoding='utf-8'))
    sentences = set(identities['sentences']); groups = set(identities['groups'])
    if any(row['_partitionGroup'] in groups or any(hashlib.sha256(row[key].encode()).hexdigest() in sentences for key in ('sentence1', 'sentence2')) for row in splits['test']):
        raise ValueError('评价集与模型训练数据存在来源/句子重合，请选择独立数据版本')
    predictions = predict(model_folder, splits['test'], emit)
    result, _ = metric_report(splits['test'], [row['score'] for row in predictions], model['family'])
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    path = output / 'predictions.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in predictions), encoding='utf-8')
    result = {'taskType': 'EVALUATION', 'status': 'COMPLETED', 'metrics': result, 'modelSha256': sha(Path(model_folder) / 'manifest.json'), 'preparationSha256': sha(Path(prepared_folder) / 'manifest.json'), 'artifacts': {'predictions.jsonl': sha(path)}}
    write_json(output / 'manifest.json', result)
    return result
