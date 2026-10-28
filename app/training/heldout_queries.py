"""Traceable heldout query construction; this queue is never neural training data."""
import argparse,contextlib,hashlib,json,re,shutil,sqlite3,sys,time
from collections import Counter
from pathlib import Path
from construct_correspondence import verify_ready,source_segments,generation_prompt,generation_options,rewrite_checks
from corpus import read_jsonl,normalized
from run_campus_stage import stage_lock
ROOT=Path(__file__).resolve().parents[2]
REVISION='aa8e72537993ba99e69dfaafa59ed015b17504d1'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def code_identity():
    names=['app/training/'+name for name in ('heldout_queries.py','construct_correspondence.py','corpus.py','run_campus_stage.py')]+['app/python/campus_workbench/training.py']
    return {name:sha(ROOT/name) for name in names}


def assert_heldout_sources(plan,references):
    if plan['split'] not in ('calibration','dev','final'):raise ValueError('Training parents cannot construct heldout queries')
    for key in plan['constructionParents']:
        if key not in references or references[key]['sourceSplit']!=plan['split']:raise ValueError('Construction parent crosses heldout boundaries')


def substantive_mix(plan,parts,references):
    values=[parts[k] for k in plan['segmentIds']]
    substantive=[p for p in values if p.get('checks',{}).get('accepted') and p['checks'].get('transformationKind')=='PARAPHRASE']
    if plan['category'] in ('local','multi_source'):return len(substantive)==len(values) and bool(values)
    amount=lambda rows:sum(len(normalized(references[p['sourceId']]['text'][p['start']:p['end']])) for p in rows)
    return amount(substantive)>=.5*max(1,amount(values))


