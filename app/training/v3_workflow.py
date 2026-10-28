"""Explicit model registration, index, calibration features and resumable real predictions."""
import argparse,hashlib,json,sqlite3,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection import v3_runtime as runtime,retrieval,v3_pipeline,aggregation
from campus_detection.v3_delivery import prediction_record
from campus_workbench.training import compute_slot
from corpus import read_jsonl
from evaluate_final import select_protocol_queries,validate_evaluation_scale,split_digest,validate_development_evidence


def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def freeze(folder,names):write(folder/'READY',{name:retrieval._sha(folder/name) for name in names})


def calibration_identity(package):
    return retrieval._digest({key:package[key] for key in ('featureConfig','calibrator','referenceManifestSha256','thresholds','policy')})


def implementation():
    paths=[Path(__file__),ROOT/'app/training/evaluate_final.py',ROOT/'app/training/text_evaluation.py']
    paths += [ROOT/'app/python/campus_detection'/name for name in ('v3_runtime.py','v3_delivery.py','v3_pipeline.py','text.py','semantic.py','models.py','retrieval.py','retrieval_model.py','task_model.py','alignment.py','aggregation.py')]
    return {p.relative_to(ROOT).as_posix():retrieval._sha(p) for p in paths}


def ready_queries(protocol,split,diagnostic=False):
    runtime.verify_files(protocol);manifest=runtime.read(protocol/'manifest.json');queries=list(read_jsonl(protocol/'queries.jsonl'))
    if split=='calibration':
        rows=[r for r in queries if r['split']==split];count=manifest['splitCounts'][split]
        if diagnostic or len(rows)!=200 or count['pending'] or count['constructed']!=200:raise ValueError('Calibration requires the full200 constructed queries, including supported negative truth')
        return rows
    if split=='final' and diagnostic:raise ValueError('Final controls cannot be inspected during development')
    if split=='final' and manifest['splitCounts'][split].get('homeTargetMetForPlan') is not True:raise ValueError('Final NCUC coverage has not met the unchanged60% plan; add heldout sources')
    rows=select_protocol_queries(manifest,queries,split,diagnostic);validate_evaluation_scale(split,len(rows),diagnostic)
    return rows


