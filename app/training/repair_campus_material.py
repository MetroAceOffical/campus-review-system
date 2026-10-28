"""Re-extract cached evidence into a new immutable version, never move old held-out data into training."""
import argparse,hashlib,json,re,sqlite3,time
from collections import Counter,defaultdict
from pathlib import Path
from article_extraction import extract_article
from corpus import normalized,near_source_edges,cluster_splits,read_jsonl
from campus_partitions import event_edges
from construct_correspondence import verify_ready
ROOT=Path(__file__).resolve().parents[2]
PARTS=('train','calibration','dev','final')
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def lines(path,values):
    with path.open('w',encoding='utf-8') as stream:
        for row in values:stream.write(json.dumps(row,ensure_ascii=False)+'\n')

def inherited_split(legacy_splits,overlap,new_choice):
    values=set(legacy_splits)
    if len(values)>1:return 'QUARANTINE'
    if values:
        old=next(iter(values))
        return 'QUARANTINE' if overlap and old!='train' else old
    return 'train' if overlap else new_choice

def public_overlap(documents,output):
    """64-codepoint sentinels at stride8; anchor8 avoids hashing every training window."""
    anchors={}
    for key,text in documents.items():
        text=normalized(text);offsets=set(range(0,max(0,len(text)-63),8))
        if len(text)>=64:offsets.add(len(text)-64)
        for i in offsets:
            window=text[i:i+64];anchors.setdefault(window[:8],{}).setdefault(window,set()).add(key)
    flagged=set();counts=Counter();inputs={}
    selected=ROOT/'runtime/experiments/final-training-20261026/retriever-aux-v1/train-groups.json'
    for folder,selection in [(ROOT/'runtime/datasets/t2ranking-training-v1',None),(ROOT/'runtime/datasets/final-training-v1',selected)]:
        inputs[folder.name]=verify_ready(folder)
        allowed=None
        if selection:
            groups=json.loads(selection.read_text(encoding='utf-8'));allowed={k for g in groups for k in [g['queryId'],g['positiveId']]+g['negativeIds']};inputs['auxiliaryTrainingSelectionSha256']=sha(selection)
        db=sqlite3.connect(f'file:{(folder/"auxiliary.sqlite").as_posix()}?mode=ro',uri=True)
        try:
            for key,text in db.execute('SELECT id,text FROM documents'):
                if allowed is not None and key not in allowed:continue
                text=normalized(text);counts['publicBodiesScanned']+=1;counts['publicCodepointsScanned']+=len(text)
                for i in range(max(0,len(text)-63)):
                    possible=anchors.get(text[i:i+8])
                    if possible:flagged.update(possible.get(text[i:i+64],()))
                if counts['publicBodiesScanned']%5000==0:write(output/'status.json',{'stage':'PUBLIC_TRAINING_OVERLAP_SCAN',**counts,'flaggedSources':len(flagged),'neuralTrainingStarted':False})
        finally:db.close()
    return flagged,{'inputs':inputs,'counts':dict(counts),'flaggedIds':sorted(flagged),'rule':'64 normalized codepoint sentinels stride8; guaranteed >=71 contiguous overlap; not semantic-only decontamination'}

