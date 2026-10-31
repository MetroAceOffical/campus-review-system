"""Reuse committed, checked material for the web's six-model experiments.

Does not run generation/training or modify protected source datasets. Output
is a new versioned package; partial generation is identified as a snapshot.
"""
from collections import Counter
import hashlib,json,re,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'app/python'),str(ROOT/'app/training')]
from campus_workbench.curated_bundles import isolate,partition
from campus_workbench.preparation import sha,prepared
from construct_correspondence import verify_ready,rewrite_checks
from prepare_correspondence import generated_pairs

OUTPUT=ROOT/'runtime/datasets/six-model-20261031-v1'
def read(path):
    with Path(path).open(encoding='utf8') as f:return [json.loads(line) for line in f if line.strip()]
def write(path,rows):
    with path.open('w',encoding='utf8',newline='\n') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
def main():
    if (OUTPUT/'manifest.json').exists():raise RuntimeError('Frozen package already exists; use its manifest')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    quality=ROOT/'runtime/datasets/campus-quality-20261028-v1'
    corrected=ROOT/'runtime/datasets/campus-corrected-preparation-20261028-v1'
    quality_hashes=verify_ready(quality);verify_ready(corrected)
    parents={r['documentId']:r for r in read(quality/'train.jsonl')}
    # Sources/events, rather than individual generated windows, determine folds.
    union={}
    def find(x):
        union.setdefault(x,x)
        while union[x]!=x:union[x]=union[union[x]];x=union[x]
        return x
    for row in parents.values():
        keys=[row['documentId'],row['sourceClusterId'],row['eventClusterId']]
        root=min(find(k) for k in keys)
        for key in keys:union[find(key)]=root
    folds={key:partition(find(key)) for key in parents}
    stats=Counter();records=[]
    generation=ROOT/'runtime/experiments/final-training-20261028/campus-generation-v4'
    config=json.loads((generation/'config.json').read_text(encoding='utf8'))
    if config['partitionTrainSha256']!=quality_hashes['train.jsonl']:raise ValueError('Generation source changed')
    snapshot=OUTPUT/'generation-snapshot.sqlite'
    with sqlite3.connect(f'file:{(generation/"generation.sqlite").as_posix()}?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as target:source.backup(target)
    with sqlite3.connect(snapshot) as db:
        states=dict(db.execute('SELECT state,count(*) FROM segments GROUP BY state'))
        for parent_id,start,end,query,checks in db.execute("SELECT parent_id,start,end,result,checks FROM segments WHERE state='ACCEPTED' ORDER BY id"):
            parent=parents.get(parent_id)
            if not parent:stats['unmappedAcceptedSegment']+=1;continue
            text=parent['text'][start:end]
            current=rewrite_checks(text,query,[parent['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',text),require_rewording=True)
            if not json.loads(checks).get('accepted') or not current['accepted']:stats['strictRecheckRejected']+=1;continue
            records.append(dict(sourceIds=[parent_id],source=text,query=query,sourceOffsets=dict(start=start,end=end),checks=current,generatorRevision=config['generatorRevision']))
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'runtime/experiments/route-b-development-20261026/model',local_files_only=True,trust_remote_code=False,use_fast=True)
    candidates=read(corrected/'bootstrap-pairs.jsonl')
    candidates.extend(row for row in generated_pairs(parents,records,tokenizer,stats) if row['transformationKind']!='COPY_CONTROL')
    campus=[];provenance=[]
    for row in candidates:
        ids=set(row['sourceIds'])
        if row.get('positiveSource'):ids.add(row['positiveSource']['sourceId'])
        if row.get('candidateSource'):ids.add(row['candidateSource']['sourceId'])
        if not ids or ids-set(parents):stats['nonTrainingSource']+=1;continue
        parts={folds[key] for key in ids}
        if len(parts)!=1:stats['negativeCrossPartition']+=1;continue
        # Cross-school negatives belong to enhancement material, not the home set.
        home=all(parents[key].get('institutionName')=='南京传媒学院' for key in ids)
        raw='\0'.join(sorted([row['query'],row['source']]))
        identity=hashlib.sha256(raw.encode()).hexdigest()
        source_id=sorted(ids)[0]
        item=dict(id=identity,sentence1=row['query'],sentence2=row['source'],label=int(row['target']),split=next(iter(parts)),source_id=source_id,group_id=find(source_id),source_cluster_id=parents[source_id]['sourceClusterId'],event_cluster_id=parents[source_id]['eventClusterId'],label_origin=row['labelOrigin'],_home=home)
        campus.append(item)
        provenance.append(dict(id=identity,sourceIds=sorted(ids),sourceOffsets=row.get('sourceOffsets'),queryOffsets=row.get('queryOffsets'),labelOrigin=row['labelOrigin'],humanVerified=False,checks=row.get('constructionParent',{}).get('checks',row.get('checks')),negativeBasis=row.get('negativeBasis')))
    campus,bad,counters=isolate(campus);stats.update(counters)
    # Reuse the exact previous PAWS-X web partition, not the public held-out set.
    public_folder=ROOT/'runtime/workbench/computations/dd27217c-9ab5-4f6d-9e04-4a73c379c329/output'
    public_manifest,parts=prepared(public_folder)
    public=[]
    for name,rows in parts.items():
        for row in rows:
            public.append({**{k:row[k] for k in ('id','sentence1','sentence2','label','source_id','group_id','label_origin') if k in row},'split':name})
    sets={'public-pairs':public,'ncuc-news-pairs':[{k:v for k,v in r.items() if k!='_home'} for r in campus if r['_home']],'campus-enhancement-pairs':[{k:v for k,v in r.items() if k!='_home'} for r in campus if not r['_home']]}
    # The combined version retains the same folds as its source versions.
    combined,bad_combined,combined_counts=isolate([row for rows in sets.values() for row in rows])
    sets['combined-pairs']=combined
    result=dict(schemaVersion=1,sourceGenerationState='PAUSED_PARTIAL_ACCEPTED_SNAPSHOT',generationCounts=states,strictAcceptedSegments=len(records),statistics=dict(stats),combinedStatistics=combined_counts,originalsInTrainingDomain=len(parents),publicPreparationSha256=sha(public_folder/'manifest.json'),protectedPartitionHashes=quality_hashes,sets={})
    for name,rows in sets.items():
        path=OUTPUT/(name+'.jsonl');write(path,rows)
        counts={part:dict(Counter(str(r['label']) for r in rows if r['split']==part)) for part in ('train','validation','test')}
        if any(not all(int(counts[part].get(label,0))>0 for label in ('0','1')) for part in counts):raise ValueError('Dataset has missing classes: '+name)
        result['sets'][name]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path),rows=len(rows),bytes=path.stat().st_size,partitions=counts,sourceOriginals=len({r.get('source_id') for r in rows if r.get('source_id')}))
    write(OUTPUT/'provenance.jsonl',provenance);write(OUTPUT/'quarantine.jsonl',bad+bad_combined)
    result['snapshotSha256']=sha(snapshot);result['provenanceSha256']=sha(OUTPUT/'provenance.jsonl')
    (OUTPUT/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('protectedPartitionHashes',)},ensure_ascii=False))
if __name__=='__main__':main()
