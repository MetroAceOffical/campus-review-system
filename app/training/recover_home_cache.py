"""Audit previously unused official API cache as heldout candidates; no downloads/training."""
import argparse,hashlib,json,re
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from html import escape
from article_extraction import extract_article
from corpus import normalized,read_jsonl,near_source_edges,cluster_splits
from campus_partitions import event_edges
from construct_correspondence import verify_ready
from repair_campus_material import public_overlap

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def recover(parent,output,raw_root=None):
    if output.exists():raise ValueError('Use a new recovery audit version')
    hashes=verify_ready(parent);originals=list(read_jsonl(parent/'corpus.jsonl'));by_url={p['url']:r for r in originals for p in [r]+r.get('provenance',[]) if p.get('url')};by_body={r['normalizedBodySha256']:r for r in originals}
    raw=raw_root or ROOT/'validation/remaining/text/data/raw';seen=set();candidates={};exclusions=[];receipts=[];stats=Counter()
    if raw_root:
        if not raw.resolve().is_relative_to(ROOT/'runtime/datasets'):raise ValueError('New API cache must stay in project datasets')
        verify_ready(raw.parent)
    for path in sorted(raw.glob('*-*.meta.json')):
        meta=json.loads(path.read_text(encoding='utf-8'));body=path.with_name(path.name.replace('.meta.json','.json'))
        if '/getArticleList.php?' not in meta.get('url',''):continue
        if sha(body)!=meta['sha256']:raise ValueError('Historical API cache changed')
        receipts.append({'path':body.relative_to(ROOT).as_posix(),'sha256':meta['sha256'],'retrievedAt':meta['retrieved_at']})
        payload=json.loads(body.read_text(encoding='utf-8'))
        if payload.get('code')!=0:raise ValueError('Historical API did not succeed')
        category=re.search(r'categoryid=([^&]+)',meta['url'])[1]
        for article in payload['data']['list']:
            key=article['uuid']
            if key in seen:continue
            seen.add(key);stats['uniqueCachedArticles']+=1
            url='https://www.cucn.edu.cn/XinWen/'+category+'/'+key
            if url in by_url:stats['alreadyRepresentedUrls']+=1;continue
            text=article.get('content','').replace('\u200b','')
            extracted=extract_article('<h1>'+escape(article['title'])+'</h1><article>'+text+'</article>',url)
            if not extracted or not 200<=len(normalized(extracted['text']))<=50000 or '\ufffd' in extracted['text']:
                exclusions.append({'url':url,'reason':'BODY_QUALITY'});continue
            digest=hashlib.sha256(normalized(extracted['text']).encode()).hexdigest()
            if digest in by_body:stats['alreadyRepresentedBodies']+=1;continue
            if digest in candidates:stats['duplicateUnusedBodies']+=1;continue
            publication=datetime.fromtimestamp(int(article['public_time'])/1000,timezone.utc).isoformat() if article.get('public_time') else None
            candidates[digest]={**extracted,'documentId':'campus:'+digest,'normalizedBodySha256':digest,'url':url,
                'publishedAt':publication,'institutionName':'南京传媒学院','school':'南京传媒学院','siteArticleId':key,
                'labelOrigin':'unknown','labelConfidence':'unknown','sourceClusterId':'campus:'+digest,'eventClusterId':'campus:'+digest,
                'provenance':receipts[-1],'extractionVersion':'cached-api-dom-once-zws-formatting-v1'}
    output.mkdir(parents=True);write(output/'status.json',{'state':'AUDITING_UNUSED_CACHE','candidateBodies':len(candidates),'neuralTrainingStarted':False})
    new=list(candidates.values());all_rows=originals+new;documents={r['documentId']:r['text'] for r in all_rows}
    links=near_source_edges(documents)+event_edges(all_rows)
    for field in ('sourceClusterId','eventClusterId'):
        groups=defaultdict(list)
        for row in originals:groups[row[field]].append(row['documentId'])
        for ids in groups.values():links.extend((ids[0],k) for k in ids[1:])
    # Preserve conservative relationships already recorded before any model work.
    old_ids={r['source_id']:by_url[r['url']]['documentId'] for name in ('validation/remaining/text/data/sources.jsonl','validation/text/campus/sources.jsonl') for r in read_jsonl(ROOT/name) if r['url'] in by_url}
    old_ids.update({'NCNEW-'+r['siteArticleId']:r['documentId'] for r in new})
    for row in read_jsonl(ROOT/'validation/remaining/text/data/dedup_review.jsonl'):
        if row['a'] in old_ids and row['b'] in old_ids:links.append((old_ids[row['a']],old_ids[row['b']]))
    assignment=cluster_splits(documents,links);components=defaultdict(list)
    for row in all_rows:components[assignment[row['documentId']]['eventClusterId']].append(row)
    flagged,public_receipt=public_overlap({r['documentId']:r['text'] for r in new},output)
    write(output/'public-overlap.json',public_receipt)
    old={r['documentId'] for r in originals};audit=[]
    historic={r['site_article_id']:r['split'] for r in read_jsonl(ROOT/'validation/remaining/text/data/sources.jsonl')}
    for component,values in components.items():
        existing={r['split'] for r in values if r['documentId'] in old};overlap=any(r['documentId'] in flagged or r.get('publicTrainingOverlap') for r in values)
        legacy={'dev' if historic.get(r.get('siteArticleId'))=='absent_dev' else 'final' for r in values if historic.get(r.get('siteArticleId')) in ('absent_dev','absent_test')}
        choices=existing|legacy
        for row in values:
            if row['documentId'] in old:continue
            bucket=int(hashlib.sha256(('20261028:heldout-only:'+component).encode()).hexdigest()[:8],16)%100
            split=next(iter(choices)) if len(choices)==1 else 'calibration' if bucket<10 else 'dev' if bucket<30 else 'final'
            reason='PUBLIC_TRAINING_OVERLAP' if overlap else 'RELATED_TO_NEURAL_TRAIN' if 'train' in choices else 'CROSS_HELDOUT_BOUNDARIES' if len(choices)>1 else None
            audit.append({**row,'eventClusterId':component,'proposedSplit':split if reason is None else None,
                'eligibility':'HELDOUT_CANDIDATE_AUDITED' if reason is None else 'QUARANTINE','reason':reason,
                'knownRelatedSplits':sorted(choices),'relatedExistingSourceIds':sorted(r['documentId'] for r in values if r['documentId'] in old),
                'historicalSplit':historic.get(row['siteArticleId']),'humanGold':False,'notInCurrentTrainingPlan':True})
    for name,rows in [('candidates.jsonl',audit),('exclusions.jsonl',exclusions)]:
        with (output/name).open('w',encoding='utf-8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest={'state':'UNUSED_HOME_CACHE_AUDITED_NOT_YET_MERGED','statistics':dict(stats),'newCandidateBodies':len(audit),
        'eligibleHeldoutCandidates':sum(r['eligibility']=='HELDOUT_CANDIDATE_AUDITED' for r in audit),
        'eligibleBySplit':dict(Counter(r['proposedSplit'] for r in audit if r['proposedSplit'])),
        'quarantineReasons':dict(Counter(r['reason'] for r in audit if r['reason'])),'rawReceipts':receipts,
        'parentHashes':hashes,'algorithmSha256':sha(Path(__file__)),'trainingInputsChanged':False,'fullHomeCoverageMet':False,
        'newNetworkDownloads':0,'neuralTrainingStarted':False}
    write(output/'manifest.json',manifest);write(output/'READY',{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name not in ('READY','status.json')});write(output/'status.json',manifest)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('rawReceipts','parentHashes')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--raw-root',type=Path);a=p.parse_args()
    if not a.output.resolve().is_relative_to(ROOT/'runtime/datasets'):raise ValueError('Use project output')
    recover(a.parent,a.output,a.raw_root)
