"""Real frozen-v2/literal-only exports with the same immutable evaluation protocol."""
import argparse,contextlib,json,sqlite3,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection import retrieval
from campus_detection.v3_runtime import controlled,verify_files
from corpus import read_jsonl
from v3_workflow import ready_queries,split_digest,validate_development_evidence,write,freeze,implementation
from run_campus_stage import stage_lock


def convert(query,result,method,reference_sha,semantic_enabled):
    pairs=[];decisions=[];scores=[]
    policy=result['actualConfig']['semanticPolicy'];threshold=policy['scoreThreshold']
    for item in result['evidence']:
        key={'sourceRevisionId':item['sourceRevisionId'],'sourceKey':item['sourceKey']}
        decisions.append({**key,'acceptedCandidate':item['acceptedCandidate'],'semanticHint':semantic_enabled and item.get('semanticSummary',{}).get('suspectedReuse',False)})
        for match in item['matches']:pairs.append({**match,**key,'evidenceKind':'LITERAL_EXACT'})
        if semantic_enabled:
            for window in item['semanticWindows']:
                pairs.append({**window,**key,'scoreType':'LEGACY_SEMANTIC_SCORE','supportPolicyPassed':window['score']>=threshold and window.get('tfidfScore',0)>=policy['lexicalFloor']});scores.append(window['score'])
    evaluation=result.get('semanticEvaluation',{});partial=semantic_enabled and evaluation.get('availableQueryUnits',0)>evaluation.get('evaluatedQueryUnits',0)
    return {'queryId':query['queryId'],'querySha256':query['querySha256'],'methodConfigId':method,'referenceManifestSha256':reference_sha,
        'coverageStatus':'PARTIAL' if partial else 'COMPLETE','pairs':pairs,'sourceDecisions':decisions,
        'candidateSources':[{'sourceRevisionId':r['sourceRevisionId']} for r in result['evidence']],
        'pairScoreThreshold':threshold,'decisionScore':max(scores) if scores else None if semantic_enabled else float(any(r['acceptedCandidate'] for r in decisions)),
        'decisionScoreType':'LEGACY_MAX_OBSERVED_BERT_SCORE' if semantic_enabled else 'BINARY_LITERAL_DECISION','elapsedMs':result['elapsedMs'],
        'semanticEvaluation':evaluation,'semanticEnabled':semantic_enabled}


