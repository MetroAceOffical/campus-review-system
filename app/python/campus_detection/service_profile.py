"""Immutable production profiles; all preparation/verification here is CPU only."""
import json
import re
import uuid
from pathlib import Path

from campus_detection import retrieval, task_model, v3_runtime
from campus_detection.models import configurations
from campus_detection.retrieval_model import verified_identity

ROOT=v3_runtime.ROOT
PROFILE_ROOT=ROOT/'runtime/delivery/text-profiles'


def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def profile_directory(profile_id):
    if not isinstance(profile_id,str) or str(uuid.UUID(profile_id))!=profile_id:
        raise ValueError('Select a canonical profile UUID')
    return v3_runtime.controlled(PROFILE_ROOT/profile_id)


def library_snapshot(generation):
    generation=str(generation)
    if not re.fullmatch(r'[1-9][0-9]*',generation):raise ValueError('Select a positive library generation')
    folder=v3_runtime.controlled(ROOT/'runtime/indexes'/generation);path=folder/'manifest.json'
    checksum=retrieval._sha(path)
    if (folder/'READY').read_text(encoding='utf-8').strip()!=checksum:raise ValueError('Business reference library is not READY')
    manifest=v3_runtime.read(path)
    if str(manifest.get('generationId'))!=generation:raise ValueError('Business library generation differs')
    documents=manifest['documents']
    if not isinstance(documents,list) or not documents:raise ValueError('Business reference library has no text documents')
    return {'generationId':generation,'manifestPath':str(path),'manifestSha256':checksum,
            'documentsDigest':retrieval._digest(documents)},manifest


def snapshot_references(generation,output):
    """Freeze the exact business documents, including source IDs, fields and order."""
    descriptor,library=library_snapshot(generation);output=v3_runtime.controlled(output)
    if output.exists():raise ValueError('Use a new immutable reference snapshot directory')
    output.mkdir(parents=True)
    with (output/'references.jsonl').open('w',encoding='utf-8') as stream:
        for document in library['documents']:stream.write(json.dumps(document,ensure_ascii=False)+'\n')
    write(output/'library.json',{**descriptor,'sourceFields':len(library['documents']),
                                'referencesSha256':retrieval._sha(output/'references.jsonl')})
    write(output/'READY',{name:retrieval._sha(output/name) for name in ('references.jsonl','library.json')})
    return v3_runtime.read(output/'library.json')


def _verified_material(spec):
    # No call to load_bundle/load_models: neural allocation is reserved for the
    # explicitly started detection service, never the Java delivery worker.
    bundle_folder=v3_runtime.controlled(spec['bundle']);bundle=v3_runtime.verify_bundle(bundle_folder)
    library,manifest=library_snapshot(spec['library']['generationId'])
    if library!=spec['library']:raise ValueError('Selected business reference generation changed')
    references=v3_runtime.controlled(bundle['references']['path'])
    with references.open(encoding='utf-8') as stream:documents=[json.loads(line) for line in stream if line.strip()]
    if retrieval._digest(documents)!=library['documentsDigest']:
        raise ValueError('Evaluation references cannot substitute for the selected business reference library')
    descriptor=bundle['retriever']
    identity=verified_identity(v3_runtime.controlled(descriptor['folder']),descriptor['files'])
    index_folder=v3_runtime.controlled(spec['index']);index=retrieval.load_dense_index(index_folder,identity)
    try:
        if index['manifest']['inputManifestSha256']!=library['documentsDigest']:raise ValueError('Dense index belongs to another business reference library')
        from campus_detection.v3_pipeline import _reference_context
        _reference_context(index,documents)
        calibration_folder=v3_runtime.controlled(spec['calibration']);v3_runtime.verify_files(calibration_folder)
        calibration=v3_runtime.read(calibration_folder/'calibration.json')
        export_folder=v3_runtime.controlled(bundle['reranker']['folder'])
        merged=v3_runtime.read(export_folder/'export-manifest.json')  # verify_bundle verified the entire export.
        session={'manifest':bundle,'reranker':{'configuration':task_model.configuration_for(export_folder,merged)}}
        base,image=configurations()
        if base['featureSpaceId']!=manifest['producerConfigs']['textConfig']['featureSpaceId']:
            raise ValueError('Business literal index requires a matching base feature space')
        text=v3_runtime.service_configuration(base,session,index,calibration)
        from campus_detection.release_quality import verify_quality
        quality=verify_quality(**{key:v3_runtime.controlled(spec['qualityEvidence'][key]) for key in
            ('protocol','evaluation','predictions','baseline','baseline_predictions')},calibration=calibration)
        files=dict(quality['verifiedFiles'])
        def add(path):
            path=Path(path).resolve()
            if not path.is_relative_to(ROOT):raise ValueError('Verified artifacts must stay inside this project')
            files[path.relative_to(ROOT).as_posix()]=retrieval._sha(path)
        def frozen(folder):
            add(folder/'READY')
            for name in v3_runtime.verify_files(folder):add(folder/name)
        for folder in (bundle_folder,export_folder,calibration_folder,
                       v3_runtime.controlled(calibration['developmentRun']),v3_runtime.controlled(calibration['developmentPredictions'])):frozen(folder)
        for component in ('retriever','reranker'):
            run=v3_runtime.controlled(bundle[component]['run'])
            add(run/'run.json');add(run/'status.json')
        for name in descriptor['files']:add(Path(descriptor['folder'])/name)
        for name in ('READY','manifest.json',*index['manifest']['files']):add(index_folder/name)
        add(references);add(Path(library['manifestPath']));add(Path(library['manifestPath']).parent/'READY')
        # The old literal/semantic branch remains a component of the combined report.
        lock=ROOT/'validation/text/round2/selection-lock.json';selected=v3_runtime.read(lock)
        weight=ROOT/'validation/text'/selected['selected']['bert']['artifact']
        if retrieval._sha(weight)!=base['weightSha256']:raise ValueError('Frozen BERT weight identity differs')
        for path in (weight,lock,ROOT/'validation/remaining/text/selection.json',
                     ROOT/'validation/text/models/bert-base-chinese/tokenizer.json',
                     ROOT/'validation/remaining/image/models/dinov2-small/preprocessor_config.json',
                     ROOT/'validation/remaining/image/evaluation/selection.json'):add(path)
        for name in ('service_profile.py','http_service.py','release_quality.py','v3_runtime.py','v3_pipeline.py',
                     'v3_delivery.py','retrieval.py','retrieval_model.py','task_model.py','alignment.py','aggregation.py',
                     'models.py','text.py','semantic.py'):add(ROOT/'app/python/campus_detection'/name)
        return {'textConfig':text,'imageConfig':image,'quality':quality['metrics'],'verifiedFiles':files}
    finally:
        if hasattr(index['vectors'],'_mmap'):index['vectors']._mmap.close()


