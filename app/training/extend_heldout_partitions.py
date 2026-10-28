"""Add audited heldout-only sources while copying neural training bytes unchanged."""
import argparse,hashlib,json,shutil
from collections import defaultdict,Counter
from pathlib import Path
from corpus import read_jsonl,cluster_splits
from construct_correspondence import verify_ready
ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def extend(parent,extension,output):
    if output.exists() or not output.resolve().is_relative_to(ROOT/'runtime/datasets'):raise ValueError('Use a new evaluation partition version')
    parent_hashes=verify_ready(parent);extension_hashes=verify_ready(extension);receipt=json.loads((extension/'manifest.json').read_text(encoding='utf-8'))
    if receipt['parentHashes']!=parent_hashes:raise ValueError('Audited extension belongs to another source version')
    original=list(read_jsonl(parent/'corpus.jsonl'));by_id={r['documentId']:r for r in original};extra=[r for r in read_jsonl(extension/'candidates.jsonl') if r['eligibility']=='HELDOUT_CANDIDATE_AUDITED']
    links=[]
    for name in ('sourceClusterId','eventClusterId'):
        groups=defaultdict(list)
        for row in original:groups[row[name]].append(row['documentId'])
        for ids in groups.values():links.extend((ids[0],k) for k in ids[1:])
    for row in extra:
        if row['documentId'] in by_id or row['proposedSplit'] not in ('calibration','dev','final'):raise ValueError('Extension cannot add or relabel training parents')
        for old_id in row['relatedExistingSourceIds']:
            if by_id[old_id]['split']!=row['proposedSplit']:raise ValueError('Inherited family would cross partitions')
            links.append((row['documentId'],old_id))
        by_id[row['documentId']]={**row,'split':row['proposedSplit'],'legacyDocumentIds':[],
            'provenance':[{**row['provenance'],'url':row['url'],'school':'南京传媒学院'}]}
    # Also preserve links between newly recovered members of the same family.
    groups=defaultdict(list)
    for row in extra:groups[row['eventClusterId']].append(row['documentId'])
    for ids in groups.values():links.extend((ids[0],k) for k in ids[1:])
    assignment=cluster_splits({k:r['text'] for k,r in by_id.items()},links);seen=defaultdict(set)
    for key,row in by_id.items():
        if row['split']!='train':row.update(sourceClusterId=assignment[key]['sourceClusterId'],eventClusterId=assignment[key]['eventClusterId'])
        seen[row['eventClusterId']].add(row['split']);seen['source:'+row['sourceClusterId']].add(row['split'])
    if any(len(s)>1 for s in seen.values()):raise ValueError('Cross-split family after heldout extension')
    output.mkdir(parents=True)
    shutil.copy2(parent/'train.jsonl',output/'train.jsonl')
    rows=list(by_id.values())
    for name,values in [('corpus.jsonl',rows)]+[(split+'.jsonl',[r for r in rows if r['split']==split]) for split in ('calibration','dev','final')]:
        with (output/name).open('w',encoding='utf-8') as stream:
            for row in values:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest={'state':'HELDOUT_EXTENDED_TRAIN_BYTES_IDENTICAL','sourceCount':len(rows),'minimum5000SourcesMet':len(rows)>=5000,
        'sourceCounts':dict(Counter(r['split'] for r in rows)),'homeCampusCounts':dict(Counter(r['split'] for r in rows if r['institutionName']=='南京传媒学院')),
        'addedHeldoutSources':len(extra),'sourceTrainSha256':sha(output/'train.jsonl'),'originalTrainSha256':parent_hashes['train.jsonl'],
        'parentHashes':parent_hashes,'extensionHashes':extension_hashes,'trainingPlanChanged':False,'qualityAccepted':False,'algorithmSha256':sha(Path(__file__))}
    if manifest['sourceTrainSha256']!=manifest['originalTrainSha256']:raise ValueError('Training source bytes changed')
    write(output/'split-manifest.json',{'sources':{k:{name:r[name] for name in ('sourceClusterId','eventClusterId','split')} for k,r in by_id.items()}})
    write(output/'manifest.json',manifest);write(output/'READY',{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='READY'});print(json.dumps({k:v for k,v in manifest.items() if k not in ('parentHashes','extensionHashes')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--extension',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();extend(a.parent,a.extension,a.output)
