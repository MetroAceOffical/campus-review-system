"""Run actual document-check functions on frozen controls without GPU allocation."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from corpus import read_jsonl
from construct_correspondence import verify_ready
from document_evaluation import ROOT, DATA, atomic_json as _atomic_json, sha, edit_score
from run_campus_stage import stage_lock

sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import digest_json, controlled_file


def atomic_json(path,value):
    for attempt in range(8):
        try:return _atomic_json(path,value)
        except PermissionError:
            if attempt==7:raise
            time.sleep(.05*(attempt+1))


def resource_budget(kind,device):
    if kind not in ('grammar-model','image-text'):return 0,0
    if device=='cuda':return int(1.5*1024**3),int((6.5 if kind=='grammar-model' else 2)*1024**3)
    return (10 if kind=='grammar-model' else 4)*1024**3,0


def field_score(expected, actual):
    values={r['field']:r['status'] for r in actual}
    return dict(assessableFields=sum(v!='INSUFFICIENT' for v in expected.values()),
                correctFields=sum(v!='INSUFFICIENT' and values.get(k)==v for k,v in expected.items()),
                unresolvedFields=sum(v!='INSUFFICIENT' and values.get(k)=='INSUFFICIENT' for k,v in expected.items()),
                conflictFields=sum(v=='CONFLICT' for v in expected.values()),
                detectedConflicts=sum(v=='CONFLICT' and values.get(k)==v for k,v in expected.items()),
                falseConflicts=sum(v!='CONFLICT' and values.get(k)=='CONFLICT' for k,v in expected.items()),
                insufficientControls=sum(v=='INSUFFICIENT' for v in expected.values()),
                correctInsufficient=sum(v=='INSUFFICIENT' and values.get(k)==v for k,v in expected.items()))


def aggregate(rows):
    keys=('truePositive','falsePositive','falseNegative','invalidSuggestions','assessableFields','correctFields',
          'unresolvedFields','conflictFields','detectedConflicts','falseConflicts','insufficientControls','correctInsufficient')
    value={key:sum(r.get('metrics',{}).get(key,0) for r in rows if not r.get('error')) for key in keys}
    value.update(failedQueries=sum(bool(r.get('error')) for r in rows),knownContextQueries=sum(bool(r.get('contextEligible')) for r in rows),
                 relatedTop1=sum(r.get('contextRank')==1 for r in rows),relatedTop3=sum(r.get('contextRank') in (1,2,3) for r in rows),
                 realRuntimeQueries=sum(r.get('realOrSynthetic')=='real' for r in rows),
                 realRuntimeCompleted=sum(r.get('realOrSynthetic')=='real' and not r.get('error') for r in rows))
    return value


def main():
    import psutil
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',required=True,choices=['grammar-rules','grammar-model','image-fields','image-text'])
    parser.add_argument('--data',type=Path,default=DATA)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--inspection',type=Path,help='Isolated candidate source under runtime/experiments; default is the deployed implementation')
    args=parser.parse_args();data=args.data.resolve();output=args.output.resolve()
    inspector=(args.inspection or ROOT/'app/python/campus_workbench/inspection.py').resolve()
    if args.inspection and (not inspector.is_relative_to((ROOT/'runtime/experiments').resolve()) or inspector.suffix!='.py' or not inspector.is_file()):
        raise ValueError('Candidate inspection source must be a project experiment Python file')
    os.environ['CUDA_VISIBLE_DEVICES']='0' if args.device=='cuda' else ''
    if not data.is_relative_to((ROOT/'runtime/datasets').resolve()) or not output.is_relative_to((ROOT/'runtime/experiments').resolve()):
        raise ValueError('Use project dataset and experiment paths')
    output.mkdir(parents=True,exist_ok=True)
    with stage_lock(output/'run.lock'):
        rows=[];started=time.perf_counter();previous_seconds=0;peak_cuda=0
        def status(state,**extra):
            nonlocal peak_cuda
            torch=sys.modules.get('torch')
            if args.device=='cuda' and torch is not None and torch.cuda.is_initialized():peak_cuda=max(peak_cuda,torch.cuda.max_memory_allocated())
            atomic_json(output/'status.json',dict(state=state,processed=len(rows),total=len(samples),
                elapsedSeconds=previous_seconds+time.perf_counter()-started,**aggregate(rows),
                cudaPeakAllocatedBytes=peak_cuda,hostRssBytes=psutil.Process().memory_info().rss,
                qualityAccepted=False,productActivated=False,finalQueriesEvaluated=0,**extra))
        try:
            ready=verify_ready(data)
            grammar=args.kind.startswith('grammar')
            samples=list(read_jsonl(data/('grammar.jsonl' if grammar else 'image-text.jsonl')))
            if args.kind=='image-fields':samples=[s for s in samples if s['realOrSynthetic']=='synthetic']
            if len(samples)!=(500 if grammar else 100 if args.kind=='image-fields' else 150):
                raise ValueError('Complete declared development controls required')
            material=ROOT/'app/training/document_evaluation.py'
            if sha(material)!=json.loads((data/'manifest.json').read_text(encoding='utf-8'))['materialCodeSha256']:
                raise ValueError('Frozen material builder changed')
            snapshot=output/'inspection-snapshot.py'
            if not snapshot.exists():snapshot.write_bytes(inspector.read_bytes())
            dependencies=[Path(__file__),material,ROOT/'app/training/corpus.py',ROOT/'app/training/construct_correspondence.py',ROOT/'app/training/run_campus_stage.py',ROOT/'app/python/campus_shared/contracts.py',ROOT/'app/python/campus_shared/document_compute.py',ROOT/'app/python/campus_workbench/grammar_edits.py']
            identity=dict(schemaVersion='document-development-evaluation-v1',kind=args.kind,samples=len(samples),
                datasetReadySha256=sha(data/'READY'),datasetHashes=ready,device=args.device,batchSize=64 if grammar else 6,
                inspectionSource=str(inspector.relative_to(ROOT)),inspectionSnapshotSha256=sha(snapshot),algorithms={str(p.relative_to(ROOT)):sha(p) for p in dependencies},artifactFiles={},
                candidateOrder='SHA256(sampleId + NUL + contextId)',
                python=sys.version,software={name:importlib.metadata.version(name) for name in ['torch','transformers','Pillow','psutil']},
                scope='AUTHORED_GRAMMAR_CONTROLS' if grammar else 'HISTORICAL_OCR_FIELD_DIAGNOSTIC' if args.kind=='image-fields' else 'SYNTHETIC_NOTICE_AND_UNLABELLED_REAL_RUNTIME')
            for name in ['Qwen2.5-3B-Instruct/aa8e72537993ba99e69dfaafa59ed015b17504d1','chinese-clip-vit-base-patch16/36e679e65c2a2fead755ae21162091293ad37834']:
                if args.kind=='grammar-model' and name.startswith('Qwen') or args.kind=='image-text' and name.startswith('chinese'):
                    artifact=ROOT/'runtime/models/final'/name/'acquisition.json'
                    identity['artifactFiles'][str(artifact.relative_to(ROOT))]=sha(artifact)
            if args.kind=='image-text':
                artifact=ROOT/'app/config/frozen-ocr-v2.json'
                identity['ocrConfiguration']=json.loads(artifact.read_text(encoding='utf-8'))
                identity['artifactFiles'][str(artifact.relative_to(ROOT))]=sha(artifact)
            run_path=output/'run.json'
            if run_path.exists():
                if not args.resume or json.loads(run_path.read_text(encoding='utf-8'))!=identity:raise ValueError('Explicit same-identity resume required')
            elif any(p.name not in ('run.lock','inspection-snapshot.py') for p in output.iterdir()):
                raise ValueError('Nonempty output lacks frozen run identity')
            atomic_json(run_path,identity);run_id=digest_json(identity)
            history=output/'predictions.jsonl'
            rows=list(read_jsonl(history)) if history.exists() else []
            if len(rows)>len(samples):raise ValueError('Too many saved predictions')
            for row,sample in zip(rows,samples):
                if (row.get('sampleId'),row.get('inputSha256'),row.get('runId'))!=(sample['sampleId'],digest_json(sample),run_id):raise ValueError('Saved input order or identity changed')
            old_status=output/'status.json'
            if old_status.exists():previous_seconds=json.loads(old_status.read_text(encoding='utf-8')).get('elapsedSeconds',0)
            def guard():
                for name,h in identity['algorithms'].items():
                    if sha(ROOT/name)!=h:raise ValueError('Evaluation code changed: '+name)
                for name,h in identity['artifactFiles'].items():
                    if sha(ROOT/name)!=h:raise ValueError('Model/configuration identity changed: '+name)
                if sha(snapshot)!=identity['inspectionSnapshotSha256']:raise ValueError('Inspection snapshot changed')
            guard()
            spec=importlib.util.spec_from_file_location('frozen_document_inspection',snapshot)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.ROOT=ROOT
            module.QWEN=ROOT/'runtime/models/final/Qwen2.5-3B-Instruct/aa8e72537993ba99e69dfaafa59ed015b17504d1'
            module.CLIP=ROOT/'runtime/models/final/chinese-clip-vit-base-patch16/36e679e65c2a2fead755ae21162091293ad37834'
            minimum,gpu_minimum=resource_budget(args.kind,args.device)
            deadline=time.monotonic()+96*3600
            def wait_capacity():
                while psutil.virtual_memory().available<minimum:
                    guard();status('WAITING_HOST_MEMORY',availableMemoryBytes=psutil.virtual_memory().available,requiredMemoryBytes=minimum)
                    if time.monotonic()>deadline:raise TimeoutError('96-hour finite resource wait exceeded')
                    time.sleep(30)
                if gpu_minimum:
                    import torch
                    if not torch.cuda.is_available():raise RuntimeError('Approved CUDA runtime is unavailable')
                    while torch.cuda.mem_get_info()[0]<gpu_minimum:
                        guard();status('WAITING_GPU_RESOURCE',availableGpuBytes=torch.cuda.mem_get_info()[0],requiredGpuBytes=gpu_minimum)
                        if time.monotonic()>deadline:raise TimeoutError('96-hour finite GPU resource wait exceeded')
                        time.sleep(30)
            def emit(event):
                status('RUNNING_DOCUMENT_EVALUATION',steps=event.get('processed',0),totalSteps=event.get('total',0))
            def execute():
                with history.open('a',encoding='utf-8') as stream:
                    for offset in range(len(rows),len(samples),identity['batchSize']):
                        # The run already owns the compute lock and its resident model budget.
                        # Do not require a second model's worth of free memory at each batch.
                        batch=samples[offset:offset+identity['batchSize']];guard();status('RUNNING_DOCUMENT_EVALUATION')
                        tick=time.perf_counter();outputs=[]
                        if grammar:
                            pieces=[];citations=[];bounds=[];cursor=0
                            for sample in batch:
                                bounds.append((cursor,cursor+len(sample['text'])))
                                citations.extend(dict(plainStart=c['plainStart']+cursor,plainEnd=c['plainEnd']+cursor) for c in sample['citations'])
                                pieces.append(sample['text']);cursor+=len(sample['text'])+1
                            plain='\n'.join(pieces)
                            if len(plain)>10000:raise ValueError('Grammar batch exceeds product text budget')
                            error=None
                            try:result=module.grammar(dict(title='',plainText=plain,citations=citations,device=args.device,captureDiagnostics=True),emit,enhanced=args.kind=='grammar-model')
                            except Exception as failure:
                                error=type(failure).__name__+': '+str(failure);result={'issues':[]}
                            for sample,(left,right) in zip(batch,bounds):
                                issues=[dict(issue,start=issue['start']-left,end=issue['end']-left) for issue in result['issues'] if left<=issue['start']<right]
                                diagnostics=[dict(entry,start=entry['start']-left) for entry in result.get('diagnostics',[]) if left<=entry['start']<right]
                                outputs.append(dict(issues=issues,metrics=edit_score(sample,issues),category=sample['category'],error=error,diagnostics=diagnostics))
                        elif args.kind=='image-fields':
                            for sample in batch:
                                recognized='\n'.join(r['text'] for r in sample['cachedOcr']['recognitionLines'] if r['confidence']>=.8)
                                actual=module.compare_fields(recognized,sample['factContext'])
                                outputs.append(dict(fields=actual,expectedFields=sample['expectedFields'],metrics=field_score(sample['expectedFields'],actual),error=sample['cachedOcrError'],transformation=sample['transformation']))
                        else:
                            pictures=[]
                            for sample in batch:
                                path=controlled_file(sample['imagePath'],sample['imageSha256'],[ROOT/'runtime'])
                                contexts=sorted(sample['contexts'],key=lambda item:hashlib.sha256((sample['sampleId']+'\0'+item['contextId']).encode()).hexdigest())
                                pictures.append(dict(path=str(path),sha256=sample['imageSha256'],nodeId=sample['sampleId'],fileId=sample['sampleId'],
                                    caption='',contexts=contexts,factContext=sample['factContext']))
                            result=module.image_text(dict(checkId=run_id,images=pictures,ocrConfig=identity['ocrConfiguration'],device=args.device),emit)
                            for sample,result in zip(batch,result['images']):
                                related=next((i+1 for i,r in enumerate(result['matches']) if r.get('contextId')==sample['expectedContextId']),None) if sample['expectedContextId'] else None
                                metrics=field_score(sample['expectedFields'],result['fields']) if sample['expectedFields'] else {}
                                outputs.append(dict(result=result,metrics=metrics,contextRank=related,contextEligible=sample['expectedContextId'] is not None,
                                    transformation=sample.get('transformation','runtime'),realOrSynthetic=sample['realOrSynthetic'],error=result['ocrError'] or None))
                        if len(outputs)!=len(batch):raise ValueError('Incomplete batch response')
                        guard()
                        for sample,result in zip(batch,outputs):
                            row=dict(sampleId=sample['sampleId'],sourceFamilyId=sample['sourceFamilyId'],runId=run_id,inputSha256=digest_json(sample),
                                     batchAmortizedElapsedMs=(time.perf_counter()-tick)*1000/len(batch),**result)
                            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno());rows.append(row)
                        if gpu_minimum:
                            import gc,torch
                            gc.collect();torch.cuda.empty_cache()
                        status('RUNNING_DOCUMENT_EVALUATION')
            if minimum:
                # Serialize only these two CPU neural evaluators, independent of the formal GPU queue.
                while True:
                    wait_capacity()
                    try:
                        with stage_lock(ROOT/'runtime/locks/document-neural-evaluation.lock'):
                            from contextlib import nullcontext
                            from campus_shared.document_compute import document_slot
                            with document_slot(ROOT/'runtime',neural=True) if gpu_minimum else nullcontext():execute()
                        break
                    except RuntimeError as lock_error:
                        if 'holds the project lock' not in str(lock_error):raise
                        status('WAITING_CPU_EVALUATOR')
                        if time.monotonic()>deadline:raise TimeoutError('96-hour CPU evaluator wait exceeded')
                        time.sleep(30)
            else:execute()
            guard();verify_ready(data)
            summary=dict(state='DOCUMENT_EVALUATION_COMPLETE',kind=args.kind,queries=len(rows),runId=run_id,**aggregate(rows),
                         scope=identity['scope'],qualityAccepted=False,finalQueriesEvaluated=0,cudaPeakAllocatedBytes=peak_cuda,
                         byCategory={name:aggregate([r for r in rows if r.get('category',r.get('transformation'))==name]) for name in sorted({r.get('category',r.get('transformation','runtime')) for r in rows})})
            atomic_json(output/'summary.json',summary);status(summary['state'])
            print(json.dumps({'state':summary['state'],'kind':args.kind,'queries':len(rows),**aggregate(rows)}),flush=True)
        except Exception as failure:
            previous=json.loads((output/'status.json').read_text(encoding='utf-8')) if (output/'status.json').exists() else {}
            atomic_json(output/'status.json',previous|dict(state='DOCUMENT_EVALUATION_STOPPED',error=type(failure).__name__+': '+str(failure)))
            raise


if __name__=='__main__':main()
