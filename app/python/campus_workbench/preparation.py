"""Immutable grouped partitions shared by the web and CLI training runners."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re

from .datasets import read_dataset


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')


def lines(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def prepare(input_path, output, kind, options, emit):
    seed = options.get('seed', 20261028)
    ratios = options.get('ratios', [.8, .1, .1])
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('随机种子须为0—2147483647的整数')
    if not isinstance(ratios, list) or len(ratios) != 3 or any(type(x) not in (int, float) or not .01 <= x <= .98 for x in ratios) or abs(sum(ratios) - 1) > .00001:
        raise ValueError('训练、验证、测试比例须大于0且合计为1')
    data = read_dataset(input_path, kind, internal=True)
    rows = data['rows']
    if data['issues'] or not rows:
        raise ValueError('请选择包含有效记录的清洗版本')
    if kind == 'PAIRS' and any(str(row['label']) not in {'0', '1'} for row in rows):
        raise ValueError('标签须为0或1，请先清洗数据')
    emit({'stage': 'GROUPING', 'processed': 0, 'total': len(rows)})
    parents = list(range(len(rows)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    first = {}
    fields = ('group_id', 'source_id', 'source_cluster_id', 'event_cluster_id')
    for i, row in enumerate(rows):
        keys = [(field, row[field]) for field in fields if row.get(field)]
        if kind == 'NEWS':
            keys += [('news', row.get('url') or row['id']), ('text', row['text'])]
        else:
            keys += [('sentence', row[field]) for field in ('sentence1', 'sentence2')]
        for key in keys:
            if key in first:
                parents[find(i)] = find(first[key])
            else:
                first[key] = i
        if (i + 1) % 1000 == 0 or i + 1 == len(rows):
            emit({'stage': 'GROUPING', 'processed': i + 1, 'total': len(rows)})
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[find(i)].append(row)
    aliases = {'train': 'train', 'training': 'train', 'validation': 'validation', 'val': 'validation', 'dev': 'validation', 'test': 'test', 'final': 'test', 'calibration': 'calibration', 'cal': 'calibration'}
    original = {row['split'].strip().lower() for row in rows if row.get('split', '').strip()}
    if original - aliases.keys():
        raise ValueError('存在不支持的原始分区名称')
    # Only the old train domain may be subdivided; old held-out records never
    # become training rows. Retain the input split alongside the new assignment.
    split_train_domain = not original or original <= {'train', 'training'}
    parts = {name: [] for name in ('train', 'validation', 'test', 'calibration')}
    counts = {name: Counter() for name in parts}
    all_labels = Counter(str(row['label']) if kind == 'PAIRS' else 'news' for row in rows)
    rng = random.Random(seed)
    components = list(groups.values())
    rng.shuffle(components)
    components.sort(key=len, reverse=True)
    targets = dict(zip(('train', 'validation', 'test'), ratios))
    group_sizes = Counter()
    for index, group in enumerate(components):
        fixed = {aliases[row['split'].strip().lower()] for row in group if row.get('split', '').strip()}
        if len(fixed) > 1:
            raise ValueError('同一来源/事件/句子组跨原始分区，请在新清洗版本解决分区冲突')
        labels = Counter(str(row['label']) if kind == 'PAIRS' else 'news' for row in group)
        if fixed and not split_train_domain:
            name = next(iter(fixed))
        else:
            # Minimize the change in squared class deficits, keeping each
            # connected component intact even when exact ratios are impossible.
            def cost(name):
                return sum(((counts[name][label] + n - all_labels[label] * targets[name]) ** 2 - (counts[name][label] - all_labels[label] * targets[name]) ** 2) / max(all_labels[label] * targets[name], 1) for label, n in labels.items())
            name = min(targets, key=cost)
        identity = hashlib.sha256('\n'.join(sorted(str(r['id']) for r in group)).encode()).hexdigest()
        for row in group:
            row['_inputSplit'] = row.get('split', '')
            row['split'] = name
            row['_partitionGroup'] = identity
        parts[name].extend(group)
        counts[name].update(labels)
        group_sizes[len(group)] += 1
        if (index + 1) % max(1, len(components) // 100) == 0 or index + 1 == len(components):
            emit({'stage': 'SPLITTING', 'processed': index + 1, 'total': len(components), 'rows': {key: len(value) for key, value in parts.items()}})
    quarantine=[]
    if kind=='PAIRS':
        from .curated_bundles import exclude_near_training
        isolated,quarantine,_=exclude_near_training([row for values in parts.values() for row in values])
        parts={name:[row for row in isolated if row['split']==name] for name in parts}
        counts={name:Counter(str(row['label']) for row in values) for name,values in parts.items()}
        if quarantine:emit({'stage':'PARTITION_ISOLATION','quarantined':len(quarantine),'message':'隔离与保留分区近重复的样本'})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    files = []
    if quarantine:
        path=output/'quarantine.jsonl';path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in quarantine),encoding='utf8');files.append(path)
    for name, values in parts.items():
        path = output / f'{name}.jsonl'
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in values), encoding='utf-8')
        files.append(path)
    segments = 0
    if kind == 'NEWS':
        with (output / 'segments.jsonl').open('w', encoding='utf-8') as stream:
            for values in parts.values():
                for row in values:
                    for match in re.finditer(r'[^\n。！？!?]+[。！？!?]?', row['text']):
                        text = match.group().strip()
                        if len(text) < 12:
                            continue
                        stream.write(json.dumps({'sourceId': row['id'], 'groupId': row['_partitionGroup'], 'split': row['split'], 'start': match.start(), 'end': match.end(), 'text': match.group(), 'labelStatus': 'PENDING'}, ensure_ascii=False) + '\n')
                        segments += 1
        files.append(output / 'segments.jsonl')
    missing = [name for name in targets if set(counts[name]) != {'0', '1'}] if kind == 'PAIRS' else []
    manifest = {'schemaVersion': 1, 'taskType': 'PREPARATION', 'status': 'COMPLETED', 'kind': kind, 'inputSha256': data['sourceSha256'], 'seed': seed, 'ratios': ratios, 'inputRows': len(rows), 'groups': len(groups), 'groupSizeDistribution': dict(group_sizes), 'partitions': {name: {'rows': len(parts[name]), 'groups': len({r['_partitionGroup'] for r in parts[name]}), 'labels': dict(counts[name])} for name in parts}, 'trainReady': kind == 'PAIRS' and not missing, 'missingClassPartitions': missing, 'segments': segments, 'requiresLabels': kind == 'NEWS', 'artifacts': {p.name: sha(p) for p in files}}
    write_json(output / 'manifest.json', manifest)
    emit({'stage': 'PREPARED', 'processed': len(rows), 'total': len(rows), 'trainReady': manifest['trainReady']})
    return manifest


def prepared(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('taskType') != 'PREPARATION' or not manifest.get('trainReady'):
        raise ValueError('该样本版本尚缺可训练的标签或类别，请先准备带标签句对')
    for name, digest in manifest['artifacts'].items():
        if name not in {'train.jsonl', 'validation.jsonl', 'test.jsonl', 'calibration.jsonl', 'pairs.jsonl', 'quarantine.jsonl'} or sha(folder / name) != digest:
            raise ValueError('样本版本校验失败')
    return manifest, {name: lines(folder / f'{name}.jsonl') for name in ('train', 'validation', 'test')}
