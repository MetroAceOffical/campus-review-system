"""Verify downloaded bytes and prepare auxiliary retrieval supervision only."""
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from corpus import cluster_splits, normalized

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runtime/datasets/final-training-v1'


def parse_header(line):
    fields = line.rstrip('\n').split('|')
    if len(fields) != 19 or fields[:3] != ['label','doc_id1','doc_id2']:
        raise ValueError('Unexpected public data schema')
    return fields


def main():
    acquisition = json.loads((ROOT/'runtime/experiments/final-design-20261026/public-data-acquisition.json').read_text(encoding='utf-8'))
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'READY').exists():
        raise RuntimeError('Prepared dataset is immutable; select a new version before rebuilding')
    documents, pairs, stats = {}, {}, Counter()
    for item in acquisition['datasets']:
        path = ROOT/item['path']
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream,'sha256').hexdigest()
        if actual != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('Downloaded data changed: '+str(path))
        if path.name == 'all.jsonl':
            stats['quarantined_mixed_schema_unknown_label_mapping'] += item['records']
            continue
        with path.open(encoding='utf-8') as stream:
            header = parse_header(next(stream))
            for line in stream:
                values = line.rstrip('\n').split('|')
                if len(values) != 19:
                    stats['malformed'] += 1
                    continue
                row = dict(zip(header,values))
                left,right = 'apm:'+row['doc_id1'], 'apm:'+row['doc_id2']
                for key,text in ((left,row['content1']),(right,row['content2'])):
                    text = text.replace('\\n','\n').strip()
                    if key in documents and normalized(documents[key]) != normalized(text):
                        raise ValueError('One document identity has different bodies')
                    documents[key] = text
                task = 'SAME_EVENT' if path.name.startswith('same_event') else 'SAME_STORY'
                key = (task,*sorted((left,right)))
                label = int(row['label'])
                if key in pairs and pairs[key] != label:
                    raise ValueError('Conflicting published relation')
                pairs[key] = label
                stats['raw_pair_rows'] += 1
    splits = cluster_splits(documents,[(left,right) for (_,left,right),label in pairs.items() if label == 1])
    db = sqlite3.connect(OUT/'auxiliary.sqlite')
    db.executescript('DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS pairs; CREATE TABLE documents(id TEXT PRIMARY KEY,text TEXT,cluster TEXT,split TEXT); CREATE TABLE pairs(id TEXT PRIMARY KEY,left_id TEXT,right_id TEXT,target INT,task TEXT,split TEXT);')
    db.executemany('INSERT INTO documents VALUES(?,?,?,?)',[(key,text,splits[key]['eventClusterId'],splits[key]['split']) for key,text in documents.items()])
    with (OUT/'auxiliary-pairs.jsonl').open('w',encoding='utf-8') as output:
        for (task,left,right),label in sorted(pairs.items()):
            if splits[left]['split'] != splits[right]['split']:
                stats['excluded_cross_partition_pair'] += 1
                continue
            if label == 0 and splits[left]['eventClusterId'] == splits[right]['eventClusterId']:
                stats['excluded_negative_inside_positive_component'] += 1
                continue
            if min(len(normalized(documents[left])),len(normalized(documents[right]))) < 64:
                stats['excluded_short_text'] += 1
                continue
            pair_id = hashlib.sha256(f'{task}:{left}:{right}'.encode()).hexdigest()
            split = splits[left]['split']
            record = {'id':pair_id,'taskType':'RETRIEVAL_RELEVANCE','relationType':task,'labelOrigin':'published_event_label',
                      'labelConfidence':'known_auxiliary_only','sourceClusterId':splits[right]['sourceClusterId'],
                      'eventClusterId':splits[left]['eventClusterId'],'split':split,'queryId':left,'sourceId':right,'target':label,
                      'sourceOffsets':None,'scope':'Auxiliary event/story relevance, not content correspondence or campus gold.'}
            output.write(json.dumps(record,ensure_ascii=False)+'\n')
            db.execute('INSERT INTO pairs VALUES(?,?,?,?,?,?)',(pair_id,left,right,label,task,split))
            stats[f'{split}_label_{label}'] += 1
    db.commit()
    db.close()
    manifest = {'schemaVersion':'1','seed':20261026,'phase':'auxiliary_retrieval_prepared','statistics':dict(stats),
                'documents':len(documents),'eventComponents':len({v['eventClusterId'] for v in splits.values()}),
                'largestComponentDocuments':Counter(v['eventClusterId'] for v in splits.values()).most_common(1)[0][1],
                'sourceInputs':acquisition['datasets'],'campusCorrespondenceRecords':0,'trainingStarted':False,
                'limitation':'Exact body dedup and positive-relation components only. Additional campus near-duplicate/event clustering required before campus splits freeze.'}
    (OUT/'split-manifest.json').write_text(json.dumps(splits,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    (OUT/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in {'sourceInputs'}},ensure_ascii=True))


if __name__ == '__main__':
    main()