def main():
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--variant',choices=['frozen-v2','semantic-disabled'],required=True);p.add_argument('--split',choices=['dev','final'],required=True);p.add_argument('--development-run',type=Path);p.add_argument('--diagnostic-controls',action='store_true');p.add_argument('--resume',action='store_true');a=p.parse_args()
    for value in vars(a).values():
        if isinstance(value,Path):controlled(value)
    queries=ready_queries(a.protocol,a.split,a.diagnostic_controls);references=list(read_jsonl(a.protocol/'references.jsonl'));refsha=retrieval._sha(a.protocol/'references.jsonl');enabled=a.variant=='frozen-v2'
    if a.output.exists() and (not a.resume or (a.output/'READY').exists()):raise ValueError('Use a new export or explicitly resume an unfinished one')
    from campus_detection.models import configurations,load_models
    config,_=configurations();identity={**implementation(),'app/training/export_legacy_evaluation.py':retrieval._sha(Path(__file__))}
    method='legacy-eval-'+retrieval._digest({'variant':a.variant,'config':config,'referenceSha256':refsha,'implementation':identity})
    devsha=None
    if a.split=='final':
        if not a.development_run:raise ValueError('Final baseline needs full400 development evidence for the same method')
        verify_files(a.development_run);devrun=json.loads((a.development_run/'run.json').read_text(encoding='utf-8'));summary=json.loads((a.development_run/'summary.json').read_text(encoding='utf-8'))
        validate_development_evidence(devrun,summary,split_digest(ready_queries(a.protocol,'dev')),refsha,method,400);devsha=retrieval._sha(a.development_run/'READY')
    run={'protocolReadySha256':retrieval._sha(a.protocol/'READY'),'splitQueriesSha256':split_digest(queries),'referenceManifestSha256':refsha,
        'methodConfigId':method,'split':a.split,'diagnosticControls':a.diagnostic_controls,'variant':a.variant,
        'operatingPointFrozen':True,'developmentEvidenceSha256':devsha,'implementation':identity,'semanticEnabled':enabled,
        'campusRetrieverTrainingComplete':False,'correspondenceTrainingComplete':False,'formalCalibrationFrozen':False}
    if enabled:
        from campus_workbench.training import compute_slot
        lock=compute_slot(ROOT/'runtime',True)
    else:
        # Pure CPU baseline has its own lock; it never loads neural weights or
        # competes for the Web/GPU compute slot. Bound CPU library threads externally.
        import psutil
        if psutil.virtual_memory().available<2*1024**3:raise RuntimeError('Insufficient free CPU memory for the full reference bank')
        lock=stage_lock(ROOT/'runtime/experiments/literal-evaluation-cpu.lock')
    with lock:
        if enabled:models=load_models()
        else:
            from transformers import AutoTokenizer
            def no_neural_pairs(pairs):
                if pairs:raise RuntimeError('Semantic-disabled baseline attempted neural inference')
                return []
            models={'textConfig':config,'textConfigs':{config['configId']:config},'tokenizer':AutoTokenizer.from_pretrained(ROOT/'validation/text/models/bert-base-chinese',local_files_only=True,use_fast=True),'predictBert':no_neural_pairs}
            models['tokenizer'].model_max_length=10**8
        originals={str(r['sourceRevisionId'])+':'+r.get('sourceKey','BODY'):r.get('sourceKey','BODY') for r in references}
        documents=[{**r,'sourceKey':str(r['sourceRevisionId'])+':'+r.get('sourceKey','BODY')} for r in references];library={'generationId':'1','documents':documents,'images':[]}
        a.output.mkdir(parents=True,exist_ok=True)
        if (a.output/'run.json').exists() and json.loads((a.output/'run.json').read_text(encoding='utf-8'))!=run:raise ValueError('Baseline resume identity changed')
        write(a.output/'run.json',run);db=sqlite3.connect(a.output/'predictions.sqlite');db.execute('CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,result TEXT NOT NULL)')
        from campus_detection.text import detect_text,prepare_text_index
        for query in queries:
            if db.execute('SELECT 1 FROM predictions WHERE id=?',(query['queryId'],)).fetchone():continue
            tick=time.perf_counter()
            try:
                excluded=set(query.get('negativeScope',{}).get('excludedSourceRevisionIds',[]));selected=library
                if excluded:
                    if '_textIndex' not in library:library['_textIndex']=prepare_text_index(library,models)
                    selected={**library,'documents':[r for r in documents if r['sourceRevisionId'] not in excluded]}
                request={'taskId':query['queryId'],'attemptId':query['queryId'],'scene':'EXTERNAL','inputSnapshotKey':query['queryId'],'inputSha256':query['querySha256'],'libraryGenerationId':'1','configId':config['configId'],'text':query['query'],'excludeManuscriptId':query.get('queryManuscriptId')}
                result=detect_text(request,selected,models,semantic_enabled=enabled)
                for item in result['evidence']:item['sourceKey']=originals[item['sourceKey']]
                record=convert(query,result,method,refsha,enabled)
            except Exception as error:record={'queryId':query['queryId'],'querySha256':query['querySha256'],'methodConfigId':method,'referenceManifestSha256':refsha,'coverageStatus':'FAILED','pairs':[],'sourceDecisions':[],'candidateSources':[],'decisionScore':None,'errorType':type(error).__name__,'message':str(error)[:300]}
            record['elapsedMs']=(time.perf_counter()-tick)*1000;db.execute('INSERT INTO predictions VALUES(?,?)',(query['queryId'],json.dumps(record,ensure_ascii=False)));db.commit()
            write(a.output/'status.json',{'state':'EXPORTING_REAL_BASELINE_PREDICTIONS','variant':a.variant,'processed':db.execute('SELECT count(*) FROM predictions').fetchone()[0],'total':len(queries),'neuralWeightsLoaded':enabled})
        with (a.output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
            for query in queries:stream.write(db.execute('SELECT result FROM predictions WHERE id=?',(query['queryId'],)).fetchone()[0]+'\n')
        db.close();freeze(a.output,['run.json','predictions.jsonl','predictions.sqlite']);write(a.output/'status.json',{'state':'BASELINE_PREDICTIONS_EXPORTED','queries':len(queries),'variant':a.variant,'qualityAccepted':False})
    command=[sys.executable,'-B',str(ROOT/'app/training/evaluate_final.py'),'--protocol',str(a.protocol),'--predictions',str(a.output),'--method-config-id',method,'--split',a.split,'--output',str(a.output.with_name(a.output.name+'-metrics'))]
    if a.diagnostic_controls:command.append('--diagnostic-controls')
    if a.development_run:command.extend(['--development-run',str(a.development_run)])
    subprocess.run(command,cwd=ROOT,check=True)


if __name__=='__main__':main()
