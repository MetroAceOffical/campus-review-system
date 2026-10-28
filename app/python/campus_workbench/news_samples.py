"""Traceable NEWS -> labelled PAIRS, without changing the input or old runs."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

from .preparation import lines, sha, write_json

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / 'runtime/models/final/Qwen2.5-3B-Instruct/aa8e72537993ba99e69dfaafa59ed015b17504d1'
DEFAULTS = {'max_originals': 0, 'segment_characters': 360, 'min_characters': 64, 'variants': 1,
            'negative_candidates': 40, 'negatives_per_positive': 1, 'attempts': 2,
            'seed': 20261028, 'device': 'cuda', 'reuse_existing': True}
PARTS = ('train', 'validation', 'test', 'calibration')


def options(values):
    if not isinstance(values, dict) or set(values) - DEFAULTS.keys():
        raise ValueError('样本准备参数无效')
    cfg = DEFAULTS | values
    bounds = {'max_originals': (0, 100000), 'segment_characters': (128, 512), 'min_characters': (32, 256),
              'variants': (1, 4), 'negative_candidates': (5, 200), 'negatives_per_positive': (1, 4),
              'attempts': (1, 4), 'seed': (0, 2147483647)}
    for name, (low, high) in bounds.items():
        if type(cfg[name]) is not int or not low <= cfg[name] <= high:
            raise ValueError(f'{name}须在{low}—{high}范围内')
    if cfg['min_characters'] > cfg['segment_characters'] or cfg['device'] not in ('cpu', 'cuda') or type(cfg['reuse_existing']) is not bool:
        raise ValueError('段落长度、设备或复用选项无效')
    return cfg


def helpers():
    folder = str(ROOT / 'app/training')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    from construct_correspondence import source_segments, generation_prompt, generation_options, rewrite_checks
    from negative_basis import assess_difference, RULE_VERSION
    return source_segments, generation_prompt, generation_options, rewrite_checks, assess_difference, RULE_VERSION


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_news(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('kind') != 'NEWS' or manifest.get('taskType') != 'PREPARATION':
        raise ValueError('请选择新闻原稿分组版本')
    for name, expected in manifest['artifacts'].items():
        if name not in {*(f'{part}.jsonl' for part in PARTS), 'segments.jsonl'} or sha(folder / name) != expected:
            raise ValueError('新闻分组版本校验失败')
    return manifest, {part: lines(folder / f'{part}.jsonl') for part in PARTS}


def windows(parts, cfg):
    segmenter = helpers()[0]
    pool, skips = {part: [] for part in PARTS}, Counter()
    for part, rows in parts.items():
        for row in rows:
            seen = set()
            for span in segmenter(row['text'], cfg['segment_characters']):
                start, end = span['sourceStart'], span['sourceEnd']
                text = row['text'][start:end]
                if len(re.sub(r'\s+', '', text)) < cfg['min_characters']:
                    skips['SHORT_SEGMENT'] += 1; continue
                if text in seen:
                    skips['REPEATED_SEGMENT_IN_ARTICLE'] += 1; continue
                seen.add(text)
                pool[part].append({'sourceId': row['id'], 'sourceClusterId': row.get('source_cluster_id') or row['_partitionGroup'],
                                   'eventClusterId': row.get('event_cluster_id') or row['_partitionGroup'],
                                   'groupId': row['_partitionGroup'], 'title': row.get('title', ''),
                                   'institutionName': row.get('source_institution', ''), 'publishedAt': row.get('published_at', ''),
                                   'start': start, 'end': end, 'text': text, 'split': part})
    owners = defaultdict(set)
    for part, values in pool.items():
        for row in values:
            owners[row['text']].add(part)
    for part in PARTS:
        retained = [row for row in pool[part] if len(owners[row['text']]) == 1]
        skips['CROSS_PARTITION_SEGMENT'] += len(pool[part]) - len(retained)
        pool[part] = retained
    return pool, skips


def old_rewrites():
    """Read-only optional cache, exact original text identity is mandatory."""
    folder = ROOT / 'runtime/experiments/final-training-20261026/campus-generation-v3'
    if not (folder / 'generation.sqlite').is_file():
        return {}
    try:
        config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
        source = ROOT / 'runtime/datasets/campus-partitions-20261026-v1/train.jsonl'
        if sha(source) != config['partitionTrainSha256']:
            return {}
        originals = {row['documentId']: row['text'] for row in lines(source)}
        result = {}
        with sqlite3.connect(f'file:{(folder / "generation.sqlite").resolve().as_posix()}?mode=ro', uri=True) as db:
            for parent, start, end, text in db.execute("SELECT parent_id,start,end,result FROM segments WHERE state='ACCEPTED'"):
                if parent in originals:
                    result[(parent, digest(originals[parent][start:end]))] = text
        return result
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return {}


class Rewriter:
    def __init__(self, cfg, emit):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.torch, self.cfg = torch, cfg
        torch.set_num_threads(4)
        if cfg['device'] == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA不可用，请选择CPU或检查现有环境')
        emit({'stage': 'GENERATOR_LOADING', 'processed': 0, 'total': 1})
        acquisition = json.loads((MODEL / 'acquisition.json').read_text(encoding='utf-8'))
        for item in acquisition['files']:
            if sha(MODEL / item['file']) != item['sha256']:
                raise ValueError('改写基础权重校验失败')
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16,
                     device_map={'': cfg['device']}, attn_implementation='sdpa', local_files_only=True, trust_remote_code=False).eval()

    def __call__(self, text, entities, seed, attempt):
        _, prompt, sampling, _, _, _ = helpers()
        self.torch.manual_seed(seed % (2 ** 63 - 1))
        tokens = self.tokenizer.apply_chat_template([{'role': 'system', 'content': '你是严谨的中文校园新闻编辑。保留事实和数字，不编造。'}, {'role': 'user', 'content': prompt(text, entities, '3')}], add_generation_prompt=True, return_tensors='pt').to(self.cfg['device'])
        if tokens.shape[1] > 2048:
            return '', {'inputTokens': int(tokens.shape[1]), 'budgetExceeded': True}
        with self.torch.inference_mode():
            result = self.model.generate(tokens, attention_mask=self.torch.ones_like(tokens), max_new_tokens=640,
                      do_sample=True, **sampling('3', attempt), pad_token_id=self.tokenizer.eos_token_id)
        generated = result[0, tokens.shape[1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip(), {'inputTokens': int(tokens.shape[1]), 'outputTokens': len(generated), 'budgetExceeded': len(generated) >= 640 and int(generated[-1]) != self.tokenizer.eos_token_id}


def generate(folder, output, values, emit, resume=None, rewriter=None, caches=()):
    cfg = options(values)
    source_manifest, parts = read_news(folder)
    pool, skips = windows(parts, cfg)
    _, _, _, check_rewrite, assess_difference, rule_version = helpers()
    output = Path(output); work = output.parent
    work.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError('样本版本目录已存在，请使用新任务')
    # Round-robin selects across fixed partitions only when the user explicitly
    # limits originals. The normal setting 0 consumes every eligible original.
    ordered = []
    choices = {part: sorted({r['sourceId'] for r in pool[part]}, key=lambda key: digest(f'{cfg["seed"]}:{key}')) for part in PARTS}
    for i in range(max((len(values) for values in choices.values()), default=0)):
        ordered.extend((part, choices[part][i]) for part in PARTS if i < len(choices[part]))
    selected = set(ordered[:cfg['max_originals']] if cfg['max_originals'] else ordered)
    selected_windows = [row for part in PARTS for row in pool[part] if (part, row['sourceId']) in selected]
    if not selected_windows:
        raise ValueError('原稿没有符合长度要求的段落，请调整长度或补充原稿')
    identity = {'preparationSha256': sha(Path(folder) / 'manifest.json'), 'parameters': cfg,
                'generatorRevision': MODEL.name, 'ruleVersion': rule_version, 'processorVersion': 'news-samples-1',
                'algorithmSha256': sha(Path(__file__)), 'differenceRuleSha256': sha(ROOT / 'app/training/negative_basis.py'),
                'rewriteRuleSha256': sha(ROOT / 'app/training/construct_correspondence.py')}
    fingerprint = digest(json.dumps(identity, sort_keys=True))
    database = work / 'generation.sqlite'
    if resume and not database.exists():
        previous = Path(resume) / 'generation.sqlite'
        if not previous.is_file():
            raise ValueError('没有可继续的生成检查点')
        with sqlite3.connect(f'file:{previous.resolve().as_posix()}?mode=ro', uri=True) as old, sqlite3.connect(database) as new:
            old.backup(new)
    db = sqlite3.connect(database)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('CREATE TABLE IF NOT EXISTS identity(fingerprint TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS segment(id TEXT PRIMARY KEY,source_id TEXT,split TEXT,start INT,end INT,variant INT,state TEXT,attempts INT,result TEXT,checks TEXT,seconds REAL); CREATE TABLE IF NOT EXISTS attempt(id INTEGER PRIMARY KEY,segment_id TEXT,attempt_no INT,output TEXT,checks TEXT,seconds REAL);')
    previous = db.execute('SELECT fingerprint FROM identity').fetchone()
    if previous and previous[0] != fingerprint:
        db.close(); raise ValueError('检查点与本次原稿或参数不一致，请新建样本任务')
    db.execute('INSERT OR IGNORE INTO identity VALUES(?)', (fingerprint,))
    lookup = {}
    for row in selected_windows:
        for variant in range(cfg['variants']):
            key = digest(f'{row["sourceId"]}:{row["split"]}:{row["start"]}:{row["end"]}:{variant}:{digest(row["text"])}')
            lookup[key] = row
            db.execute('INSERT OR IGNORE INTO segment VALUES(?,?,?,?,?,?,?,0,NULL,NULL,0)', (key, row['sourceId'], row['split'], row['start'], row['end'], variant, 'PENDING'))
    db.commit()
    cache = old_rewrites() if cfg['reuse_existing'] else {}
    if cfg['reuse_existing']:
        originals = {row['id']: row['text'] for values in parts.values() for row in values}
        for cache_folder in caches:
            path = Path(cache_folder) / 'generation.sqlite'
            if not path.is_file():
                continue
            # These paths are selected by Java from the same authorized dataset
            # and immutable input version, never accepted from an upload.
            with sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True) as previous:
                for parent, start, end, result in previous.execute("SELECT source_id,start,end,result FROM segment WHERE state='ACCEPTED' ORDER BY variant"):
                    if parent in originals and 0 <= start < end <= len(originals[parent]):
                        cache.setdefault((parent, digest(originals[parent][start:end])), result)
    started = time.monotonic(); reused = 0
    def progress(stage, preview=None):
        counts = dict(db.execute('SELECT state,COUNT(*) FROM segment GROUP BY state'))
        value = {'stage': stage, 'processed': counts.get('ACCEPTED', 0) + counts.get('QUARANTINED', 0), 'total': len(lookup),
                 'accepted': counts.get('ACCEPTED', 0), 'quarantined': counts.get('QUARANTINED', 0), 'reused': reused,
                 'originals': len(selected), 'elapsedSeconds': time.monotonic() - started}
        if preview:
            value['preview'] = preview
        emit(value)
    progress('SAMPLE_PLANNED')
    generator = rewriter
    try:
        for key, variant, attempts in db.execute("SELECT id,variant,attempts FROM segment WHERE state='PENDING' ORDER BY split,source_id,start,variant").fetchall():
            row = lookup[key]; text = row['text']
            entities = [row['institutionName']] + re.findall(r'[“《]([^”》]{2,30})[”》]', text)
            cached = cache.get((row['sourceId'], digest(text))) if variant == 0 else None
            if cached:
                checks = check_rewrite(text, cached, entities, require_rewording=True)
                if checks['accepted']:
                    checks['reusedExisting'] = True; reused += 1
                    db.execute("UPDATE segment SET state='ACCEPTED',result=?,checks=? WHERE id=?", (cached, json.dumps(checks, ensure_ascii=False), key));db.commit()
                    progress('GENERATING', {'source': text, 'rewritten': cached, 'accepted': True, 'reused': True});continue
            for attempt in range(attempts, cfg['attempts']):
                if generator is None:
                    generator = Rewriter(cfg, emit)
                tick = time.monotonic()
                rewritten, budget = generator(text, entities, cfg['seed'] + int(key[:12], 16) + attempt, attempt)
                checks = check_rewrite(text, rewritten, entities, require_rewording=True)
                checks.update(budget)
                if budget.get('budgetExceeded'):
                    checks['accepted'] = False;checks['reasons'].append('TOKEN_BUDGET')
                elapsed = time.monotonic() - tick
                status = 'ACCEPTED' if checks['accepted'] else 'QUARANTINED' if attempt + 1 == cfg['attempts'] else 'PENDING'
                encoded = json.dumps(checks, ensure_ascii=False)
                db.execute('INSERT INTO attempt(segment_id,attempt_no,output,checks,seconds) VALUES(?,?,?,?,?)', (key, attempt + 1, rewritten, encoded, elapsed))
                db.execute('UPDATE segment SET state=?,attempts=?,result=?,checks=?,seconds=seconds+? WHERE id=?', (status, attempt + 1, rewritten, encoded, elapsed, key));db.commit()
                progress('GENERATING', {'source': text, 'rewritten': rewritten, 'accepted': checks['accepted'], 'reasons': checks['reasons']})
                if checks['accepted']:
                    break
        # Release generator memory before sparse CPU mining/assembly.
        if isinstance(generator, Rewriter):
            import gc
            import torch
            del generator;gc.collect()
            if torch.cuda.is_available():torch.cuda.empty_cache()
        result = assemble(db, lookup, pool, cfg, assess_difference, emit, output, identity, source_manifest, skips, selected)
        return result
    finally:
        db.close()


def assemble(db, lookup, pool, cfg, assess_difference, emit, output, identity, source_manifest, skips, selected):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    indexes = {}
    for part, rows in pool.items():
        if not rows:
            continue
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3), max_features=40000, dtype=np.float32)
        matrix = vectorizer.fit_transform([row['text'] for row in rows])
        neighbors = NearestNeighbors(metric='cosine', algorithm='brute', n_neighbors=min(cfg['negative_candidates'], len(rows))).fit(matrix)
        indexes[part] = (vectorizer, neighbors)
    pairs = {part: [] for part in PARTS}; quarantine = []; labels = Counter(); seen = {}; text_partitions = defaultdict(set)
    for key, status, rewritten, checks in db.execute('SELECT id,state,result,checks FROM segment'):
        row = lookup[key]
        if status != 'ACCEPTED':
            quarantine.append({'sampleId': key, 'sourceId': row['sourceId'], 'source': row['text'], 'rewritten': rewritten, 'reasons': json.loads(checks or '{}').get('reasons', ['NO_RESULT'])})
        else:
            text_partitions[rewritten].add(row['split'])
    def append(row):
        key = tuple(sorted((row['sentence1'], row['sentence2'])))
        if key in seen:
            previous = seen[key]
            if previous['label'] != row['label']:
                previous['_rejected'] = True;quarantine.extend([dict(previous, reasons=['LABEL_CONFLICT']), dict(row, reasons=['LABEL_CONFLICT'])])
            else:
                skips['DUPLICATE_PAIR'] += 1
            return
        if len(seen) >= 500000:
            raise ValueError('本批样本超过500000条，请按原稿分批准备；检查点已保存')
        seen[key] = row;pairs[row['split']].append(row);labels[str(row['label'])] += 1
    accepted = db.execute("SELECT id,result,checks FROM segment WHERE state='ACCEPTED' ORDER BY split,source_id,start,variant").fetchall()
    # Cache supported negatives for variants of the same source window.
    negative_cache = {}
    for index, (key, rewritten, checks_json) in enumerate(accepted):
        row = lookup[key];part = row['split']
        if len(text_partitions[rewritten]) > 1:
            quarantine.append({'sampleId': key, 'sourceId': row['sourceId'], 'source': row['text'], 'rewritten': rewritten, 'reasons': ['CROSS_PARTITION_REWRITE']});continue
        common = {'source_id': row['sourceId'], 'group_id': row['groupId'], '_partitionGroup': row['groupId'], 'split': part, 'sourceOffsets': {'start': row['start'], 'end': row['end']}, 'humanVerified': False}
        append(dict(common, id=key, sentence1=row['text'], sentence2=rewritten, label=1, label_origin='controlled_paraphrase', checks=json.loads(checks_json)))
        cache_key = (part, row['sourceId'], row['start'], row['end'])
        if cache_key not in negative_cache:
            negatives = []
            vectorizer, neighbors = indexes[part]
            candidate_indices = neighbors.kneighbors(vectorizer.transform([row['text']]), return_distance=False)[0]
            for candidate_index in candidate_indices:
                other = pool[part][int(candidate_index)]
                if row['sourceId'] == other['sourceId'] or row['groupId'] == other['groupId']:
                    continue
                basis = assess_difference(row, other)
                if basis['supported']:
                    negatives.append((other, basis))
                    if len(negatives) >= cfg['negatives_per_positive'] * cfg['variants']:
                        break
            negative_cache[cache_key] = negatives
        found = negative_cache[cache_key]
        for other, basis in found:
            candidate_key = digest(key + ':' + other['sourceId'] + ':' + str(other['start']))
            append(dict(common, id=candidate_key, sentence1=row['text'], sentence2=other['text'], label=0,
                        label_origin='rule_supported_negative', sourceIds=[row['sourceId'], other['sourceId']],
                        candidateOffsets={'start': other['start'], 'end': other['end']}, differenceBasis=basis))
        if not found:
            skips['NO_SUPPORTED_NEGATIVE'] += 1
        if (index + 1) % max(1, len(accepted) // 100) == 0 or index + 1 == len(accepted):
            emit({'stage': 'NEGATIVE_MINING', 'processed': index + 1, 'total': len(accepted), 'positivePairs': labels['1'], 'negativePairs': labels['0'], 'quarantined': len(quarantine), 'missingNegatives': skips['NO_SUPPORTED_NEGATIVE']})
    # Remove any generated sentence that exactly matches another partition's
    # original text; quarantine the whole pair rather than move held-out rows.
    owners = defaultdict(set)
    for part, rows in pairs.items():
        for row in rows:
            for field in ('sentence1', 'sentence2'):owners[row[field]].add(part)
    for part, rows in pairs.items():
        kept = []
        for row in rows:
            if row.get('_rejected'):
                continue
            if any(len(owners[row[field]]) > 1 for field in ('sentence1', 'sentence2')):
                quarantine.append(dict(row, reasons=['CROSS_PARTITION_SENTENCE']))
            else:
                kept.append(row)
        pairs[part] = kept
    output.mkdir(parents=True, exist_ok=False)
    paths = []
    for part, rows in pairs.items():
        path = output / f'{part}.jsonl';path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8');paths.append(path)
    for name, rows in [('pairs.jsonl', [row for values in pairs.values() for row in values]), ('quarantine.jsonl', quarantine)]:
        path = output / name;path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8');paths.append(path)
    partitions = {part: {'rows': len(rows), 'groups': len({row['group_id'] for row in rows}), 'labels': dict(Counter(str(row['label']) for row in rows))} for part, rows in pairs.items()}
    missing = [part for part in ('train', 'validation', 'test') if set(partitions[part]['labels']) != {'0', '1'}]
    counts = dict(db.execute('SELECT state,COUNT(*) FROM segment GROUP BY state'))
    manifest = {'schemaVersion': 1, 'taskType': 'PREPARATION', 'status': 'COMPLETED', 'kind': 'PAIRS', 'sourceKind': 'NEWS',
                'inputSha256': source_manifest['inputSha256'], 'inputRows': source_manifest['inputRows'], 'outputRows': sum(len(rows) for rows in pairs.values()),
                'groups': source_manifest['groups'], 'partitions': partitions, 'trainReady': not missing, 'requiresLabels': False,
                'missingClassPartitions': missing, 'identity': identity, 'selectedOriginals': len(selected), 'segmentCounts': counts,
                'quarantineRows': len(quarantine), 'skipped': dict(skips), 'labelOrigins': dict(Counter(row['label_origin'] for rows in pairs.values() for row in rows)),
                'preview': [row for rows in pairs.values() for row in rows][:12], 'artifacts': {path.name: sha(path) for path in paths}}
    write_json(output / 'manifest.json', manifest)
    emit({'stage': 'SAMPLES_SAVED', 'processed': manifest['outputRows'], 'total': manifest['outputRows'], 'trainReady': manifest['trainReady'], 'quarantined': len(quarantine)})
    return manifest