def predict(args):
    protocol=runtime.controlled(args.protocol);queries=ready_queries(protocol,args.split,args.diagnostic_controls)
    # Validate all original-range truth and closed negative scope before loading
    # models. Discard this empty-prediction validation result; it is not a grade.
    from text_evaluation import score_predictions
    score_predictions(queries,[],list(read_jsonl(protocol/'references.jsonl')),'truth-validation-only',
        reference_sha256=retrieval._sha(protocol/'references.jsonl'),bootstrap_resamples=1)
    calibration=None
    if args.calibration:
        runtime.verify_files(args.calibration);calibration=runtime.read(args.calibration/'calibration.json')
    if args.split!='calibration' and not calibration:raise ValueError('Scored v3 predictions require real fitted calibration')
    reference_sha=retrieval._sha(protocol/'references.jsonl');bundle=runtime.verify_bundle(args.bundle)
    if bundle['references']['sha256']!=reference_sha:raise ValueError('Model bundle and protocol reference banks differ')
    if args.split=='final' and (not args.development_run or calibration.get('operatingPointFrozen') is not True):raise ValueError('Final needs full development evidence and frozen operating point')
    output=runtime.controlled(args.output)
    if output.exists() and not args.resume:raise ValueError('Existing predictions require explicit unchanged-identity resume')
    if (output/'READY').exists():
        runtime.verify_files(output)
        raise ValueError('Predictions already frozen; use evaluate_final.py to score the saved export')
    with compute_slot(ROOT/'runtime',args.device=='cuda'):
        session=runtime.load_bundle(args.bundle,device=args.device,precision='BF16' if args.device=='cuda' else 'FP32',batch_size=args.batch_size)
        index=retrieval.load_dense_index(args.index,session['retriever']['identity'])
        try:
            # Keep the exact existing literal branch and source acceptance policy.
            from campus_detection.models import load_models
            if args.device!='cuda':raise ValueError('Full v2/v3 joint export requires existing CUDA literal-model runtime; CPU index building remains supported')
            legacy=load_models()
            # Legacy indexes use a globally unique sourceKey; v3 indexes use
            # revision+field. Adapt at this boundary without changing either.
            legacy_documents=[{**row,'sourceKey':str(row['sourceRevisionId'])+':'+row.get('sourceKey','BODY')} for row in session['documents']]
            original_fields={r['sourceKey']:source.get('sourceKey','BODY') for r,source in zip(legacy_documents,session['documents'])}
            library={'generationId':'1','documents':legacy_documents,'images':[]}
            feature_config=v3_pipeline.configuration_for(index,session['reranker'],calibration.get('policy') if calibration else None)[2]
            if calibration:
                if calibration['referenceManifestSha256']!=reference_sha or calibration['featureConfig']!=feature_config:raise ValueError('Calibration/query model identities differ')
                aggregation.validate_calibrator(calibration['calibrator'],feature_config,calibration['thresholds'])
            method='v3-method-'+retrieval._digest({'bundle':bundle['bundleId'],'indexManifest':retrieval._sha(args.index/'manifest.json'),
                'calibration':calibration_identity(calibration) if calibration else None,'legacy':legacy['textConfig']['configId'],
                'features':feature_config,'implementation':implementation()})
            dev_sha=None
            if args.split=='final':
                runtime.verify_files(args.development_run);devrun=runtime.read(args.development_run/'run.json');summary=runtime.read(args.development_run/'summary.json')
                dev_queries=ready_queries(protocol,'dev')
                validate_development_evidence(devrun,summary,split_digest(dev_queries),reference_sha,method,400);dev_sha=retrieval._sha(args.development_run/'READY')
                if calibration.get('developmentEvidenceSha256')!=dev_sha or calibration.get('developmentMethodConfigId')!=method:raise ValueError('Working-point freeze belongs to another development run')
            run={'protocolReadySha256':retrieval._sha(protocol/'READY'),'splitQueriesSha256':split_digest(queries),
                'referenceManifestSha256':reference_sha,'methodConfigId':method,'split':args.split,'diagnosticControls':args.diagnostic_controls,
                'variant':'full-v3' if calibration else 'candidate-v3-calibration-features','campusRetrieverTrainingComplete':True,
                'correspondenceTrainingComplete':True,'formalCalibrationFrozen':bool(calibration),
                'operatingPointFrozen':bool(calibration and calibration.get('operatingPointFrozen')),
                'developmentEvidenceSha256':dev_sha,'featureConfig':feature_config,'implementation':implementation(),
                'calibrationIdentity':calibration_identity(calibration) if calibration else None,
                'calibrationPackageSha256':retrieval._sha(args.calibration/'calibration.json') if calibration else None}
            output.mkdir(parents=True,exist_ok=True)
            if (output/'run.json').exists() and runtime.read(output/'run.json')!=run:raise ValueError('Prediction resume identity changed')
            write(output/'run.json',run)
            db=sqlite3.connect(output/'predictions.sqlite');db.execute('CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,result TEXT NOT NULL)')
            from campus_detection.text import detect_text
            for number,query in enumerate(queries,1):
                if db.execute('SELECT 1 FROM predictions WHERE id=?',(query['queryId'],)).fetchone():continue
                started=time.perf_counter()
                try:
                    request={'taskId':query['queryId'],'attemptId':query['queryId'],'scene':'EXTERNAL','inputSnapshotKey':query['queryId'],
                        'inputSha256':query['querySha256'],'libraryGenerationId':'1','configId':legacy['textConfig']['configId'],
                        'text':query['query'],'excludeManuscriptId':query.get('queryManuscriptId')}
                    excluded=set(query.get('negativeScope',{}).get('excludedSourceRevisionIds',[]))
                    query_library=library
                    if excluded:
                        from campus_detection.text import prepare_text_index
                        if '_textIndex' not in library:library['_textIndex']=prepare_text_index(library,legacy)
                        query_library={**library,'documents':[r for r in library['documents'] if r['sourceRevisionId'] not in excluded]}
                    literal=detect_text(request,query_library,legacy)
                    for item in literal['evidence']:item['sourceKey']=original_fields[item['sourceKey']]
                    result=runtime.analyze(session,index,query['query'],literal_hits=literal['evidence'],exclude_manuscript_id=query.get('queryManuscriptId'),exclude_source_revision_ids=excluded,calibration=calibration)
                    record=prediction_record(query,result,method,reference_sha,literal)
                    record['elapsedMs']=(time.perf_counter()-started)*1000
                    record['sourceFeatures']=result['aggregation']['sources']
                except Exception as error:
                    record=prediction_record(query,{'coverageStatus':'FAILED','elapsedMs':(time.perf_counter()-started)*1000,'failures':[{'errorType':type(error).__name__,'message':str(error)[:300]}]},method,reference_sha)
                db.execute('INSERT INTO predictions VALUES(?,?)',(query['queryId'],json.dumps(record,ensure_ascii=False)));db.commit()
                write(output/'status.json',{'state':'PREDICTING','processed':db.execute('SELECT count(*) FROM predictions').fetchone()[0],'total':len(queries),'qualityAccepted':False})
            with (output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
                for query in queries:stream.write(db.execute('SELECT result FROM predictions WHERE id=?',(query['queryId'],)).fetchone()[0]+'\n')
            db.close();freeze(output,['run.json','predictions.jsonl','predictions.sqlite'])
            write(output/'status.json',{'state':'REAL_PREDICTIONS_EXPORTED','queries':len(queries),'qualityAccepted':False})
        finally:
            if hasattr(index['vectors'],'_mmap'):index['vectors']._mmap.close()
    if args.split in {'dev','final'}:
        command=[sys.executable,'-B',str(ROOT/'app/training/evaluate_final.py'),'--protocol',str(protocol),'--predictions',str(output),'--method-config-id',method,'--split',args.split,'--output',str(output.with_name(output.name+'-metrics'))]
        if args.diagnostic_controls:command.append('--diagnostic-controls')
        if args.development_run:command.extend(['--development-run',str(args.development_run)])
        subprocess.run(command,cwd=ROOT,check=True)


def calibrate(args):
    queries=ready_queries(args.protocol,'calibration');runtime.verify_files(args.features);run=runtime.read(args.features/'run.json')
    if run.get('split')!='calibration' or run['splitQueriesSha256']!=split_digest(queries) or run['protocolReadySha256']!=retrieval._sha(args.protocol/'READY'):raise ValueError('Calibration features belong to another protocol')
    predictions={r['queryId']:r for r in read_jsonl(args.features/'predictions.jsonl')};rows=[]
    partition_hashes=runtime.verify_files(args.partitions)
    if runtime.read(args.protocol/'manifest.json')['partitionHashes']!=partition_hashes:raise ValueError('Calibration source partitions differ from protocol')
    allowed={r['eventClusterId'] for r in read_jsonl(args.partitions/'calibration.jsonl')}
    forbidden={r['eventClusterId'] for split in ('train','dev','final') for r in read_jsonl(args.partitions/(split+'.jsonl'))}
    reference_sha=retrieval._sha(args.protocol/'references.jsonl');references={str(r['sourceRevisionId']) for r in read_jsonl(args.protocol/'references.jsonl')}
    for query in queries:
        prediction=predictions.get(query['queryId'],{})
        if prediction.get('coverageStatus')!='COMPLETE' or prediction.get('querySha256')!=query['querySha256'] or prediction.get('methodConfigId')!=run['methodConfigId'] or not set(query['eventClusterIds'])<=allowed:raise ValueError('Calibration features incomplete, failed or cross partition')
        if prediction.get('referenceManifestSha256')!=reference_sha:raise ValueError('Calibration reference identity differs')
        expected=set(query['expectedSourceIds']);negative=query.get('negativeScope',{})
        if not expected and (query['truthScope']!='closed_reference_set' or negative.get('auditVerified') is not True or negative.get('referenceManifestSha256')!=reference_sha or set(negative.get('supportedNegativeSources',[]))!=references-set(negative.get('excludedSourceRevisionIds',[]))):raise ValueError('Normal calibration truth does not cover the frozen bank')
        features={(str(r['sourceRevisionId']),r.get('sourceKey','BODY')):r['features'] for r in prediction.get('sourceFeatures',[])}
        for source in expected if expected else {key[0] for key in features}:
            values=features.get((source,'BODY'),{name:0. for name in aggregation.FEATURE_NAMES})
            rows.append({'split':'calibration','queryEventClusterId':query['eventClusterIds'][0],'queryEventClusterIds':query['eventClusterIds'],
                'featureConfigSha256':aggregation._feature_identity(run['featureConfig']),'features':values,
                'wholeTarget':int(bool(expected) and query['category'] in {'whole_synonym','whole_reordered','copy_control'}),
                'localTarget':int(bool(expected)),'labelOrigin':query['labelOrigin'],'labelConfidence':query['labelConfidence'],
                'negativeBasis':query.get('negativeBasis') or {},'queryId':query['queryId'],'sourceRevisionId':source})
    fitted=aggregation.fit_calibrator(rows,run['featureConfig'],partition_hashes['calibration.jsonl'],forbidden_events=forbidden,calibration_events=allowed)
    output=runtime.controlled(args.output)
    if output.exists():raise ValueError('Use a new calibration package')
    thresholds={'whole':args.whole_threshold,'local':args.local_threshold};aggregation.validate_calibrator(fitted,run['featureConfig'],thresholds)
    output.mkdir(parents=True);write(output/'calibration.json',{'featureConfig':run['featureConfig'],'calibrator':fitted,
        'referenceManifestSha256':reference_sha,'thresholds':thresholds,'policy':None,
        'operatingPointFrozen':False,'state':'FITTED_WORKING_POINT_REQUIRES_DEVELOPMENT','sourceFeaturesReadySha256':retrieval._sha(args.features/'READY')})
    freeze(output,['calibration.json'])


def freeze_point(args):
    for folder in (args.calibration,args.development_predictions,args.development_run):runtime.verify_files(folder)
    package=runtime.read(args.calibration/'calibration.json');pred=runtime.read(args.development_predictions/'run.json')
    run=runtime.read(args.development_run/'run.json');summary=runtime.read(args.development_run/'summary.json')
    if pred.get('split')!='dev' or pred.get('diagnosticControls') is not False or pred.get('calibrationIdentity')!=calibration_identity(package):raise ValueError('Development predictions do not use this calibration/working point')
    if run.get('predictionReadySha256')!=retrieval._sha(args.development_predictions/'READY'):raise ValueError('Development scoring belongs to different predictions')
    validate_development_evidence(run,summary,pred['splitQueriesSha256'],package['referenceManifestSha256'],pred['methodConfigId'],400)
    output=runtime.controlled(args.output)
    if output.exists():raise ValueError('Freeze working point in a new package')
    output.mkdir(parents=True);write(output/'calibration.json',{**package,'operatingPointFrozen':True,
        'state':'WORKING_POINT_FROZEN_AFTER_FULL_DEVELOPMENT','developmentEvidenceSha256':retrieval._sha(args.development_run/'READY'),
        'developmentMethodConfigId':pred['methodConfigId'],'developmentRun':str(args.development_run.resolve()),
        'developmentPredictions':str(args.development_predictions.resolve())});freeze(output,['calibration.json'])


def readiness(args):
    recipe=runtime.read(args.recipe);protocol=runtime.controlled(args.protocol);runtime.verify_files(protocol)
    manifest=runtime.read(protocol/'manifest.json');paths={k:runtime.controlled(v) for k,v in recipe['paths'].items()}
    models={}
    for name,key,complete in [('bge','retrieverRun','CAMPUS_RETRIEVAL_TRAINING_COMPLETE'),('m3','correspondenceRun','CORRESPONDENCE_TRAINING_COMPLETE')]:
        path=paths[key]/'status.json';status=runtime.read(path) if path.exists() else {'state':'NOT_STARTED'}
        models[name]={'state':status.get('state'),'epochs':status.get('epochs'),'reloadVerified':status.get('reloadVerified') is True,
            'completed':status.get('state')==complete and status.get('epochs')==2 and status.get('reloadVerified') is True}
    export_ready=False
    if (paths['export']/'READY').exists():
        from campus_detection.task_model import verify_export
        verify_export(paths['export']);export_ready=True
    status={'state':'MODELS_READY_FOR_EXPLICIT_REGISTRATION' if all(m['completed'] for m in models.values()) and export_ready else 'MODEL_ARTIFACTS_PENDING',
        'models':models,'mergedExportVerified':export_ready,'protocolQueries':manifest['splitCounts'],
        'requestedQueries':1800,'constructedQueries':manifest['constructedQueries'],'pendingQueries':manifest['pendingSlots'],
        'fullQuerySetReady':manifest['fullQuerySetReady'],'homeCoverageComplete':all(r['homeTargetMetForPlan'] for r in manifest['splitCounts'].values()),
        'recipeSha256':retrieval._sha(args.recipe),'protocolReadySha256':retrieval._sha(protocol/'READY'),
        'dataOrEpochsReduced':False,'predictionExecuted':False,'qualityAccepted':False,'productActivated':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);write(args.output,status);print(json.dumps(status,ensure_ascii=False))


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    reg=sub.add_parser('register');reg.add_argument('--retriever-run',type=Path,required=True);reg.add_argument('--correspondence-run',type=Path,required=True);reg.add_argument('--export',type=Path,required=True);reg.add_argument('--references',type=Path,required=True);reg.add_argument('--output',type=Path,required=True)
    index=sub.add_parser('index');index.add_argument('--bundle',type=Path,required=True);index.add_argument('--output',type=Path,required=True);index.add_argument('--device',choices=['cpu','cuda'],default='cuda');index.add_argument('--batch-size',type=int,default=8)
    pred=sub.add_parser('predict');pred.add_argument('--bundle',type=Path,required=True);pred.add_argument('--index',type=Path,required=True);pred.add_argument('--protocol',type=Path,required=True);pred.add_argument('--output',type=Path,required=True);pred.add_argument('--split',choices=['calibration','dev','final'],required=True);pred.add_argument('--calibration',type=Path);pred.add_argument('--development-run',type=Path);pred.add_argument('--diagnostic-controls',action='store_true');pred.add_argument('--resume',action='store_true');pred.add_argument('--device',choices=['cpu','cuda'],default='cuda');pred.add_argument('--batch-size',type=int,default=8)
    cal=sub.add_parser('calibrate');cal.add_argument('--protocol',type=Path,required=True);cal.add_argument('--partitions',type=Path,required=True);cal.add_argument('--features',type=Path,required=True);cal.add_argument('--output',type=Path,required=True)
    cal.add_argument('--whole-threshold',type=float,default=.5);cal.add_argument('--local-threshold',type=float,default=.5)
    point=sub.add_parser('freeze-point');point.add_argument('--calibration',type=Path,required=True);point.add_argument('--development-predictions',type=Path,required=True);point.add_argument('--development-run',type=Path,required=True);point.add_argument('--output',type=Path,required=True)
    state=sub.add_parser('status');state.add_argument('--recipe',type=Path,required=True);state.add_argument('--protocol',type=Path,required=True);state.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    for value in vars(args).values():
        if isinstance(value,Path):runtime.controlled(value)
    if args.action=='register':print(json.dumps(runtime.register_bundle(args.retriever_run,args.correspondence_run,args.export,args.references,args.output),ensure_ascii=False))
    elif args.action=='index':
        with compute_slot(ROOT/'runtime',args.device=='cuda'):
            # Index construction needs only BGE, not the M3 or old BERT models.
            from campus_detection.retrieval_model import load_retrieval_model
            bundle=runtime.verify_bundle(args.bundle);descriptor=bundle['retriever'];encoder=load_retrieval_model(descriptor['folder'],expected_hashes=descriptor['files'],device=args.device,precision='BF16' if args.device=='cuda' else 'FP32',batch_size=args.batch_size)
            retrieval.build_dense_index(list(read_jsonl(Path(bundle['references']['path']))),encoder['tokenizer'],encoder['encode'],args.output,encoder['identity'])
    elif args.action=='predict':predict(args)
    elif args.action=='calibrate':calibrate(args)
    elif args.action=='freeze-point':freeze_point(args)
    else:readiness(args)


if __name__=='__main__':main()