def materialize(plan,parts,references):
    pieces=[parts[k] for k in plan['segmentIds']]
    if plan['category']=='whole_reordered':
        pivot=max(1,len(pieces)//2);pieces=pieces[pivot:]+pieces[:pivot]
        if len(pieces)==1:
            sentences=re.findall(r'[^。！？；\n]+[。！？；\n]*',pieces[0]['result'])
            if len(sentences)<2:raise ValueError('Generated whole query has no reorderable sentence boundary')
            pivot=max(1,len(sentences)//2);pieces=[{**pieces[0],'result':''.join(sentences[pivot:]+sentences[:pivot])}]
    cursor=0;chunks=[];mappings=[]
    for part in pieces:
        if part['sourceId'] not in plan['expectedSourceIds'] or references[part['sourceId']]['sourceSplit']!=plan['split']:raise ValueError('Generation parent identity differs')
        value=part['result'];chunks.append(value)
        mappings.append({'sourceRevisionId':part['sourceId'],'sourceKey':'BODY','queryStart':cursor,'queryEnd':cursor+len(value),
            'sourceStart':part['start'],'sourceEnd':part['end'],'mappingType':'EXACT_SEGMENT' if value==references[part['sourceId']]['text'][part['start']:part['end']] else 'PARAPHRASE_SEGMENT'})
        cursor+=len(value)+1
    query='\n'.join(chunks);context=None
    if plan['category']=='local':
        key=plan['contextSourceId'];parent=references[key]
        if key in plan['expectedSourceIds'] or parent['sourceSplit']!=plan['split']:raise ValueError('Local context must be a separate same-split source')
        text=parent['text'][:plan['contextEnd']];middle=len(text)//2
        ends=[i+1 for i,c in enumerate(text[:middle+1]) if c in '。！？；\n'];cut=ends[-1] if ends else middle
        prefix=text[:cut]+'\n';query=prefix+query+'\n'+text[cut:]
        for span in mappings:span['queryStart']+=len(prefix);span['queryEnd']+=len(prefix)
        context={'sourceRevisionId':key,'sourceStart':0,'sourceEnd':len(text),'text':text,'queryPrefixEnd':cut,
                 'querySuffixStart':len(prefix)+cursor,'role':'CONTROLLED_REAL_CONTEXT_EXCLUDED_FROM_REFERENCE_CANDIDATES'}
    if not 1<=len(query)<=10000:raise ValueError('Constructed query exceeds product codepoint limit')
    row={**plan,'query':query,'querySha256':digest(query),'queryManuscriptId':plan['queryId'],
        'truthScope':'known_positive_sources_only','labelOrigin':'controlled_construction','labelConfidence':'known','humanVerified':False,
        'constructionStatus':'CONSTRUCTED','transformationKind':'PARAPHRASE_REORDER' if plan['category']=='whole_reordered' else 'PARAPHRASE',
        'sourceMappings':mappings,'generatorRevision':REVISION,'usedDetectorScoresForTruth':False,
        'expectedEvidenceScope':'LOCAL' if plan['category']=='local' else 'MULTI_SOURCE' if plan['category']=='multi_source' else 'WHOLE',
        'naturalProvenance':[]}
    if context:row.update(contextProvenance=context,negativeScope={'excludedSourceRevisionIds':[plan['contextSourceId']]})
    return row


def prepare(protocol,output):
    if output.exists():raise ValueError('Use a new immutable heldout construction version')
    hashes=verify_ready(protocol);refs={r['sourceRevisionId']:r for r in read_jsonl(protocol/'references.jsonl')};plans=list(read_jsonl(protocol/'construction-plan.jsonl'))
    usage=Counter(event for row in plans for event in row['eventClusterIds']);segments={};prepared=[]
    if max(usage.values(),default=0)>2:raise ValueError('Original event budget exceeded')
    for row in plans:
        assert_heldout_sources(row,refs)
        if row['constructionStatus']!='WAITING_HELDOUT_GENERATION':prepared.append(row);continue
        row={**row,'segmentIds':[]}
        if row['category']=='local':
            choices=[r for r in refs.values() if r['sourceSplit']==row['split'] and r['eventClusterId'] not in row['eventClusterIds'] and usage[r['eventClusterId']]<2 and len(r['text'])>=800]
            if not choices:row['constructionStatus']='NEEDS_LOCAL_CONTEXT_PARENT';prepared.append(row);continue
            context=min(choices,key=lambda r:(r['institutionName']!=refs[row['constructionParents'][0]]['institutionName'],usage[r['eventClusterId']],digest(row['queryId']+r['sourceRevisionId'])))
            usage[context['eventClusterId']]+=1;row['contextSourceId']=context['sourceRevisionId'];row['contextEnd']=min(1800,len(context['text']))
            row['constructionParents']=row['constructionParents']+[context['sourceRevisionId']]
            row['eventClusterIds']=sorted(set(row['eventClusterIds'])|{context['eventClusterId']});row['sourceClusterIds']=sorted(set(row['sourceClusterIds'])|{context['sourceClusterId']})
            row['contextInstitutionName']=context['institutionName']
        for key in row['expectedSourceIds']:
            source=refs[key];spans=source_segments(source['text'])
            if row['category'] in ('local','multi_source'):
                spans=[span for span in spans if len(normalized(source['text'][span['sourceStart']:span['sourceEnd']]))>=64]
                if not spans:raise ValueError('No valid original span for a planned local/multi-source query')
                spans=[min(spans,key=lambda r:digest(row['queryId']+key+str(r['sourceStart'])))]
            for span in spans:
                start,end=span['sourceStart'],span['sourceEnd'];text=source['text'][start:end]
                sid=digest(row['split']+':'+key+':'+str(start)+':'+str(end)+':'+digest(text))
                segments[sid]={'id':sid,'split':row['split'],'sourceId':key,'start':start,'end':end,'text':text,
                    'kind':'EXACT_TAIL' if len(normalized(text))<64 else 'PARAPHRASE'}
                row['segmentIds'].append(sid)
        prepared.append(row)
    output.mkdir(parents=True)
    with (output/'construction-plan.jsonl').open('w',encoding='utf-8') as stream:
        for row in prepared:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output/'segments.jsonl').open('w',encoding='utf-8') as stream:
        for row in segments.values():stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    db=sqlite3.connect(output/'generation.sqlite');db.executescript('CREATE TABLE segments(id TEXT PRIMARY KEY,state TEXT,result TEXT,checks TEXT,attempts INT);CREATE TABLE attempts(id INTEGER PRIMARY KEY,segment_id TEXT,number INT,result TEXT,checks TEXT,seconds REAL);')
    for sid,row in segments.items():
        tail=row['kind']=='EXACT_TAIL';db.execute('INSERT INTO segments VALUES(?,?,?,?,?)',(sid,'ACCEPTED' if tail else 'PENDING',row['text'] if tail else None,json.dumps({'accepted':True,'exactShortTailControl':True}) if tail else None,0))
    db.commit();db.close()
    config={'schemaVersion':'heldout-query-construction-v1','purpose':'HELDOUT_CONSTRUCTION_NEVER_NEURAL_TRAINING','protocol':str(protocol.resolve()),'protocolHashes':hashes,
        'generatorRevision':REVISION,'promptVersion':'3','segmentCodepoints':360,'attempts':2,'modelInputTokens':2048,'modelOutputTokens':512,
        'wholeMinimumSubstantivelyParaphrasedSourceFraction':.5,'wholeLiteralCopyFractionMaximum':.75,'localAndMultiAllSegmentsRequireParaphrase':True,
        'maximumQueriesPerEvent':2,'algorithmHashes':code_identity(),'planSha256':sha(output/'construction-plan.jsonl'),'segmentsSha256':sha(output/'segments.jsonl')}
    write(output/'config.json',config);shutil.copy2(Path(__file__),output/'construction-code.py')
    summary={'state':'HELDOUT_GENERATION_PLAN_PREPARED','requestedSlots':len(prepared),'existingConstructedQueries':sum(r['constructionStatus']=='CONSTRUCTED' for r in prepared),
        'positiveQueriesPlanned':sum(bool(r.get('segmentIds')) for r in prepared),'uniqueOriginalSegments':len(segments),
        'exactShortTailSegments':sum(r['kind']=='EXACT_TAIL' for r in segments.values()),'maximumPlannedQueriesPerEvent':max(usage.values()),
        'negativeTruthStillPending':sum(r['constructionStatus']=='NEEDS_SUPPORTED_NEGATIVE_SCOPE' for r in prepared),'neuralTrainingStarted':False,'modelEvaluationStarted':False,'qualityAccepted':False}
    write(output/'status.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


def verify_work(work):
    config=json.loads((work/'config.json').read_text(encoding='utf-8'))
    if config['algorithmHashes']!=code_identity() or sha(work/'construction-plan.jsonl')!=config['planSha256'] or sha(work/'segments.jsonl')!=config['segmentsSha256']:raise ValueError('Heldout construction code/input changed; use a reviewed new version')
    if verify_ready(Path(config['protocol']))!=config['protocolHashes']:raise ValueError('Original heldout protocol changed')
    return config


def generate(work,after_training_stage,wait_hours):
    config=verify_work(work);deadline=time.monotonic()+wait_hours*3600
    sys.path.insert(0,str(ROOT/'app/python'));from campus_workbench.training import compute_slot
    def status(state,**values):write(work/'status.json',{'state':state,'neuralTrainingStarted':False,'modelEvaluationStarted':False,**values})
    while True:
        verify_work(work)
        try:upstream=json.loads((after_training_stage/'status.json').read_text(encoding='utf-8'))
        except (FileNotFoundError,json.JSONDecodeError):upstream={}
        if upstream.get('state') in ('CAMPUS_TRAINING_AND_EXPORT_COMPLETE','M3_TRAINING_AND_EXPORT_COMPLETE_RETRIEVER_PENDING'):break
        if upstream.get('state')=='STAGE_STOPPED':raise RuntimeError('Upstream training stopped; heldout generation will not conceal or replace it')
        status('WAITING_CAMPUS_TRAINING_COMPLETION',upstreamState=upstream.get('state','NOT_STARTED'))
        if time.monotonic()>=deadline:raise TimeoutError('Upstream training not ready within finite waiting period')
        time.sleep(15)
    with contextlib.ExitStack() as stack:
        while True:
            try:stack.enter_context(compute_slot(ROOT/'runtime',True));break
            except BlockingIOError as e:
                status('WAITING_GPU_RESOURCE',reason=str(e))
                if time.monotonic()>=deadline:raise TimeoutError('GPU still busy; no other process was stopped')
                time.sleep(15)
        verify_work(work)
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        model_path=ROOT/'runtime/models/final/Qwen2.5-3B-Instruct'/REVISION;acquisition=json.loads((model_path/'acquisition.json').read_text(encoding='utf-8'))
        for item in acquisition['files']:
            if sha(model_path/item['file'])!=item['sha256']:raise ValueError('Fixed generator weights changed')
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():raise RuntimeError('Existing CUDA/BF16 unavailable; no environment change attempted')
        status('LOADING_HELDOUT_GENERATOR');torch.set_num_threads(4)
        tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(model_path,torch_dtype=torch.bfloat16,device_map={'':'cuda'},attn_implementation='sdpa',local_files_only=True,trust_remote_code=False).eval()
        protocol=Path(config['protocol']);refs={r['sourceRevisionId']:r for r in read_jsonl(protocol/'references.jsonl')};segments={r['id']:r for r in read_jsonl(work/'segments.jsonl')};db=sqlite3.connect(work/'generation.sqlite');started=time.monotonic()
        for sid,attempts in db.execute("SELECT id,attempts FROM segments WHERE state='PENDING' ORDER BY id").fetchall():
            row=segments[sid];source=refs[row['sourceId']];entities=[source['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',row['text'])
            for attempt in range(attempts,2):
                torch.manual_seed(20261028+int(sid[:8],16)+attempt);prompt=generation_prompt(row['text'],entities,'3')
                inputs=tokenizer.apply_chat_template([{'role':'system','content':'你是严谨的中文校园新闻编辑，保留全部原有事实。'},{'role':'user','content':prompt}],add_generation_prompt=True,return_tensors='pt').to('cuda')
                if inputs.shape[1]>2048:raise ValueError('Heldout input exceeds token budget; no truncation')
                tick=time.monotonic()
                with torch.inference_mode():output=model.generate(inputs,attention_mask=torch.ones_like(inputs),max_new_tokens=512,do_sample=True,**generation_options('3',attempt),pad_token_id=tokenizer.eos_token_id)
                tokens=output[0,inputs.shape[1]:];text=tokenizer.decode(tokens,skip_special_tokens=True).strip();checks=rewrite_checks(row['text'],text,entities,require_rewording=False)
                if len(tokens)>=512 and int(tokens[-1])!=tokenizer.eos_token_id:checks['accepted']=False;checks['reasons'].append('OUTPUT_TOKEN_BUDGET')
                checks.update(inputTokens=int(inputs.shape[1]),outputTokens=len(tokens),semanticCorrectnessCertified=False)
                db.execute('INSERT INTO attempts(segment_id,number,result,checks,seconds) VALUES(?,?,?,?,?)',(sid,attempt+1,text,json.dumps(checks,ensure_ascii=False),time.monotonic()-tick))
                db.execute('UPDATE segments SET state=?,result=?,checks=?,attempts=? WHERE id=?',('ACCEPTED' if checks['accepted'] else 'QUARANTINED' if attempt==1 else 'PENDING',text,json.dumps(checks,ensure_ascii=False),attempt+1,sid));db.commit()
                if checks['accepted']:break
            status('GENERATING_HELDOUT_QUERIES',counts=dict(db.execute('SELECT state,count(*) FROM segments GROUP BY state')),elapsedSeconds=time.monotonic()-started)
        db.close();verify_work(work);status('HELDOUT_SEGMENT_GENERATION_FINISHED',semanticCorrectnessCertified=False)


def assemble(work,output):
    config=verify_work(work);protocol=Path(config['protocol']);db=sqlite3.connect(f'file:{(work/"generation.sqlite").as_posix()}?mode=ro',uri=True)
    counts=dict(db.execute('SELECT state,count(*) FROM segments GROUP BY state'))
    if counts.get('PENDING',0):db.close();raise ValueError('Heldout segment generation is unfinished')
    parts={r['id']:r for r in read_jsonl(work/'segments.jsonl')}
    for sid,state,result,checks,attempts in db.execute('SELECT * FROM segments'):parts[sid].update(state=state,result=result,checks=json.loads(checks or '{}'))
    db.close();refs={r['sourceRevisionId']:r for r in read_jsonl(protocol/'references.jsonl')};plans=list(read_jsonl(work/'construction-plan.jsonl'));queries=list(read_jsonl(protocol/'queries.jsonl'));seen={normalized(r['query']) for r in queries};old=json.loads((protocol/'manifest.json').read_text(encoding='utf-8'));generated=0
    for row in plans:
        if not row.get('segmentIds'):continue
        if any(parts[k]['state']!='ACCEPTED' for k in row['segmentIds']):row['constructionStatus']='NEEDS_REPLACEMENT_GENERATION';continue
        if not substantive_mix(row,parts,refs):row['constructionStatus']='INSUFFICIENT_SUBSTANTIVE_PARAPHRASE';continue
        try:query=materialize(row,parts,refs)
        except ValueError as error:row.update(constructionStatus='QUERY_ASSEMBLY_FAILED',assemblyError=str(error));continue
        if row['category'] in ('whole_synonym','whole_reordered'):
            source=refs[row['expectedSourceIds'][0]];checks=rewrite_checks(source['text'],query['query'],[source['institutionName']],require_rewording=True)
            if not checks['accepted']:row['constructionStatus']='WHOLE_QUERY_CHECK_FAILED';row['queryChecks']=checks;continue
        if normalized(query['query']) in seen:row['constructionStatus']='DUPLICATE_QUERY_EXCLUDED';continue
        seen.add(normalized(query['query']));queries.append(query);row['constructionStatus']='CONSTRUCTED';generated+=1
    if output.exists():raise ValueError('Use a new immutable assembled protocol')
    output.mkdir(parents=True);shutil.copy2(protocol/'references.jsonl',output/'references.jsonl')
    for name,rows in [('construction-plan.jsonl',plans),('queries.jsonl',queries)]:
        with (output/name).open('w',encoding='utf-8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest={**old,'state':'HELDOUT_QUERY_MATERIAL_ASSEMBLED','constructedQueries':len(queries),'pendingSlots':sum(r['constructionStatus']!='CONSTRUCTED' for r in plans),'generatedParaphraseQueries':generated,
        'fullQuerySetReady':len(queries)==1800 and all(r['constructionStatus']=='CONSTRUCTED' for r in plans),'generationConfigSha256':sha(work/'config.json'),'constructionCodeSha256':sha(Path(__file__)),'finalProtocolExecuted':False,'qualityAccepted':False,
        'scope':'Traceable exact/natural controls and checked controlled paraphrase ranges; negative truth and NCUC coverage remain separate gates. Local context is real same-split text excluded before retrieval; no detector scores create labels.'}
    for split in ('calibration','dev','final'):
        made=[r for r in queries if r['split']==split];todo=[r for r in plans if r['split']==split]
        manifest['splitCounts'][split].update(constructed=len(made),pending=sum(r['constructionStatus']!='CONSTRUCTED' for r in todo),constructedByCategory=dict(Counter(r['category'] for r in made)),constructedHomePrimaryQueries=sum(r['homePrimary'] for r in made),constructionStatuses=dict(Counter(r['constructionStatus'] for r in todo)))
    write(output/'manifest.json',manifest);write(output/'READY',{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='READY'});print(json.dumps({'constructedQueries':len(queries),'generated':generated,'pending':manifest['pendingSlots'],'fullQuerySetReady':manifest['fullQuerySetReady']}))


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    plan=sub.add_parser('prepare');plan.add_argument('--protocol',type=Path,required=True);plan.add_argument('--output',type=Path,required=True)
    gen=sub.add_parser('generate');gen.add_argument('--work',type=Path,required=True);gen.add_argument('--after-training-stage',type=Path,required=True);gen.add_argument('--wait-hours',type=int,default=96)
    gen.add_argument('--assemble-output',type=Path)
    save=sub.add_parser('assemble');save.add_argument('--work',type=Path,required=True);save.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    for value in vars(args).values():
        if isinstance(value,Path) and not value.resolve().is_relative_to(ROOT/'runtime'):raise ValueError('Use project runtime paths')
    if args.action=='prepare':prepare(args.protocol,args.output)
    elif args.action=='generate':
        if not 1<=args.wait_hours<=96:raise ValueError('Use a finite1..96hour waiting period')
        with stage_lock(args.work/'generator.lock'):
            try:
                generate(args.work,args.after_training_stage,args.wait_hours)
                if args.assemble_output:assemble(args.work,args.assemble_output)
            except Exception as error:write(args.work/'status.json',{'state':'HELDOUT_GENERATION_STOPPED','message':str(error),'neuralTrainingStarted':False,'modelEvaluationStarted':False});raise
    else:assemble(args.work,args.output)


if __name__=='__main__':main()