def create_profile(*,name,generation,bundle,index,calibration,quality_evidence):
    if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Profile name must contain 1..100 characters')
    library,_=library_snapshot(generation)
    spec={'schemaVersion':'campus-v3-service-profile-v1','profileId':str(uuid.uuid4()),'name':name.strip(),
          'library':library,'bundle':str(v3_runtime.controlled(bundle)),'index':str(v3_runtime.controlled(index)),
          'calibration':str(v3_runtime.controlled(calibration)),
          'qualityEvidence':{key:str(v3_runtime.controlled(value)) for key,value in quality_evidence.items()}}
    spec.update(_verified_material(spec))
    folder=profile_directory(spec['profileId']);folder.mkdir(parents=True,exist_ok=False)
    write(folder/'profile.json',spec)
    write(folder/'READY',{'profile.json':retrieval._sha(folder/'profile.json')})
    return spec


def verify_profile(profile_id):
    folder=profile_directory(profile_id);ready=v3_runtime.verify_files(folder)
    if set(ready)!={'profile.json'}:raise ValueError('Unexpected profile components')
    spec=v3_runtime.read(folder/'profile.json')
    if spec.get('schemaVersion')!='campus-v3-service-profile-v1' or spec.get('profileId')!=profile_id:
        raise ValueError('Profile identity differs')
    for name,checksum in spec['verifiedFiles'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or retrieval._sha(path)!=checksum:raise ValueError('Profile dependency changed: '+name)
    material=_verified_material(spec)
    if any(spec[key]!=material[key] for key in material):raise ValueError('Profile configuration/evidence differs from its artifacts')
    files={**material['verifiedFiles'],**{(folder/name).relative_to(ROOT).as_posix():retrieval._sha(folder/name) for name in ('profile.json','READY')}}
    return {**spec,'verifiedFiles':files,'profileSha256':retrieval._sha(folder/'profile.json'),
            'libraryGenerationId':spec['library']['generationId'],'libraryManifestSha256':spec['library']['manifestSha256']}


def candidates():
    items=[]
    if PROFILE_ROOT.exists():
        for folder in sorted(PROFILE_ROOT.iterdir()):
            try:
                if not folder.is_dir() or profile_directory(folder.name)!=folder.resolve():continue
                files=v3_runtime.verify_files(folder);spec=v3_runtime.read(folder/'profile.json')
                if set(files)!={'profile.json'} or spec.get('profileId')!=folder.name or spec.get('schemaVersion')!='campus-v3-service-profile-v1':continue
                items.append({'profileId':folder.name,'name':spec['name'],'libraryGenerationId':spec['library']['generationId']})
            except (ValueError,KeyError,TypeError,OSError):continue
    return {'items':items}
