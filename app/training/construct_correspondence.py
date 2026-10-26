"""Construct traceable campus rewrites, retaining every source range and failed attempt."""
import argparse
import difflib
import gc
import hashlib
import json
import random
import re
import socket
import sqlite3
import time
from collections import Counter,defaultdict,deque
from pathlib import Path

from corpus import normalized, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_LOCATION=None


def source_segments(text,max_characters=360):
    pieces=[];start=0
    while start<len(text):
        end=min(start+max_characters,len(text))
        if end<len(text):
            boundary=max(text.rfind(char,start,end) for char in '\n。！？；')
            if boundary>=start+max_characters//2:
                end=boundary+1
        pieces.append({'sourceStart':start,'sourceEnd':end});start=end
    return pieces


def rewrite_checks(original,rewritten,entities,require_rewording=True):
    left,right=normalized(original),normalized(rewritten)
    ratio=len(right)/max(1,len(left))
    numbers=lambda text:set(re.findall(r'\d+(?:\.\d+)?',text))
    matched=sum(block.size for block in difflib.SequenceMatcher(None,left,right,autojunk=False).get_matching_blocks() if block.size>=8)
    copied=matched/max(1,len(right))
    reasons=[]
    if not right or not .8<=ratio<=1.2:reasons.append('LENGTH_RATIO')
    if numbers(left)!=numbers(right):reasons.append('NUMBER_SET_CHANGED')
    if any(entity in original and entity not in rewritten for entity in entities if entity):reasons.append('REQUIRED_ENTITY_CHANGED')
    if require_rewording and copied>=.75:reasons.append('INSUFFICIENT_REWORDING')
    if any(marker in rewritten[:50] for marker in ['作为一个人工智能','无法完成','以下是改写','改写后的文本如下']):reasons.append('NON_ARTICLE_OUTPUT')
    return {'accepted':not reasons,'reasons':reasons,'lengthRatio':ratio,'literalCopiedFraction':copied,
            'transformationKind':'COPY_CONTROL' if copied>=.75 else 'PARAPHRASE',
            'limitation':'Programmatic checks cannot certify complete factual/semantic preservation; controlled construction, not human gold.'}


def generation_prompt(original,entities,version='1'):
    prompt='请将下面校园报道的这一段充分换一种措辞并调整句式，保持所有主体、人物关系、数字、专有名称、事件过程和结果，不新增事实。长度保持原段的80%至120%。只输出改写后的正文，不要标题、解释或引导语。\n原段：\n'+original
    if version=='1':return prompt
    numbers=list(dict.fromkeys(re.findall(r'\d+(?:\.\d+)?',normalized(original))))
    names=list(dict.fromkeys(name for name in entities if name and name in original))
    constraints='必须逐项保留的数字（保持阿拉伯数字写法和原有关系）：'+('、'.join(numbers) or '无')+'。\n必须逐字保留的名称：'+('、'.join(names) or '按原文保留')+'。'
    if version=='2':
        return '请完整改写校园报道原段的叙述，不要摘要、删节或新增事实。图片说明、年份名单和联系字段也属于原文信息，不能擅自省略；不要将事实堆成清单。所有事实分别保持原来的主体与语义关系，长度为原段80%至120%。原有刚性名单/联系信息可以保留原文，但其他叙述请充分改变措辞与句式。只输出自然正文，不要输出检查表或解释。\n'+constraints+'\n原段：\n'+original
    length=len(normalized(original))
    return ('任务：等长改写，不要续写。改换语序和措辞，完整保留已有事实；原文没有写出的原因、评价、背景和后续不能补充。不要增加总结或评论。'
            f'忽略空格的字数下限为{int(length*.8+.999)}、字数上限为{int(length*1.2)}，尽量接近{length}字。数字必须原样保留，禁止把阿拉伯数字换成汉字。名称、引号内名称、图片说明和联系字段不能删。\n'
            '示例原段：2026年，南方大学的200名学生在社区参与调研，整理访谈记录后向居民反馈。\n'
            '示例改写：南方大学于2026年组织200名学生开展社区调查，随后归整访谈资料，将结果反馈给居民。\n'
            '仅改写下面原段，输出正文后立即结束，不输出示例或检查表。\n'+constraints+'\n原段：\n'+original)