def rebuild(output):
    if (output/'READY').exists():raise RuntimeError('Version already frozen')
    if output.exists() and any(output.iterdir()):raise RuntimeError('Preserve partial output; use a fresh version')
    output.mkdir(parents=True);start=time.monotonic();parent=ROOT/'runtime/datasets/campus-partitions-20261026-v1';old_hashes=verify_ready(parent)
    old={r['documentId']:r for part in PARTS for r in read_jsonl(parent/(part+'.jsonl'))};url_ids=defaultdict(set)
    for key,row in old.items():
        for source in [row]+row.get('alternateSources',[]):
            if source.get('url'):url_ids[source['url']].add(key)
    canonical={};changes=[];exclusions=[];stats=Counter();input_receipts=[];seen_old=set()
    def add(row,legacy,receipt):
        text=row['text'].strip();title=row.get('title','').strip();stats['candidateRows']+=1
        if not title or not 200<=len(normalized(text))<=50000 or '\ufffd' in text or len(re.findall('[\u3400-\u9fff]',text))/max(1,len(text))<.15:
            exclusions.append({'url':row.get('url'),'legacyIds':sorted(legacy),'reason':'INVALID_BODY_OR_TITLE','characters':len(text)});return
        digest=hashlib.sha256(normalized(text).encode()).hexdigest();key='campus:'+digest
        provenance={k:row.get(k) for k in ('url','finalUrl','school','pageSha256','fetchedAt','publishedAt')};provenance['receipt']=receipt
        if key in canonical:
            target=canonical[key];target['provenance'].append(provenance);target['legacyDocumentIds']=sorted(set(target['legacyDocumentIds'])|legacy);stats['exactDuplicateCandidates']+=1
        else:
            canonical[key]={**row,'text':text,'title':title,'documentId':key,'normalizedBodySha256':digest,'institutionName':'南京传媒学院' if row['school'].startswith('南京传媒学院') else row['school'],'sourceClusterId':key,'legacyDocumentIds':sorted(legacy),'provenance':[provenance],'extractionVersion':row.get('extractionVersion','historical-public-text-cache'),'sizeBucket':'within_product_body_limit' if len(text)<=10000 else 'training_long_document'}
        for old_id in legacy:
            seen_old.add(old_id);before=old[old_id]['text'];changes.append({'oldId':old_id,'newId':key,'changed':before!=text,'beforeCharacters':len(before),'afterCharacters':len(text),'oldTextSha256':hashlib.sha256(before.encode()).hexdigest(),'newTextSha256':hashlib.sha256(text.encode()).hexdigest(),'nestedParagraphs':row.get('nestedParagraphs',0)})
    roots=[ROOT/'runtime/datasets/campus-final-v1',ROOT/'runtime/datasets/campus-extension-20261027-v1']
    for base in roots:
        for path in sorted(base.glob('*/crawl.sqlite')):
            db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True);payloads=db.execute('SELECT payload FROM articles ORDER BY url').fetchall();db.close()
            for (payload,) in payloads:
                row=json.loads(payload);file=path.parent/'pages'/(row['pageSha256']+'.html');legacy=set(url_ids.get(row['url'],()))
                if not file.is_file():exclusions.append({'url':row['url'],'legacyIds':sorted(legacy),'reason':'MISSING_CACHED_HTML'});continue
                if sha(file)!=row['pageSha256']:raise ValueError('Cached HTML checksum mismatch')
                result=extract_article(file.read_bytes(),row.get('finalUrl',row['url']))
                if result is None:exclusions.append({'url':row['url'],'legacyIds':sorted(legacy),'reason':'NO_ARTICLE_CONTAINER'});continue
                record={**row,**result};record['publishedAt']=result.get('publishedAt') or row.get('publishedAt');input_receipts.append({'path':file.relative_to(ROOT).as_posix(),'sha256':row['pageSha256']});add(record,legacy,input_receipts[-1])
            write(output/'status.json',{'stage':'REEXTRACTING','candidates':stats['candidateRows'],'uniqueBodies':len(canonical),'neuralTrainingStarted':False})
    # Historical public-interface text has a separate byte-verified source; no invented HTML recovery.
    for name in ['validation/remaining/text/data/reference_sources.jsonl','validation/text/campus/sources.jsonl']:
        source=ROOT/name;input_receipts.append({'path':name,'sha256':sha(source)})
        for row in read_jsonl(source):
            file=(source.parent/row['body_path']).resolve()
            if not file.is_relative_to(source.parent.resolve()) or sha(file)!=row['body_sha256']:raise ValueError('Historical body identity mismatch')
            add({'title':row['title'],'text':row['text'],'url':row['url'],'school':'南京传媒学院','publishedAt':row.get('published_at'),'historicalBodySha256':row['body_sha256']},set(url_ids.get(row['url'],())),{'path':file.relative_to(ROOT).as_posix(),'sha256':row['body_sha256']})
    rows=sorted(canonical.values(),key=lambda r:r['documentId']);lines(output/'candidate-corpus.jsonl',rows);lines(output/'changes.jsonl',changes);lines(output/'exclusions.jsonl',exclusions);write(output/'input-receipts.json',input_receipts)
    write(output/'status.json',{'stage':'GROUPING','uniqueBodies':len(rows),'neuralTrainingStarted':False})
    documents={r['documentId']:r['text'] for r in rows};near=near_source_edges(documents);events=event_edges(rows);source_edges=list(near);event_links=list(near)+events;by_source=defaultdict(list);by_event=defaultdict(list)
    for row in rows:
        for previous in row['legacyDocumentIds']:by_source[old[previous]['sourceClusterId']].append(row['documentId']);by_event[old[previous]['eventClusterId']].append(row['documentId'])
    for ids in by_source.values():source_edges.extend((ids[0],key) for key in ids[1:]);event_links.extend((ids[0],key) for key in ids[1:])
    for ids in by_event.values():event_links.extend((ids[0],key) for key in ids[1:])
    source_groups=cluster_splits(documents,source_edges);event_groups=cluster_splits(documents,event_links)
    flagged,overlap=public_overlap(documents,output);write(output/'public-overlap.json',overlap)
    components=defaultdict(list)
    for row in rows:components[event_groups[row['documentId']]['eventClusterId']].append(row)
    assignments={};quarantine=[]
    for group,values in components.items():
        old_splits={old[key]['split'] for row in values for key in row['legacyDocumentIds']};has_overlap=any(row['documentId'] in flagged or any(old[k].get('publicTrainingOverlap') for k in row['legacyDocumentIds']) for row in values);home=any(r['institutionName']=='南京传媒学院' for r in values);bucket=int(hashlib.sha256(f'20261026:campus:{group}'.encode()).hexdigest()[:8],16)%10000;ends=(4050,4500,6000) if home else (6300,7000,8000);choice='train' if bucket<ends[0] else 'calibration' if bucket<ends[1] else 'dev' if bucket<ends[2] else 'final';split=inherited_split(old_splits,has_overlap,choice)
        for row in values:
            assignment={'sourceClusterId':source_groups[row['documentId']]['sourceClusterId'],'eventClusterId':group,'split':split,'publicTrainingOverlap':has_overlap,'legacySplits':sorted(old_splits),'eventLabelOrigin':'conservative_automatic_grouping_not_human_gold'};row.update(assignment);assignments[row['documentId']]=assignment
            if split=='QUARANTINE':quarantine.append({**row,'qualityReason':'CROSS_LEGACY_PARTITIONS_OR_HELDOUT_PUBLIC_OVERLAP'})
    accepted=[r for r in rows if r['split'] in PARTS];lines(output/'corpus.jsonl',accepted);lines(output/'quarantine.jsonl',quarantine)
    for split in PARTS:lines(output/(split+'.jsonl'),(r for r in accepted if r['split']==split))
    summary={'state':'CORRECTED_SOURCE_PARTITIONS_READY','rawCandidateRows':stats['candidateRows'],'candidateUniqueBodies':len(rows),'acceptedSources':len(accepted),'sourceCount':len(accepted),'minimum5000SourcesMet':len(accepted)>=5000,'sourceCounts':dict(Counter(r['split'] for r in accepted)),'homeCampusCounts':dict(Counter(r['split'] for r in accepted if r['institutionName']=='南京传媒学院')),'eventGroups':{p:len({r['eventClusterId'] for r in accepted if r['split']==p}) for p in PARTS},'changedLegacyDocuments':len({r['oldId'] for r in changes if r['changed']}),'legacySourcesWithLineage':len(seen_old),'legacyMissingFromAcceptedOrQuarantine':sorted(set(old)-seen_old),'quarantinedSources':len(quarantine),'nearSourceEdges':len(near),'titleDateEdges':len(events),'candidateStatistics':dict(stats),'legacyPartitionHashes':old_hashes,'neuralTrainingStarted':False,'formalMaterialPrepared':False,'elapsedSeconds':round(time.monotonic()-start,3)}
    write(output/'split-manifest.json',{'summary':summary,'sources':assignments});write(output/'manifest.json',summary)
    if verify_ready(parent)!=old_hashes:raise ValueError('Old source partition files changed')
    write(output/'READY',{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name not in ('status.json','READY')});write(output/'status.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runtime/datasets'):raise ValueError('Output must stay in project datasets')
    rebuild(output)
