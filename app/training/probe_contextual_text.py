"""Actual bounded text evidence comparison on the unchanged16 historical cases."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'app/python'),str(ROOT/'validation/text')]
from campus_shared.contracts import file_sha256,digest_json
from campus_shared.document_compute import document_slot
from campus_detection import contextual_text,reference_versions
from campus_detection.models import configurations
from campus_detection.retrieval_model import load_retrieval_model
from probe_existing_text_decisions import prepare_cases,decision
from text_verifier_metrics import counts
from run_document_evaluation import atomic_json


def main():
    import torch,psutil,joblib,round2
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runtime/experiments') or output.exists():raise ValueError('New project experiment directory required')
    cases,files=prepare_cases();data=ROOT/'runtime/experiments/final-training-20261029/existing-text-decisions-v2'
    baseline=[json.loads(l) for l in (data/'predictions.jsonl').open(encoding='utf-8')];baseline={r['caseId']:r for r in baseline if r['generation']=='18'}
    library_path=ROOT/'runtime/indexes/18/manifest.json';library=json.loads(library_path.read_text(encoding='utf-8'))
    checkpoint=ROOT/'runtime/experiments/final-training-20261026/retriever-t2-v1/checkpoint-003126'
    model_hashes={k.removeprefix('model/'):v for k,v in json.loads((checkpoint/'READY').read_text(encoding='utf-8')).items() if k.startswith('model/')}
    files += [Path(__file__),Path(contextual_text.__file__),Path(reference_versions.__file__),library_path,data/'predictions.jsonl',ROOT/'app/python/campus_detection/retrieval_model.py',ROOT/'app/python/campus_detection/semantic.py']
    hashes={p.relative_to(ROOT).as_posix():file_sha256(p) for p in files}
    output.mkdir();started=time.perf_counter();deadline=time.monotonic()+3600;processed=0
    def guard():
        for name,h in hashes.items():
            if file_sha256(ROOT/name)!=h:raise ValueError('Bound source changed: '+name)
    def status(state,**extra):atomic_json(output/'status.json',dict(state=state,processed=processed,total=32,elapsedSeconds=time.perf_counter()-started,**extra))
    atomic_json(output/'run.json',dict(hashes=hashes,cases=16,requests=32,libraryGeneration='18',groupingPolicy='Reference-version compute groups; records and truth/citations retained',modelHashes=model_hashes,
        scope='12historical authored positives and4scoped reviewed normal controls; not independent natural gold',newTrainingSamples=0,epochsChanged=False,productActivated=False,finalQueriesInferred=0))
    try:
        while True:
            guard()
            if time.monotonic()>deadline:raise TimeoutError('One-hour finite evaluation wait expired')
            if psutil.virtual_memory().available<1.5*1024**3 or not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<2*1024**3:
                status('WAITING_GPU_RESOURCE');time.sleep(15);continue
            try:
                with document_slot(ROOT/'runtime',neural=True):
                    torch.set_num_threads(2);status('LOADING_EXISTING_BERT_AND_BGE')
                    _,bert,_,tokenizer=round2.load_selected('bert');tokenizer.model_max_length=10**8
                    def predict(rows):return round2.predict_rows('bert',bert,rows,tokenizer=tokenizer,batch=8)[0].tolist() if rows else []
                    retriever=load_retrieval_model(checkpoint/'model',expected_hashes=model_hashes,device='cuda',precision='BF16',batch_size=8)
                    base,_=configurations()
                    if any(r['report']['actualConfig']!=base for r in baseline.values()):raise ValueError('Actual historical method differs')
                    library['_textIndex']=joblib.load(ROOT/'runtime/indexes/18/text-index.joblib')
                    groups=reference_versions.reference_groups(library['documents']);group_sizes={}
                    for key,group in groups.items():group_sizes.setdefault(group,[]).append(key)
                    atomic_json(output/'reference-groups.json',dict(libraryManifestSha256=hashes['runtime/indexes/18/manifest.json'],records=len(groups),groups=len(group_sizes),duplicates=[v for v in group_sizes.values() if len(v)>1],recordsRemoved=0))
                    rows=[];methods=['context-lexical','context-hybrid']
                    with (output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
                        for name in methods:
                            config=contextual_text.configuration(base,hybrid=name=='context-hybrid',retriever=retriever['identity'])
                            models=dict(textConfig=config,textConfigs={config['configId']:config},tokenizer=tokenizer,predictBert=predict)
                            for case in cases:
                                guard();old=baseline[case['caseId']]['report'];cid=case['caseId']+'-'+name
                                if old['inputSha256']!=digest_json(case['text']) or old['libraryGenerationId']!='18':raise ValueError('Historical input differs')
                                request=dict(taskId=cid,attemptId=cid,scene='PRECHECK',inputSnapshotKey='diagnostic:'+cid,inputSha256=old['inputSha256'],libraryGenerationId='18',configId=config['configId'],text=case['text'],excludeManuscriptId=None)
                                report=contextual_text.detect(request,library,models,encode=retriever['encode'] if name=='context-hybrid' else None)
                                actual=decision(report,case['expected'],case['judgedSources'],case['normal'])
                                row=dict(caseId=case['caseId'],method=name,report=report,decision=actual,baseline=baseline[case['caseId']]['variants']['current'])
                                rows.append(row);stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno());processed+=1
                                status('RUNNING_CONTEXTUAL_TEXT',method=name,caseId=case['caseId'],lastElapsedMs=report['elapsedMs'])
                    guard();summary=dict(state='CONTEXTUAL_TEXT_COMPLETE',requests=32,uniqueCases=16,referenceRecords=len(groups),referenceGroups=len(group_sizes),duplicateGroups=sum(len(v)>1 for v in group_sizes.values()),
                        baseline=counts([baseline[c['caseId']]['variants']['current'] for c in cases]),methods={name:dict(**counts([r['decision'] for r in rows if r['method']==name]),
                        totalPairs=sum(r['report']['semanticEvaluation']['evaluatedPairs'] for r in rows if r['method']==name),elapsedMs=sum(r['report']['elapsedMs'] for r in rows if r['method']==name)) for name in methods},
                        elapsedSeconds=time.perf_counter()-started,productActivated=False,naturalQualityAccepted=False,normalPopulationFpr=None,finalQueriesInferred=0)
                    atomic_json(output/'summary.json',summary);atomic_json(output/'status.json',summary);print(json.dumps(summary));return
            except BlockingIOError:status('WAITING_SHARED_COMPUTE_SLOT');time.sleep(15)
    except Exception as failure:
        status('CONTEXTUAL_TEXT_FAILED',error=type(failure).__name__+': '+str(failure));raise


if __name__=='__main__':
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUTF8='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2');main()
