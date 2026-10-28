"""Explicit v3 artifact registration/loading. Never trains or changes an active profile."""
import hashlib
import json
import re
from pathlib import Path
from campus_detection import retrieval,task_model,v3_pipeline

ROOT=Path(__file__).resolve().parents[3]


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def controlled(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'runtime'):raise ValueError('Model integration paths must stay in project runtime')
    return path


def verify_files(folder):
    folder=controlled(folder);files=read(folder/'READY')
    if not isinstance(files,dict) or not files:raise ValueError('Require a nonempty frozen file manifest')
    for name,expected in files.items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or not re.fullmatch('[0-9a-f]{64}',expected) or retrieval._sha(path)!=expected:raise ValueError('Frozen component changed: '+name)
    return files


def register_bundle(retriever_run,correspondence_run,export,references,output):
    retriever_run=controlled(retriever_run);correspondence_run=controlled(correspondence_run);export=controlled(export);references=controlled(references);output=controlled(output)
    status=read(retriever_run/'status.json');cfg=read(retriever_run/'run.json')
    if status.get('state')!='CAMPUS_RETRIEVAL_TRAINING_COMPLETE' or status.get('epochs')!=2 or status.get('reloadVerified') is not True:
        raise ValueError('Campus BGE training/reload not complete; auxiliary weights are not a campus model')
    if cfg.get('epochs')!=2 or cfg.get('trainGroups',0)<1000 or cfg.get('effectiveQueries')!=32 or cfg.get('maxTokensPerSide')!=512:
        raise ValueError('Campus BGE formal scale/configuration differs')
    name=status.get('checkpoint','')
    if not re.fullmatch(r'checkpoint-\d{6}',name):raise ValueError('Invalid completed BGE checkpoint')
    checkpoint=retriever_run/name;files=verify_files(checkpoint)
    m3status=read(correspondence_run/'status.json');m3cfg=read(correspondence_run/'run.json')
    if m3status.get('state')!='CORRESPONDENCE_TRAINING_COMPLETE' or m3status.get('epochs')!=2 or m3status.get('reloadVerified') is not True or m3cfg.get('pairCount',0)<20000 or m3cfg.get('epochs')!=2:
        raise ValueError('Formal M3 training/reload not complete')
    merged=task_model.verify_export(export)
    if merged['trainingRunSha256']!=retrieval._sha(correspondence_run/'run.json') or merged['trainingStatusSha256']!=retrieval._sha(correspondence_run/'status.json'):
        raise ValueError('Merged export belongs to a different completed M3 run')
    manifest={'schemaVersion':'campus-v3-model-bundle-v1','taskType':'CONTENT_CORRESPONDENCE',
        'retriever':{'folder':str(checkpoint/'model'),'files':{k[6:]:v for k,v in files.items() if k.startswith('model/')},
            'run':str(retriever_run),'runSha256':retrieval._sha(retriever_run/'run.json'),'statusSha256':retrieval._sha(retriever_run/'status.json')},
        'reranker':{'folder':str(export),'exportId':merged['exportId'],'exportManifestSha256':retrieval._sha(export/'export-manifest.json'),
            'run':str(correspondence_run),'runSha256':retrieval._sha(correspondence_run/'run.json'),'statusSha256':retrieval._sha(correspondence_run/'status.json')},
        'references':{'path':str(references),'sha256':retrieval._sha(references)},
        'campusRetrieverTrainingComplete':True,'correspondenceTrainingComplete':True,
        'formalCalibrationFrozen':False,'productActivated':False}
    manifest['bundleId']='v3-bundle-'+retrieval._digest(manifest)
    if output.exists():raise ValueError('Use a new immutable model bundle')
    output.mkdir(parents=True);(output/'bundle.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'READY').write_text(json.dumps({'bundle.json':retrieval._sha(output/'bundle.json')}),encoding='utf-8')
    return manifest


def verify_bundle(folder):
    folder=controlled(folder);verify_files(folder);manifest=read(folder/'bundle.json')
    if manifest.get('schemaVersion')!='campus-v3-model-bundle-v1' or manifest.get('bundleId')!='v3-bundle-'+retrieval._digest({k:v for k,v in manifest.items() if k!='bundleId'}):raise ValueError('Model bundle identity differs')
    for name in ('retriever','reranker'):
        descriptor=manifest[name];run=controlled(descriptor['run'])
        if retrieval._sha(run/'run.json')!=descriptor['runSha256'] or retrieval._sha(run/'status.json')!=descriptor['statusSha256']:raise ValueError('Completed training identity changed')
    source=controlled(manifest['references']['path'])
    if retrieval._sha(source)!=manifest['references']['sha256']:raise ValueError('Reference bank changed')
    for name,expected in manifest['retriever']['files'].items():
        path=controlled(manifest['retriever']['folder'])/name
        if path.resolve().parent!=controlled(manifest['retriever']['folder']) or retrieval._sha(path)!=expected:raise ValueError('BGE component changed')
    merged=task_model.verify_export(controlled(manifest['reranker']['folder']),manifest['reranker']['exportId'])
    if retrieval._sha(Path(manifest['reranker']['folder'])/'export-manifest.json')!=manifest['reranker']['exportManifestSha256']:raise ValueError('M3 export manifest changed')
    return manifest


def load_bundle(folder,*,device='cuda',precision='BF16',batch_size=8):
    from campus_detection.retrieval_model import load_retrieval_model
    manifest=verify_bundle(folder)
    retriever=load_retrieval_model(manifest['retriever']['folder'],expected_hashes=manifest['retriever']['files'],device=device,precision=precision,batch_size=batch_size)
    reranker=task_model.load_correspondence_model(manifest['reranker']['folder'],expected_export_id=manifest['reranker']['exportId'],device=device,precision=precision)
    with Path(manifest['references']['path']).open(encoding='utf-8') as stream:documents=[json.loads(line) for line in stream if line.strip()]
    return {'manifest':manifest,'retriever':retriever,'reranker':reranker,'documents':documents}


def service_configuration(base,session,index,calibration):
    """Validate the frozen working point without loading neural weights."""
    references_sha=session['manifest']['references']['sha256']
    if calibration.get('referenceManifestSha256')!=references_sha:raise ValueError('Calibration belongs to another reference bank')
    if calibration.get('operatingPointFrozen') is not True:raise ValueError('Service profile requires a frozen development working point')
    development=controlled(calibration['developmentRun']);predictions=controlled(calibration['developmentPredictions'])
    verify_files(development);verify_files(predictions)
    devrun=read(development/'run.json');summary=read(development/'summary.json');predrun=read(predictions/'run.json')
    if retrieval._sha(development/'READY')!=calibration.get('developmentEvidenceSha256') or devrun.get('predictionReadySha256')!=retrieval._sha(predictions/'READY'):
        raise ValueError('Frozen development evidence changed')
    identity=retrieval._digest({key:calibration[key] for key in ('featureConfig','calibrator','referenceManifestSha256','thresholds','policy')})
    if devrun.get('split')!='dev' or devrun.get('diagnosticControls') is not False or summary.get('evaluationScope')!='FORMAL_PROTOCOL' or summary.get('queries')!=400 or summary.get('missingPredictions')!=0:
        raise ValueError('Service activation requires complete400 development evidence')
    if predrun.get('calibrationIdentity')!=identity or devrun.get('methodConfigId')!=calibration.get('developmentMethodConfigId') or devrun.get('referenceManifestSha256')!=references_sha:
        raise ValueError('Frozen development method/working point differs')
    from campus_detection.aggregation import validate_calibrator
    _,_,features=v3_pipeline.configuration_for(index,session['reranker'],calibration.get('policy'))
    if features!=calibration.get('featureConfig'):raise ValueError('Selected index/task/policy differ from calibration features')
    validate_calibrator(calibration['calibrator'],features,calibration['thresholds'])
    configuration={**base,'schemaVersion':'text-v3','method':'campus-correspondence-v3','baseConfigId':base['configId'],
        'bundleId':session['manifest']['bundleId'],'denseFeatureSpaceId':index['manifest']['featureSpaceId'],
        'calibrationSha256':retrieval._digest(calibration)}
    configuration.pop('configId');configuration['configId']='text-'+retrieval._digest(configuration)
    return configuration


def attach_runtime(models,session,index,calibration):
    """Expose an explicit v3 choice while preserving the default v2 service."""
    base=models['textConfig'];configuration=service_configuration(base,session,index,calibration)
    return {**models,'textConfigs':{**models['textConfigs'],configuration['configId']:configuration},
        'v3Runtime':{**session,'index':index,'calibration':calibration,'baseConfigId':base['configId'],'configId':configuration['configId']}}


def analyze(session,index,text,*,literal_hits=(),exclude_manuscript_id=None,exclude_source_revision_ids=(),calibration=None):
    if calibration and calibration['referenceManifestSha256']!=session['manifest']['references']['sha256']:raise ValueError('Calibration reference bank differs')
    result=v3_pipeline.analyze_correspondence(text,index,session['documents'],session['retriever'],session['reranker'],
        literal_hits=literal_hits,exclude_manuscript_id=exclude_manuscript_id,exclude_source_revision_ids=exclude_source_revision_ids,
        policy=calibration.get('policy') if calibration else None,calibrator=calibration.get('calibrator') if calibration else None,
        thresholds=calibration.get('thresholds') if calibration else None)
    if calibration and result['featureConfig']!=calibration['featureConfig']:raise ValueError('Calibration execution features differ')
    return result


def detect(request,library,models):
    from campus_detection.text import detect_text
    from campus_detection.v3_delivery import merge_report
    runtime=models['v3Runtime']
    if request['configId']!=runtime['configId']:raise ValueError('Requested v3 configuration is not loaded')
    selected=models['textConfigs'][request['configId']]
    if retrieval._digest(library['documents'])!=runtime['index']['manifest']['inputManifestSha256']:raise ValueError('This reference generation requires a matching v3 index/calibration')
    base_request={**request,'configId':runtime['baseConfigId']}
    base_models={**models,'textConfig':models['textConfigs'][runtime['baseConfigId']]}
    literal=detect_text(base_request,library,base_models)
    if literal['status']=='NOT_APPLICABLE':return {**literal,'configId':request['configId'],'actualConfig':selected}
    result=analyze(runtime,runtime['index'],request['text'],literal_hits=literal['evidence'],exclude_manuscript_id=request.get('excludeManuscriptId'),calibration=runtime['calibration'])
    report=merge_report(literal,result,library['documents']);report['configId']=request['configId'];report['actualConfig']=selected
    return report
