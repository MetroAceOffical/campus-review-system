"""Freeze source/event groups before construction; public training overlap is train-only."""
import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

from corpus import cluster_splits, normalized, read_jsonl

ROOT = Path(__file__).resolve().parents[2]


def training_overlap(documents, training_texts):
    canonical = {key:normalized(text) for key,text in documents.items()}
    index = {}
    for key,text in canonical.items():
        offsets = set(range(0,max(0,len(text)-63),8))
        if len(text)>=64:
            offsets.add(len(text)-64)
        for offset in offsets:
            code = hashlib.blake2b(text[offset:offset+64].encode(),digest_size=8).digest()
            previous = index.get(code)
            if previous is None:
                index[code] = key
            elif previous != key:
                index[code] = tuple(sorted(set(previous if isinstance(previous,tuple) else (previous,))|{key}))
    flagged = set()
    for text in training_texts:
        text = normalized(text)
        for offset in range(max(0,len(text)-63)):
            window = text[offset:offset+64]
            candidates = index.get(hashlib.blake2b(window.encode(),digest_size=8).digest())
            if candidates:
                for key in candidates if isinstance(candidates,tuple) else (candidates,):
                    if key not in flagged and window in canonical[key]:
                        flagged.add(key)
    return flagged


def event_edges(rows):
    by_id = {row['documentId']:row for row in rows}
    titles = {}
    frequency = Counter()
    for key,row in by_id.items():
        title = normalized(row['title'])
        values = {title[i:i+3] for i in range(max(0,len(title)-2))}
        titles[key] = values;frequency.update(values)
    buckets = defaultdict(list);candidates = set()
    for key in sorted(titles):
        for value in titles[key]:
            if frequency[value] >= 50:
                continue
            for other in buckets[value]:
                candidates.add((other,key))
            buckets[value].append(key)
    edges = []
    for left,right in sorted(candidates):
        a,b = by_id[left],by_id[right]
        if min(len(normalized(a['title'])),len(normalized(b['title']))) < 12:
            continue
        union = titles[left]|titles[right]
        similarity = len(titles[left]&titles[right])/max(1,len(union))
        same_school = a['institutionName'] == b['institutionName']
        if similarity < (.55 if same_school else .85):
            continue
        dates = [re.search(r'\d{4}-\d{2}-\d{2}',str(row.get('publishedAt') or '')) for row in (a,b)]
        if all(dates):
            gap = abs((datetime.fromisoformat(dates[0][0])-datetime.fromisoformat(dates[1][0])).days)
            if gap > 14:
                continue
        elif similarity < .8:
            continue
        edges.append((left,right))
    return edges


def assign_partitions(rows, related_events, contaminated, seed=20261026):
    documents = {row['documentId']:row['text'] for row in rows}
    source_groups = defaultdict(list)
    for row in rows:
        source_groups[row['sourceClusterId']].append(row['documentId'])
    edges = list(related_events)
    for ids in source_groups.values():
        edges.extend((ids[0],key) for key in ids[1:])
    grouped = cluster_splits(documents,edges,seed)
    components = defaultdict(list)
    by_id = {row['documentId']:row for row in rows}
    for key,value in grouped.items():
        components[value['eventClusterId']].append(key)
    result = {}
    for cluster,ids in sorted(components.items()):
        overlap = bool(set(ids)&set(contaminated))
        primary = any(by_id[key]['institutionName']=='南京传媒学院' for key in ids)
        bucket = int(hashlib.sha256(f'{seed}:campus:{cluster}'.encode()).hexdigest()[:8],16)%10000
        # Reserve more home-campus source families for development/final material construction.
        train_end,calibration_end,dev_end = (4050,4500,6000) if primary else (6300,7000,8000)
        split = 'train' if overlap or bucket<train_end else 'calibration' if bucket<calibration_end else 'dev' if bucket<dev_end else 'final'
        for key in ids:
            result[key] = {'sourceClusterId':by_id[key]['sourceClusterId'],'eventClusterId':cluster,'split':split,
                           'publicTrainingOverlap':overlap,'eventLabelOrigin':'conservative_automatic_grouping'}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus',type=Path,default=ROOT/'runtime/datasets/campus-clean-20261026-v2')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-partitions-20261026-v1')
    args = parser.parse_args()
    if (args.output/'READY').exists():
        raise RuntimeError('Partition version already frozen')
    args.output.mkdir(parents=True,exist_ok=True)
    inputs = json.loads((args.corpus/'READY').read_text(encoding='utf-8'))
    for name,sha in inputs.items():
        with (args.corpus/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=sha:
                raise ValueError('Campus snapshot changed')
    rows = list(read_jsonl(args.corpus/'corpus.jsonl'))
    t2 = ROOT/'runtime/datasets/t2ranking-training-v1'
    if not (t2/'READY').exists():
        raise RuntimeError('Selected public training shard is not ready')
    def training_texts():
        for folder,selected in [(t2,None),(ROOT/'runtime/datasets/final-training-v1',ROOT/'runtime/experiments/final-training-20261026/retriever-aux-v1/train-groups.json')]:
            allowed = None
            if selected:
                groups = json.loads(selected.read_text(encoding='utf-8'))
                allowed = {key for group in groups for key in [group['queryId'],group['positiveId']]+group['negativeIds']}
            db = sqlite3.connect(f'file:{(folder/"auxiliary.sqlite").as_posix()}?mode=ro',uri=True)
            try:
                for key,text in db.execute('SELECT id,text FROM documents'):
                    if allowed is None or key in allowed:
                        yield text
            finally:
                db.close()
    flagged = training_overlap({row['documentId']:row['text'] for row in rows},training_texts())
    edges = event_edges(rows)
    partitions = assign_partitions(rows,edges,flagged)
    for split in ['train','calibration','dev','final']:
        with (args.output/(split+'.jsonl')).open('w',encoding='utf-8') as stream:
            for row in rows:
                assignment = partitions[row['documentId']]
                if assignment['split']==split:
                    stream.write(json.dumps({**row,**assignment},ensure_ascii=False)+'\n')
    summary = {'state':'SOURCE_PARTITIONS_FROZEN_BEFORE_CONSTRUCTION','seed':20261026,'sourceCount':len(rows),
               'sourcesBySplit':dict(Counter(value['split'] for value in partitions.values())),
               'eventGroupsBySplit':{split:len({value['eventClusterId'] for value in partitions.values() if value['split']==split}) for split in ['train','calibration','dev','final']},
               'homeCampusBySplit':dict(Counter(partitions[row['documentId']]['split'] for row in rows if row['institutionName']=='南京传媒学院')),
               'publicTrainingOverlappingSources':len(flagged),'additionalTitleDateEdges':len(edges),'sourceSnapshotSha256':inputs['corpus.jsonl'],
               'eventLabelOrigin':'conservative_automatic_grouping_not_human_gold','queryConstructionComplete':False,'finalProtocolExecuted':False,
               'decontaminationScope':'All selected T2 query/passage bodies and actually used news auxiliary bodies. Sampled campus 64-character sentinels at stride8; complete training scan. Guaranteed detection of >=71 contiguous normalized characters, shorter spans/semantic-only common provenance remain a limitation.',
               'splitPolicy':'General 63/7/10/20%, home-campus families 40.5/4.5/15/40%; any overlapping event forced train. Calibration is disjoint from neural training.'}
    (args.output/'split-manifest.json').write_text(json.dumps({'summary':summary,'sources':partitions},ensure_ascii=False,indent=2),encoding='utf-8')
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()}
    (args.output/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