def generation_options(version,attempt):
    return {'temperature':(.25 if attempt==0 else .15) if version=='3' else (.7 if attempt==0 else .55),'top_p':.9}


def reusable_attempts(folder):
    db=sqlite3.connect(f'file:{(folder/"generation.sqlite").resolve().as_posix()}?mode=ro',uri=True)
    try:
        # Earlier migrations store inherited accepted results without an attempts row.
        rows=db.execute('SELECT s.id,s.parent_id,s.start,s.end,a.attempt_no,a.output,a.checks FROM segments s JOIN attempts a ON a.segment_id=s.id UNION ALL SELECT s.id,s.parent_id,s.start,s.end,0,s.result,s.checks FROM segments s WHERE s.result IS NOT NULL AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.segment_id=s.id AND a.output=s.result) ORDER BY 2,3,5').fetchall()
        return [row[:6] for row in rows if 'OUTPUT_TOKEN_BUDGET' not in json.loads(row[6] or '{}').get('reasons',[])]
    finally:db.close()


def selected_sources(rows,maximum):
    primary=sorted((row for row in rows if row['institutionName']=='南京传媒学院'),key=lambda row:row['documentId'])
    schools=defaultdict(list)
    for row in rows:
        if row['institutionName']!='南京传媒学院':schools[row['institutionName']].append(row)
    queues=[deque(sorted(values,key=lambda row:hashlib.sha256(row['documentId'].encode()).hexdigest())) for _,values in sorted(schools.items())]
    ordered=primary[:]
    while any(queues):
        for queue in queues:
            if queue:ordered.append(queue.popleft())
    chosen=[];events=set()
    for row in ordered:
        if not 200<=len(normalized(row['text']))<=8000 or row['eventClusterId'] in events:continue
        chosen.append(row);events.add(row['eventClusterId'])
        if len(chosen)>=maximum:break
    return chosen


