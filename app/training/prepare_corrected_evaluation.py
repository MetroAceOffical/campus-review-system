"""Rebuild heldout protocol from corrected sources and re-extracted natural evidence."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from article_extraction import extract_article
from corpus import normalized,read_jsonl
from construct_correspondence import verify_ready
from prepare_text_protocol import build_protocol,TARGETS

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def lines(path,rows):
    with path.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def prepare(partitions,natural,output):
    if output.exists() or not output.resolve().is_relative_to(ROOT/'runtime/datasets'):raise ValueError('Use a new project protocol version')
    partition_hashes=verify_ready(partitions);natural_hashes=verify_ready(natural)
    parents=list(read_jsonl(partitions/'corpus.jsonl'));mapping=defaultdict(list)
    for parent in parents:
        for old in parent['legacyDocumentIds']:mapping[old].append(parent)
    pages={p.stem:p for base in ('campus-final-v1','campus-extension-20261027-v1') for p in (ROOT/'runtime/datasets'/base).glob('*/pages/*.html')}
    accepted=[];excluded=[]
    for row in read_jsonl(natural/'relations.jsonl'):
        matches=mapping.get(row['sourceIds'][0],[])
        if len(matches)!=1 or matches[0]['split']!=row['split']:
            excluded.append({'relationId':row['relationId'],'reason':'PARENT_MISSING_AMBIGUOUS_OR_QUARANTINED'});continue
        parent=matches[0];page=pages.get(row['queryPageSha256'])
        if not page or sha(page)!=row['queryPageSha256']:
            excluded.append({'relationId':row['relationId'],'reason':'MISSING_VERIFIABLE_NATURAL_QUERY_PAGE'});continue
        extracted=extract_article(page.read_bytes(),row['queryUrl'])
        if not extracted or normalized(extracted['text'])!=normalized(parent['text']):
            excluded.append({'relationId':row['relationId'],'reason':'CORRECTED_NATURAL_BODY_DIFFERS'});continue
        accepted.append({**row,'sourceIds':[parent['documentId']],'source':parent['text'],'query':extracted['text'],
            'sourceClusterId':parent['sourceClusterId'],'eventClusterId':parent['eventClusterId'],
            'sourceOffsets':{'start':0,'end':len(parent['text'])},'queryOffsets':{'start':0,'end':len(extracted['text'])},
            'contentProof':{'accepted':True,'relationType':'NORMALIZED_EXACT_CONTENT_DISTINCT_PUBLICATION_RECORDS',
                'queryPageSha256Reverified':row['queryPageSha256'],'correctedSourceBodySha256':sha_text(parent['text']),
                'extractorSha256':sha(ROOT/'app/training/article_extraction.py'),'semanticParaphraseClaim':False}})
    result=build_protocol({split:[r for r in parents if r['split']==split] for split in TARGETS},accepted,seed=20261028)
    references=[{'sourceRevisionId':r['documentId'],'sourceWorkId':r['documentId'],'sourceKey':'BODY','manuscriptId':'reference:'+r['documentId'],
        'title':r['title'],'text':r['text'],'url':r['url'],'sourceSplit':r['split'],'sourceClusterId':r['sourceClusterId'],
        'eventClusterId':r['eventClusterId'],'institutionName':r['institutionName']} for r in parents]
    output.mkdir(parents=True)
    for name,rows in [('construction-plan.jsonl',result['plans']),('queries.jsonl',result['queries']),('references.jsonl',references),('natural-relations.jsonl',accepted),('natural-exclusions.jsonl',excluded)]:lines(output/name,rows)
    manifest={**result['summary'],'targetsBySplit':TARGETS,'partitionHashes':partition_hashes,'oldNaturalHashes':natural_hashes,
        'naturalRelationsRevalidated':len(accepted),'naturalRelationsExcluded':len(excluded),'referenceFields':len(references),
        'algorithmHashes':{name:sha(ROOT/'app/training'/name) for name in ('prepare_corrected_evaluation.py','prepare_text_protocol.py','article_extraction.py')},
        'oldProtocolChanged':False,'finalProtocolExecuted':False,'qualityAccepted':False}
    write(output/'manifest.json',manifest);write(output/'READY',{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='READY'})
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('partitionHashes','oldNaturalHashes','algorithmHashes')},ensure_ascii=False),flush=True)


def sha_text(value):return hashlib.sha256(value.encode()).hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--partitions',type=Path,required=True);p.add_argument('--natural',type=Path,default=ROOT/'runtime/datasets/campus-natural-relations-v1');p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.partitions,a.natural,a.output)
