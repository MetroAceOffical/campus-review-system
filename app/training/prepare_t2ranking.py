"""Build a 250k-pair auxiliary shard from official train labels only, streaming collection."""
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'runtime/datasets/public/t2ranking/2a369a430a70979223f1b9a41b1919774d46b432'
OUT = ROOT/'runtime/datasets/t2ranking-training-v1'


def prepare(source=SOURCE, output=OUT, query_count=50000):
    meta = json.loads((source/'acquisition.json').read_text(encoding='utf-8'))
    if meta['status'] != 'download_verified_not_trained':
        raise RuntimeError('T2Ranking acquisition incomplete')
    output.mkdir(parents=True,exist_ok=True)
    if (output/'READY').exists():
        raise RuntimeError('Immutable prepared shard already exists')
    for item in meta['files']:
        with (source/item['file']).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != item['sha256']:
                raise ValueError('Downloaded input changed')
    positives,negatives = defaultdict(set),defaultdict(set)
    with (source/'qrels.train.tsv').open(encoding='utf-8') as stream:
        for line in stream:
            qid,_,pid,grade = line.split()
            if grade == 'rel':
                continue
            grade = int(grade)
            if grade >= 2:
                positives[qid].add(pid)
            elif grade == 0:
                negatives[qid].add(pid)
    eligible = [qid for qid in positives if len(negatives[qid]-positives[qid]) >= 4]
    eligible.sort(key=lambda key:hashlib.sha256(f'20261026:{key}'.encode()).hexdigest())
    chosen = eligible[:query_count]
    if len(chosen) != query_count:
        raise ValueError('Insufficient independently labelled query groups')
    set_chosen = set(chosen)
    queries = {}
    with (source/'queries.train.tsv').open(encoding='utf-8') as stream:
        for line in stream:
            key,text = line.rstrip('\n').split('\t',1)
            if key in set_chosen:
                queries[key] = text
    pairs,needed = [],set()
    for qid in chosen:
        positive = sorted(positives[qid])[0]
        negative = sorted(negatives[qid]-positives[qid])[:4]
        for pid,target in [(positive,1)]+[(pid,0) for pid in negative]:
            pairs.append(('t2q:'+qid,'t2p:'+pid,target));needed.add(pid)
    db = sqlite3.connect(output/'auxiliary.sqlite')
    db.executescript('DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS pairs; CREATE TABLE documents(id TEXT PRIMARY KEY,text TEXT,cluster TEXT,split TEXT); CREATE TABLE pairs(id TEXT PRIMARY KEY,left_id TEXT,right_id TEXT,target INT,task TEXT,split TEXT);')
    for qid in chosen:
        if qid not in queries:
            raise ValueError('Missing selected query')
        db.execute('INSERT INTO documents VALUES(?,?,?,?)',('t2q:'+qid,queries[qid],'t2q:'+qid,'aux_train'))
    found = set()
    with (source/'collection.tsv').open(encoding='utf-8') as stream:
        for line in stream:
            pid,text = line.rstrip('\n').split('\t',1)
            if pid in needed:
                db.execute('INSERT INTO documents VALUES(?,?,?,?)',('t2p:'+pid,text,'t2p:'+pid,'aux_train'));found.add(pid)
    if found != needed:
        raise ValueError('Missing selected passages')
    for query,source,target in pairs:
        pair_id = hashlib.sha256(f'{query}:{source}'.encode()).hexdigest()
        db.execute('INSERT INTO pairs VALUES(?,?,?,?,?,?)',(pair_id,query,source,target,'T2RANKING','aux_train'))
    db.commit();db.close()
    manifest = {'schemaVersion':'1','taskType':'RETRIEVAL_RELEVANCE','labelOrigin':'published_relevance_grade',
                'positiveGrades':[2,3],'negativeGrade':0,'unusedGrade':1,'queryCount':len(chosen),'uniquePassages':len(found),
                'uniquePairCount':len(pairs),'positivePairs':len(chosen),'negativePairs':len(chosen)*4,
                'sourceRevision':meta['revision'],'sourceFiles':meta['files'],'seed':20261026,
                'split':'aux_train_only','auxiliaryValidationGroups':0,'trainingStarted':False,
                'scope':'Official train only. No campus/final queries. Campus decontamination must check selected query/passage bodies before its splits freeze.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='sourceFiles'}),flush=True)


if __name__ == '__main__':
    prepare()
