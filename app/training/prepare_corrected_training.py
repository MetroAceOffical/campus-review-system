"""Map only provable old ranges to corrected training parents; preserve all old files."""
import argparse,hashlib,json,re,sqlite3,time,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
from corpus import normalized,read_jsonl
from construct_correspondence import verify_ready,rewrite_checks,source_segments,selected_sources
from prepare_correspondence import generated_pairs
from negative_basis import assess_difference,RULE_VERSION
ROOT=Path(__file__).resolve().parents[2]
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def freeze(folder):write(folder/'READY',{p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file() and p.name not in ('READY','status.json')})
def remap_span(old_text,new_text,start,end):
    if not 0<=start<end<=len(old_text):return None
    needle=normalized(old_text[start:end]);canonical=[];positions=[]
    for offset,char in enumerate(new_text):
        for c in unicodedata.normalize('NFKC',char):
            if not c.isspace():canonical.append(c);positions.append(offset)
    haystack=''.join(canonical)
    if haystack!=normalized(new_text) or not needle:return None
    left=haystack.find(needle)
    if left<0 or haystack.find(needle,left+1)>=0:return None
    a,b=positions[left],positions[left+len(needle)-1]+1
    return (a,b) if normalized(new_text[a:b])==needle else None

def prepare(corpus,output,web_run=None):
    if output.exists():raise ValueError('Use a new training preparation version')
    output.mkdir(parents=True);partition_hashes=verify_ready(corpus);old_hashes=verify_ready(ROOT/'runtime/datasets/campus-partitions-20261026-v1');negative_hashes=verify_ready(ROOT/'runtime/datasets/campus-supported-negatives-v4')
    parents={r['documentId']:r for r in read_jsonl(corpus/'train.jsonl')};old={r['documentId']:r for r in read_jsonl(ROOT/'runtime/datasets/campus-partitions-20261026-v1/train.jsonl')};mapping=defaultdict(list)
    for parent in parents.values():
        for previous in parent['legacyDocumentIds']:mapping[previous].append(parent)
    stats=Counter();records=[];seen=set();proofs=[]
    def mapped(previous,start,end):
        if previous not in old:return None
        matches=[]
        for parent in mapping.get(previous,[]):
            span=remap_span(old[previous]['text'],parent['text'],start,end)
            if span:matches.append((parent,*span))
        return matches[0] if len(matches)==1 else None
    def consider(previous,start,end,query,evidence):
        stats['generationCandidates']+=1;match=mapped(previous,start,end)
        if not match:stats['unmappableOrAmbiguousGenerationRanges']+=1;return
        parent,a,b=match;source=parent['text'][a:b];entities=[parent['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',source);checks=rewrite_checks(source,query,entities,require_rewording=True)
        if not checks['accepted']:
            stats['generationRejectedByCurrentStrictRules']+=1
            for reason in checks['reasons']:stats['generationRejected:'+reason]+=1
            return
        key=(parent['documentId'],a,b,normalized(query))
        if key in seen:stats['duplicateGenerationOutputs']+=1;return
        seen.add(key);records.append({'sourceIds':[parent['documentId']],'source':source,'query':query,'sourceOffsets':{'start':a,'end':b},'checks':checks,'generatorRevision':'aa8e72537993ba99e69dfaafa59ed015b17504d1','remappedFrom':evidence,'split':'train'});stats['strictReusableParagraphs']+=1
    snapshots=output/'snapshots';snapshots.mkdir()
    for folder in sorted((ROOT/'runtime/experiments/final-training-20261026').glob('campus-generation-v*')):
        if not (folder/'generation.sqlite').is_file():continue
        if json.loads((folder/'config.json').read_text(encoding='utf-8'))['partitionTrainSha256']!=old_hashes['train.jsonl']:raise ValueError('Historical generation source partition differs')
        target=snapshots/(folder.name+'.sqlite');source=sqlite3.connect(f'file:{(folder/"generation.sqlite").as_posix()}?mode=ro',uri=True);snapshot=sqlite3.connect(target);source.backup(snapshot);source.close()
        proofs.append({'source':str(folder.relative_to(ROOT)),'snapshotSha256':sha(target),'configSha256':sha(folder/'config.json')})
        for previous,start,end,query in snapshot.execute("SELECT parent_id,start,end,result FROM segments WHERE state='ACCEPTED' AND result IS NOT NULL"):
            consider(previous,start,end,query,{'snapshot':target.name,'oldParentId':previous,'oldStart':start,'oldEnd':end})
        snapshot.close()
    if web_run:
        folder=ROOT/'runtime/workbench/computations'/web_run;source=sqlite3.connect(f'file:{(folder/"generation.sqlite").as_posix()}?mode=ro',uri=True);target=snapshots/'web-training-news.sqlite';snapshot=sqlite3.connect(target);source.backup(snapshot);source.close();proofs.append({'source':str(folder.relative_to(ROOT)),'snapshotSha256':sha(target),'kind':'partial committed snapshot, not completed Web generation'})
        config=json.loads((folder/'config.json').read_text(encoding='utf-8'));web_parents={r['id']:r['text'] for r in read_jsonl(Path(config['input']))};proofs[-1]['inputSha256']=sha(config['input'])
        for previous,start,end,query in snapshot.execute("SELECT source_id,start,end,result FROM segment WHERE state='ACCEPTED' AND result IS NOT NULL"):
            if previous not in old or previous not in web_parents or web_parents[previous][start:end]!=old[previous]['text'][start:end]:stats['webSourceSnapshotMismatch']+=1;continue
            consider(previous,start,end,query,{'snapshot':target.name,'oldParentId':previous,'oldStart':start,'oldEnd':end})
        snapshot.close()
    with (output/'reusable-paragraphs.jsonl').open('w',encoding='utf-8') as stream:
        for row in records:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'runtime/experiments/route-b-development-20261026/model',local_files_only=True,trust_remote_code=False,use_fast=True)
    classes=Counter();pair_seen={};pair_rows={};conflicts=set();events=set();sources=set();negatives=[]
    with (output/'bootstrap-pairs.jsonl').open('w',encoding='utf-8') as stream:
        def emit(row):
            key=tuple(sorted((normalized(row['query']),normalized(row['source']))))
            if key in pair_seen:
                if pair_seen[key]!=row['target']:conflicts.add(key)
                else:stats['duplicatePairsExcluded']+=1
                return
            if len(tokenizer(row['query'],row['source'],truncation=False)['input_ids'])>512:stats['jointTokenBudgetExceeded']+=1;return
            pair_seen[key]=row['target'];pair_rows[key]=row;row['pairId']=hashlib.sha256('\0'.join(key).encode()).hexdigest()
        for row in generated_pairs(parents,records,tokenizer,stats):
            if row['transformationKind']=='COPY_CONTROL':stats['copyLikeQuerySlicesExcluded']+=1;continue
            emit(row)
        for candidate in read_jsonl(ROOT/'runtime/datasets/campus-supported-negatives-v4/negative-pairs.jsonl'):
            left=candidate['positiveSource'];right=candidate['candidateSource'];a=mapped(left['sourceId'],left['start'],left['end']);b=mapped(right['sourceId'],right['start'],right['end'])
            if not a or not b:stats['unmappableNegativeRanges']+=1;continue
            def side(match):
                parent,start,end=match
                return {'sourceId':parent['documentId'],'text':parent['text'][start:end],'start':start,'end':end,**{k:parent.get(k) for k in ['sourceClusterId','eventClusterId','title','institutionName','publishedAt']}}
            a,b=side(a),side(b);basis=assess_difference(a,b)
            if a['eventClusterId']==b['eventClusterId'] or a['sourceClusterId']==b['sourceClusterId'] or not basis['supported']:stats['negativeBasisNoLongerSupported']+=1;continue
            row={**candidate,'query':a['text'],'source':b['text'],'sourceIds':[b['sourceId']],'sourceClusterId':b['sourceClusterId'],'eventClusterId':a['eventClusterId'],'sourceOffsets':{'start':b['start'],'end':b['end']},'positiveSource':a,'candidateSource':b,'negativeBasis':basis,'remappedFromPairId':candidate['pairId']};negatives.append(row);emit(row)
        stats['conflictingPairFamiliesQuarantined']=len(conflicts)
        for key,row in pair_rows.items():
            if key in conflicts:continue
            classes[row['target']]+=1;events.add(row['eventClusterId']);sources.update(row['sourceIds']);stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output/'remapped-negatives.jsonl').open('w',encoding='utf-8') as stream:
        for row in negatives:
            if tuple(sorted((normalized(row['query']),normalized(row['source'])))) not in conflicts:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    selected=selected_sources(list(parents.values()),len(parents));plan=[];by_range=defaultdict(list)
    for row in records:by_range[(row['sourceIds'][0],row['sourceOffsets']['start'],row['sourceOffsets']['end'])].append(row)
    seed=output/'generation-seed';seed.mkdir();db=sqlite3.connect(seed/'generation.sqlite');db.executescript('CREATE TABLE segments(id TEXT PRIMARY KEY,parent_id TEXT,start INT,end INT,state TEXT,result TEXT,checks TEXT,attempts INT);CREATE TABLE attempts(id INTEGER PRIMARY KEY,segment_id TEXT,attempt_no INT,output TEXT,checks TEXT,seconds REAL);')
    for parent in selected:
        for span in source_segments(parent['text']):
            key=(parent['documentId'],span['sourceStart'],span['sourceEnd']);reuse=by_range.get(key,[]);plan.append({'parentId':key[0],'start':key[1],'end':key[2],'reusable':bool(reuse)})
            if reuse:
                row=reuse[0];sid=hashlib.sha256(str(key).encode()).hexdigest();db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(sid,*key,'ACCEPTED',row['query'],json.dumps(row['checks']),0))
    db.commit();db.close();write(seed/'config.json',{'partitionTrainSha256':partition_hashes['train.jsonl'],'generatorRevision':'aa8e72537993ba99e69dfaafa59ed015b17504d1','provenance':'strictly rechecked exact-normalized range remapping; no old offsets inherited'})
    with (output/'generation-plan.jsonl').open('w',encoding='utf-8') as stream:
        for row in plan:stream.write(json.dumps(row)+'\n')
    manifest={'state':'BOOTSTRAP_MATERIAL_AND_GENERATION_PLAN_PREPARED','statistics':dict(stats),'pairCount':sum(classes.values()),'classCounts':dict(classes),'sourceParents':len(sources),'eventGroups':len(events),'plannedOriginals':len(selected),'originalMinimum1200Met':len(selected)>=1200,'plannedSegments':len(plan),'reusablePlannedSegments':sum(r['reusable'] for r in plan),'remainingGenerationSegments':sum(not r['reusable'] for r in plan),'formalCorrespondenceMinimum':20000,'formalRetrievalMinimum':1000,'bgeEpochs':2,'m3Epochs':2,'formalScaleAndBalanceReady':False,'neuralTrainingStarted':False,'partitionHashes':partition_hashes,'sourceSnapshots':proofs,'algorithmHashes':{name:sha(ROOT/'app/training'/name) for name in ['prepare_corrected_training.py','article_extraction.py','repair_campus_material.py','negative_basis.py','construct_correspondence.py']},'scope':'bootstrap is not formal training-ready; no copy/control or reversed duplicate count padding'};write(output/'manifest.json',manifest);freeze(output);print(json.dumps({k:v for k,v in manifest.items() if k not in ('partitionHashes','sourceSnapshots','algorithmHashes')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--web-run');a=p.parse_args()
    for path in (a.corpus,a.output):
        if not path.resolve().is_relative_to(ROOT/'runtime'):raise ValueError('Use project runtime paths')
    prepare(a.corpus,a.output,a.web_run)