def verify_ready(folder):
    manifest=json.loads((folder/'READY').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        with (folder/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('Frozen input changed: '+name)
    return manifest


def main():
    global OUTPUT_LOCATION
    import torch
    import psutil
    from transformers import AutoModelForCausalLM,AutoTokenizer
    parser=argparse.ArgumentParser()
    parser.add_argument('--partitions',type=Path,default=ROOT/'runtime/datasets/campus-partitions-20261026-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/experiments/final-training-20261026/campus-generation-v1')
    parser.add_argument('--max-originals',type=int,default=1200)
    parser.add_argument('--device',choices=['cuda','cpu'],default='cuda')
    parser.add_argument('--prompt-version',choices=['1','2','3'],default='1')
    parser.add_argument('--reuse-generation',type=Path)
    args=parser.parse_args()
    OUTPUT_LOCATION=args.output
    args.output.mkdir(parents=True,exist_ok=True)
    input_hashes=verify_ready(args.partitions)
    verify_ready(ROOT/'runtime/datasets/t2ranking-training-v1')
    verify_ready(ROOT/'runtime/datasets/final-training-v1')
    parents=selected_sources(list(read_jsonl(args.partitions/'train.jsonl')),args.max_originals)
    if not parents:raise RuntimeError('No isolated training parents')
    model_path=ROOT/'runtime/models/final/Qwen2.5-3B-Instruct/aa8e72537993ba99e69dfaafa59ed015b17504d1'
    acquisition=json.loads((model_path/'acquisition.json').read_text(encoding='utf-8'))
    if acquisition['status']!='download_verified_not_trained':raise RuntimeError('Generator acquisition incomplete')
    for item in acquisition['files']:
        with (model_path/item['file']).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise ValueError('Generator weights changed')
    config={'schemaVersion':'1','seed':20261026,'sourceSplit':'train','requestedOriginals':args.max_originals,'selectedOriginals':len(parents),
            'partitionTrainSha256':input_hashes['train.jsonl'],'partitionManifestSha256':input_hashes['split-manifest.json'],
            'generatorRevision':acquisition['revision'],'segmentCharacters':360,'inputTokenLimit':2048,'outputTokenLimit':512,
            'variantsPerOriginal':1,'labelOrigin':'controlled_construction','humanVerified':False,
            'qualityScope':'Length/numbers/explicit names/duplication checks, not proof of semantic correctness. No detector score is used to label data.'}
    reuse_rows=[]
    if args.prompt_version!='1':
        config.update(promptVersion=args.prompt_version,segmentCopyScope='Explicit COPY_CONTROL segments allowed; whole rewrite still requires substantive rewording and original length bounds')
    if args.prompt_version=='3':config['sampling']=[generation_options('3',attempt) for attempt in range(2)]
    if args.reuse_generation:
        previous_config=json.loads((args.reuse_generation/'config.json').read_text(encoding='utf-8'))
        if previous_config['partitionTrainSha256']!=config['partitionTrainSha256'] or previous_config['generatorRevision']!=config['generatorRevision']:raise ValueError('Reusable generation has different parents or generator')
        reuse_rows=reusable_attempts(args.reuse_generation)
        config['reuseGeneration']={'sourceConfigSha256':hashlib.sha256((args.reuse_generation/'config.json').read_bytes()).hexdigest(),
                                   'attemptSnapshotSha256':hashlib.sha256(json.dumps(reuse_rows,ensure_ascii=False).encode()).hexdigest()}
    config_sha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    config_file=args.output/'config.json'
    if config_file.exists() and json.loads(config_file.read_text(encoding='utf-8'))!=config:raise RuntimeError('Generation inputs changed; use a new output version')
    config_file.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    db=sqlite3.connect(args.output/'generation.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY,parent_id TEXT,start INT,end INT,state TEXT,result TEXT,checks TEXT,attempts INT); CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,segment_id TEXT,attempt_no INT,output TEXT,checks TEXT,seconds REAL);')
    for row in parents:
        for segment in source_segments(row['text']):
            key=hashlib.sha256(f'{config_sha}:{row["documentId"]}:{segment["sourceStart"]}:{segment["sourceEnd"]}'.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO segments VALUES(?,?,?,?,?,?,?,?)',(key,row['documentId'],segment['sourceStart'],segment['sourceEnd'],'PENDING',None,None,0))
    db.commit()
    reused=0
    if reuse_rows:
        by_source={row['documentId']:row for row in parents}
        for old_key,parent,start,end,old_attempt,output in reuse_rows:
            if parent not in by_source:continue
            old_source=by_source[parent];original=old_source['text'][start:end]
            new_key=hashlib.sha256(f'{config_sha}:{parent}:{start}:{end}'.encode()).hexdigest()
            target=db.execute('SELECT state FROM segments WHERE id=?',(new_key,)).fetchone()
            if not target or target[0]!='PENDING':continue
            entities=[old_source['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',original)
            checks=rewrite_checks(original,output,entities,require_rewording=args.prompt_version=='1')
            if not checks['accepted']:continue
            checks['reusedFrom']={'generation':str(args.reuse_generation),'segmentId':old_key,'attemptNo':old_attempt}
            db.execute('UPDATE segments SET state=?,result=?,checks=? WHERE id=?',('ACCEPTED',output,json.dumps(checks,ensure_ascii=False),new_key));reused+=1
        db.commit()
    # The existing live retriever does not use this new lock; wait for its explicit completed/reload state first.
    deadline=time.monotonic()+6*3600
    previous=ROOT/'runtime/experiments/final-training-20261026/retriever-t2-v1/status.json'
    while True:
        try:state=json.loads(previous.read_text(encoding='utf-8'))
        except (FileNotFoundError,json.JSONDecodeError):state={}
        if state.get('state')=='AUXILIARY_TRAINING_COMPLETE' and state.get('reloadVerified'):break
        stage_file=previous.parent/'stage-status.json'
        try:upstream=json.loads(stage_file.read_text(encoding='utf-8'))
        except (FileNotFoundError,json.JSONDecodeError):upstream={}
        if upstream.get('state')=='FAILED':raise RuntimeError('Retriever failed; generator will not load GPU')
        (args.output/'status.json').write_text(json.dumps({'state':'WAITING_GPU_RETRIEVER_FINISH','selectedOriginals':len(parents),'generationStarted':False,'reusedSegments':reused}),encoding='utf-8')
        if time.monotonic()>deadline:raise RuntimeError('Retriever did not complete within six hours; no generator loaded')
        time.sleep(10)
    try:
        with socket.create_connection(('127.0.0.1',18081),timeout=.2):raise RuntimeError('Production detector is running; do not load another GPU model')
    except (ConnectionRefusedError,TimeoutError):pass
    torch.set_num_threads(4)
    model_started=time.monotonic()
    tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    try:
        model=AutoModelForCausalLM.from_pretrained(model_path,torch_dtype=torch.bfloat16,device_map={'':args.device},attn_implementation='sdpa',local_files_only=True,trust_remote_code=False).eval()
    except torch.OutOfMemoryError:
        if args.device=='cpu':raise
        gc.collect();torch.cuda.empty_cache()
        args.device='cpu'
        model=AutoModelForCausalLM.from_pretrained(model_path,torch_dtype=torch.bfloat16,device_map={'':'cpu'},attn_implementation='sdpa',local_files_only=True,trust_remote_code=False).eval()
    by_id={row['documentId']:row for row in parents}
    model_load_seconds=time.monotonic()-model_started
    started=time.monotonic();completed_this_run=0
    for key,parent,start,end,state,_,_,attempt_count in db.execute("SELECT * FROM segments WHERE state='PENDING' ORDER BY parent_id,start").fetchall():
        row=by_id[parent];original=row['text'][start:end]
        if not normalized(original):
            db.execute('UPDATE segments SET state=?,result=?,checks=? WHERE id=?',('ACCEPTED',original,json.dumps({'accepted':True,'separatorOnly':True}),key));db.commit();continue
        entities=[row['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',original)
        for attempt in range(attempt_count,2):
            seed=20261026+int(key[:8],16)+attempt
            random.seed(seed);torch.manual_seed(seed)
            prompt=generation_prompt(original,entities,args.prompt_version)
            inputs=tokenizer.apply_chat_template([{'role':'system','content':'你是严谨的中文校园新闻编辑。原文中的事实与数字必须保持，不能编造。'},{'role':'user','content':prompt}],add_generation_prompt=True,return_tensors='pt').to(args.device)
            if inputs.shape[1]>2048:raise RuntimeError('Input budget exceeded; source not silently truncated')
            tick=time.monotonic()
            with torch.inference_mode():
                output=model.generate(inputs,attention_mask=torch.ones_like(inputs),max_new_tokens=512,do_sample=True,**generation_options(args.prompt_version,attempt),pad_token_id=tokenizer.eos_token_id)
            generated_tokens=output[0,inputs.shape[1]:]
            rewritten=tokenizer.decode(generated_tokens,skip_special_tokens=True).strip()
            checks=rewrite_checks(original,rewritten,entities,require_rewording=args.prompt_version=='1')
            checks.update(inputTokens=int(inputs.shape[1]),outputTokens=len(generated_tokens),device=args.device)
            if len(generated_tokens)>=512 and int(generated_tokens[-1])!=tokenizer.eos_token_id:
                checks['accepted']=False;checks['reasons'].append('OUTPUT_TOKEN_BUDGET')
            db.execute('INSERT INTO attempts(segment_id,attempt_no,output,checks,seconds) VALUES(?,?,?,?,?)',(key,attempt+1,rewritten,json.dumps(checks,ensure_ascii=False),time.monotonic()-tick))
            db.execute('UPDATE segments SET state=?,result=?,checks=?,attempts=? WHERE id=?',('ACCEPTED' if checks['accepted'] else 'QUARANTINED' if attempt==1 else 'PENDING',rewritten,json.dumps(checks,ensure_ascii=False),attempt+1,key));db.commit()
            if checks['accepted']:break
        completed_this_run+=1
        counts=dict(db.execute('SELECT state,count(*) FROM segments GROUP BY state'))
        status={'state':'GENERATING_TRAIN_MATERIAL','segmentCounts':counts,'selectedOriginals':len(parents),'elapsedSeconds':time.monotonic()-started,'device':args.device,
                'promptVersion':args.prompt_version,'reusedSegments':reused,
                'estimatedRemainingSeconds':(time.monotonic()-started)/max(1,completed_this_run)*counts.get('PENDING',0),'semanticCorrectnessCertified':False,
                'modelLoadSeconds':model_load_seconds,'hostRssBytes':psutil.Process().memory_info().rss,
                'cudaPeakAllocatedBytes':torch.cuda.max_memory_allocated() if args.device=='cuda' else None}
        (args.output/'status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    whole_count=0;quarantined=0
    with (args.output/'whole-rewrites.jsonl').open('w',encoding='utf-8') as stream,(args.output/'paragraph-pairs.jsonl').open('w',encoding='utf-8') as pairs:
        for row in parents:
            parts=db.execute('SELECT start,end,state,result,checks FROM segments WHERE parent_id=? ORDER BY start',(row['documentId'],)).fetchall()
            cursor=0;query_parts=[];mappings=[]
            for start,end,state,rewritten,checks_json in parts:
                if state!='ACCEPTED':continue
                checks=json.loads(checks_json)
                if checks.get('separatorOnly'):continue
                begin=cursor;query_parts.append(rewritten);cursor+=len(rewritten)+1
                mapping={'queryStart':begin,'queryEnd':begin+len(rewritten),'sourceStart':start,'sourceEnd':end};mappings.append(mapping)
                pair={'taskType':'CONTENT_CORRESPONDENCE','labelOrigin':'controlled_construction','labelConfidence':'known','target':1,
                      'sourceClusterId':row['sourceClusterId'],'eventClusterId':row['eventClusterId'],'split':'train','sourceIds':[row['documentId']],
                      'query':rewritten,'source':row['text'][start:end],'sourceOffsets':{'start':start,'end':end},'checks':checks,'transformationKind':checks.get('transformationKind','PARAPHRASE'),'generatorRevision':acquisition['revision']}
                pairs.write(json.dumps(pair,ensure_ascii=False)+'\n')
            if any(part[2]!='ACCEPTED' for part in parts):quarantined+=1;continue
            query='\n'.join(query_parts)
            checks=rewrite_checks(row['text'],query,[row['institutionName']])
            if not checks['accepted']:quarantined+=1;continue
            record={'queryId':'constructed:'+hashlib.sha256((row['documentId']+config_sha).encode()).hexdigest(),'category':'whole_paraphrase',
                    'labelOrigin':'controlled_construction','labelConfidence':'known','humanVerified':False,'split':'train','sourceIds':[row['documentId']],
                    'sourceClusterId':row['sourceClusterId'],'eventClusterId':row['eventClusterId'],'query':query,'sourceMappings':mappings,'checks':checks}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');whole_count+=1
    result={'state':'TRAIN_CONSTRUCTION_FINISHED','wholeRewrites':whole_count,'quarantinedWholeOriginals':quarantined,'segmentCounts':dict(db.execute('SELECT state,count(*) FROM segments GROUP BY state')),
            'promptVersion':args.prompt_version,'reusedSegments':reused,
            'selectedOriginals':len(parents),'elapsedSeconds':time.monotonic()-started,'generatorDevice':args.device,'semanticCorrectnessCertified':False,
            'negativePairsPrepared':False,'neuralCampusAdaptationComplete':False,'finalQueriesGenerated':False}
    db.close();(args.output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        if OUTPUT_LOCATION:
            OUTPUT_LOCATION.mkdir(parents=True,exist_ok=True)
            (OUTPUT_LOCATION/'status.json').write_text(json.dumps({'state':'GENERATION_FAILED','error':type(error).__name__+': '+str(error),'wholeRewritesComplete':False}),encoding='utf-8')
        raise
