"""Diagnostic retrieval over the existing reference bank; no training or deployment."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import file_sha256,digest_json
from campus_shared.document_compute import document_slot
from campus_detection.retrieval import build_dense_index,load_dense_index,token_blocks,search_dense,hybrid_sources
from campus_detection.retrieval_model import load_retrieval_model,verified_identity
from corpus import read_jsonl
from run_document_evaluation import atomic_json

def main():
    import psutil,torch
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runtime/experiments') or output.exists():raise ValueError('Use a new project experiment directory')
    output.mkdir(parents=True)
    data=ROOT/'runtime/datasets/text-evaluation-corrected-20261028-v3'
    checkpoint=ROOT/'runtime/experiments/final-training-20261026/retriever-t2-v1/checkpoint-003126'
    run=checkpoint.parent;trained=json.loads((run/'status.json').read_text(encoding='utf-8'))
    if trained['state']!='AUXILIARY_TRAINING_COMPLETE' or trained['epochs']!=2 or not trained['reloadVerified']:raise ValueError('Require completed existing auxiliary training')
    hashes=json.loads((checkpoint/'READY').read_text(encoding='utf-8'))
    model_hashes={name.removeprefix('model/'):h for name,h in hashes.items() if name.startswith('model/')}
    verified_identity(checkpoint/'model',model_hashes,device='cuda',precision='BF16',batch_size=8)
    files={str(data/name):h for name,h in json.loads((data/'READY').read_text(encoding='utf-8')).items()}
    dependencies=[Path(__file__),ROOT/'app/training/run_document_evaluation.py',ROOT/'app/training/document_evaluation.py',ROOT/'app/python/campus_detection/retrieval.py',ROOT/'app/python/campus_detection/retrieval_model.py',ROOT/'app/python/campus_shared/document_compute.py']
    files.update({str(p):file_sha256(p) for p in dependencies})
    def guard():
        for name,h in files.items():
            if file_sha256(name)!=h:raise ValueError('Bound input or algorithm changed: '+name)
    guard()
    references=list(read_jsonl(data/'references.jsonl'))
    # The complete planned400 remains incomplete. Only already-built dev controls
    # are probed here; calibration/final queries never enter encoder inference.
    queries=[q for q in read_jsonl(data/'queries.jsonl') if q['split']=='dev']
    literal_path=ROOT/'runtime/experiments/final-training-20261028/literal-dev-controls-v1/predictions.jsonl'
    files[str(literal_path)]=file_sha256(literal_path)
    literal={q['queryId']:q for q in read_jsonl(literal_path)}
    if len(references)!=6311 or len(queries)!=75 or set(literal)!={q['queryId'] for q in queries}:raise ValueError('Existing diagnostic scope changed')
    for q in queries:
        if literal[q['queryId']]['querySha256']!=q['querySha256'] or literal[q['queryId']]['referenceManifestSha256']!=files[str(data/'references.jsonl')]:raise ValueError('Literal comparison input differs')
    previous_summary=ROOT/'runtime/experiments/final-training-20261028/literal-dev-controls-v1-metrics/summary.json'
    files[str(previous_summary)]=file_sha256(previous_summary)
    previous=json.loads(previous_summary.read_text(encoding='utf-8'))
    for k in [1,5,10,20,30]:
        count=sum(bool(set(q['expectedSourceIds']).intersection(x['sourceRevisionId'] for x in literal[q['queryId']]['candidateSources'][:k])) for q in queries)
        if count!=previous['rates'][f'correctSourceRecallAt{k}']['numerator']:raise ValueError('Previous literal ranks do not reproduce recorded counts')
    identity=dict(scope='EXISTING_PARTIAL_DEV_RETRIEVAL_DIAGNOSTIC',references=len(references),queries=len(queries),formalDevelopmentTarget=400,
        fullFormalDevelopmentReady=False,finalQueriesInferred=0,newTrainingSamples=0,checkpoint=str(checkpoint.relative_to(ROOT)),
        modelHashes=model_hashes,files={str(Path(p).relative_to(ROOT)):h for p,h in files.items()},device='cuda',precision='BF16',tokens=192,overlap=48,batch=8)
    atomic_json(output/'run.json',identity);started=time.perf_counter();encoded=0;source_encoded=0;query_done=0
    def status(state,**extra):atomic_json(output/'status.json',dict(state=state,referenceSources=6311,referenceBlocksEncoded=source_encoded,processed=query_done,total=75,elapsedSeconds=time.perf_counter()-started,trainingExpanded=False,productActivated=False,**extra))
    if args.preflight:
        status('PREFLIGHT_COMPLETE');print(json.dumps(dict(state='PREFLIGHT_COMPLETE',referenceSources=6311,developmentControls=75,formalTarget=400,checkpointFilesVerified=len(model_hashes),literalCountsReproduced=True,inferenceQueries=0)));return
    deadline=time.monotonic()+4*3600
    while True:
        guard()
        if time.monotonic()>deadline:raise TimeoutError('Finite diagnostic resource wait exceeded')
        if psutil.virtual_memory().available<1.5*1024**3 or not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<2*1024**3:
            status('WAITING_GPU_RESOURCE');time.sleep(15);continue
        try:
            with document_slot(ROOT/'runtime',neural=True):
                status('LOADING_EXISTING_BGE')
                session=load_retrieval_model(checkpoint/'model',expected_hashes=model_hashes,device='cuda',precision='BF16',batch_size=8)
                session['tokenizer'].model_max_length=10**8
                def encode(texts):
                    nonlocal encoded,source_encoded
                    result=session['encode'](texts);encoded+=len(texts)
                    if query_done==0:source_encoded=encoded
                    status('BUILDING_EXISTING_REFERENCE_INDEX');return result
                manifest=build_dense_index(references,session['tokenizer'],encode,output/'index',session['identity'],tokens=192,overlap=48,batch=8)
                source_encoded=manifest['blockCount'];index=load_dense_index(output/'index',session['identity'],tokens=192,overlap=48)
                rates={method:{k:0 for k in [1,5,10,20,30]} for method in ['literal','dense','hybrid']}
                with (output/'query-results.jsonl').open('w',encoding='utf-8') as stream:
                    for q in queries:
                        guard();blocks=token_blocks(q['query'],session['tokenizer'],192,48)
                        hits=search_dense(index,session['encode']([b['text'] for b in blocks]),top_k=30,distinct_sources=True,exclude_manuscript_id=q.get('queryManuscriptId'))
                        scores={}
                        for group in hits:
                            for hit in group:scores[hit['sourceRevisionId']]=max(scores.get(hit['sourceRevisionId'],-1.),hit['score'])
                        dense=[dict(sourceRevisionId=sid,score=score) for sid,score in sorted(scores.items(),key=lambda x:(-x[1],x[0]))[:30]]
                        old=literal[q['queryId']]['candidateSources'];hybrid=hybrid_sources(old,dense,30)
                        rankings={name:[r['sourceRevisionId'] for r in rows] for name,rows in [('literal',old),('dense',dense),('hybrid',hybrid)]}
                        expected=set(q['expectedSourceIds'])
                        for method,ids in rankings.items():
                            for k in rates[method]:rates[method][k]+=bool(expected.intersection(ids[:k]))
                        row=dict(queryId=q['queryId'],querySha256=q['querySha256'],category=q['category'],transformationKind=q['transformationKind'],rankings=rankings,expectedSourceIds=sorted(expected))
                        stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno());query_done+=1;status('RUNNING_EXISTING_RETRIEVAL_DIAGNOSTIC',completedReferenceBlocks=source_encoded)
                guard()
                summary=dict(state='EXISTING_RETRIEVAL_DIAGNOSTIC_COMPLETE',queries=75,referenceSources=6311,referenceBlocks=manifest['blockCount'],counts=rates,
                    scope=identity['scope'],formalDevelopmentTarget=400,fullFormalDevelopmentReady=False,finalQueriesInferred=0,
                    decisionAccuracy=None,falsePositiveRate=None,campusTrainingComplete=False,productActivated=False,elapsedSeconds=time.perf_counter()-started)
                atomic_json(output/'summary.json',summary);status(summary['state']);print(json.dumps(summary));return
        except BlockingIOError:
            status('WAITING_SHARED_COMPUTE_SLOT');time.sleep(15)

if __name__=='__main__':
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false')
    main()
