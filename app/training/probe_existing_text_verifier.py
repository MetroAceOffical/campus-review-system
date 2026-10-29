"""Offline Qwen correspondence candidate on the same16 existing diagnostic cases."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench import inspection,text_verification
from campus_shared.contracts import file_sha256
from campus_shared.document_compute import document_slot
from run_document_evaluation import atomic_json
from probe_existing_text_decisions import decision
from text_verifier_metrics import summarize_cases


def main():
    import torch,psutil
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    baseline=args.baseline.resolve();output=args.output.resolve()
    if not baseline.is_relative_to(ROOT/'runtime/experiments') or not output.is_relative_to(ROOT/'runtime/experiments') or output.exists():raise ValueError('Require project input and new experiment directory')
    output.mkdir(parents=True);deadline=time.monotonic()+2*3600;started=time.perf_counter()
    def state(name,**extra):atomic_json(output/'status.json',dict(state=name,elapsedSeconds=time.perf_counter()-started,**extra))
    while not (baseline/'summary.json').exists():
        state('WAITING_BASELINE_DECISIONS')
        if time.monotonic()>deadline:raise TimeoutError('Finite baseline wait expired')
        time.sleep(15)
    previous=json.loads((baseline/'summary.json').read_text(encoding='utf-8'))
    if previous['state']!='EXISTING_TEXT_DECISIONS_COMPLETE' or previous['queries']!=32:raise ValueError('Require all32 baseline requests')
    run=json.loads((baseline/'run.json').read_text(encoding='utf-8'));cases={c['caseId']:c for c in run['cases']}
    rows=[json.loads(line) for line in (baseline/'predictions.jsonl').open(encoding='utf-8')];rows=[r for r in rows if r['generation']=='18']
    if len(rows)!=16 or len({r['caseId'] for r in rows})!=16:raise ValueError('Require all16 existing cases')
    files=[Path(__file__),ROOT/'app/training/text_verifier_metrics.py',Path(text_verification.__file__),Path(inspection.__file__),ROOT/'app/python/campus_shared/document_compute.py',baseline/'run.json',baseline/'predictions.jsonl',baseline/'summary.json',ROOT/'runtime/indexes/18/manifest.json']
    hashes={p.relative_to(ROOT).as_posix():file_sha256(p) for p in files}
    if hashes['runtime/indexes/18/manifest.json']!=run['hashes']['runtime/indexes/18/manifest.json']:raise ValueError('Reference snapshot differs')
    library=json.loads((ROOT/'runtime/indexes/18/manifest.json').read_text(encoding='utf-8'))
    documents={str(d['sourceRevisionId']):d for d in library['documents'] if d.get('sourceKind','BODY')=='BODY'}
    atomic_json(output/'run.json',dict(hashes=hashes,sourceSelection='First3 BODY candidates from actual current-library Top10; no truth-source injection',queries=16,
                scope='Candidate only; four scoped human-reviewed normal controls and12 authored positive cases; no independent natural quality acceptance',
                modelRevision=inspection.QWEN.name,weightsChanged=False,trainingSamplesAdded=0,maxInputTokens=4096,maxNewTokens=384,evidenceProtocol='indexed-exact-sentence-spans',productActivated=False))
    def guard():
        for name,sha in hashes.items():
            if file_sha256(ROOT/name)!=sha:raise ValueError('Bound algorithm/material changed: '+name)
    while True:
        guard()
        if time.monotonic()>deadline:raise TimeoutError('Finite verifier resource wait expired')
        if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<6.5*1024**3 or psutil.virtual_memory().available<1.5*1024**3:
            state('WAITING_GPU_RESOURCE');time.sleep(15);continue
        try:
            with document_slot(ROOT/'runtime',neural=True):
                inspection.check_files(inspection.QWEN);torch.set_num_threads(2);tokenizer,model=inspection._grammar_pipeline('cuda')
                completed=[];attempted=0;assessed=0;invalid=0;skipped=0
                with (output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
                    for row in rows:
                        case=cases[row['caseId']];report=json.loads(json.dumps(row['report']));sources=[]
                        for evidence in report['evidence']:
                            evidence['semanticSummary']={'status':'NOT_EVALUATED','suspectedReuse':False}
                            if evidence.get('sourceKind','BODY')!='BODY' or len(sources)>=3:continue
                            guard();source=documents[str(evidence['sourceRevisionId'])]
                            verified=text_verification.verify_correspondence(case['text'],source['text'],tokenizer,model)
                            attempted+=1;assessed+=verified['assessed'];invalid+=verified['status']=='INVALID_MODEL_SUPPORT';skipped+=verified['status']=='CONTEXT_BUDGET_EXCEEDED'
                            evidence['semanticSummary']=verified;sources.append(dict(sourceWorkId=evidence['sourceWorkId'],sourceRevisionId=evidence['sourceRevisionId'],result=verified))
                            state('VERIFYING_SOURCE_CONTENT',processed=len(completed),total=16,attemptedSources=attempted,assessedSources=assessed,invalidSources=invalid,skippedSources=skipped)
                        actual=decision(report,case['expected'],case['judgedSources'],case['normal'])
                        result=dict(caseId=case['caseId'],sources=sources,baseline=row['variants']['current'],candidate=actual,allSelectedSourcesAssessed=all(s['result']['assessed'] for s in sources))
                        completed.append(result);stream.write(json.dumps(result,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
                guard()
                summary=dict(state='EXISTING_TEXT_VERIFIER_COMPLETE',queries=16,attemptedSources=attempted,assessedSources=assessed,invalidSources=invalid,skippedSources=skipped,
                             incompleteDocuments=sum(not r['allSelectedSourcesAssessed'] for r in completed),elapsedSeconds=time.perf_counter()-started,productActivated=False,qualityAccepted=False,finalQueriesInferred=0,
                             **summarize_cases(completed))
                atomic_json(output/'summary.json',summary);atomic_json(output/'status.json',summary);print(json.dumps(summary));return
        except BlockingIOError:
            state('WAITING_SHARED_COMPUTE_SLOT');time.sleep(15)


if __name__=='__main__':
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    main()
