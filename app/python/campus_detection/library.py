"""Build an immutable generation in a new directory; database activation belongs to Java."""
import json
from pathlib import Path
from campus_shared.contracts import ContractError,controlled_file,digest_json,file_sha256
from campus_detection.models import ROOT

def artifact_cache_key(file_sha,config):return digest_json({'fileSha256':file_sha,'producerConfig':config})

def validate_feature_space(artifact,config):
    if artifact.get('featureSpaceId')!=config.get('featureSpaceId'):raise ContractError('INCOMPATIBLE_FEATURE_SPACE','Feature spaces differ; rebuild the affected index')

def validate_image_feature(artifact):
    import numpy as np
    vector=np.asarray(artifact.get('vector',[]),dtype=np.float32)
    if vector.shape!=(384,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector),1,atol=1e-4):
        raise ContractError('INVALID_IMAGE_FEATURE','Cached DINO vector is invalid')

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8');temporary.replace(path)

def build_library(manifest,config):
    from campus_detection.image import encode_images
    from campus_detection.text import prepare_text_index
    import joblib
    models=config['models'];generation=str(manifest['generationId'])
    if not generation.isdecimal() or int(generation)<1:raise ContractError('INVALID_LIBRARY_ID','Invalid generation identity')
    root=Path(config.get('indexRoot',ROOT/'runtime/indexes')).resolve()
    cache=Path(config.get('cacheRoot',ROOT/'runtime/derived/image-features')).resolve()
    if not root.is_relative_to(ROOT/'runtime') or not cache.is_relative_to(ROOT/'runtime'):raise ContractError('FILE_OUTSIDE_ROOT','Index and cache roots must stay within project runtime')
    directory=root/generation;directory.mkdir(parents=True,exist_ok=True)
    target=directory/'manifest.json';ready=directory/'READY';input_hash=digest_json(manifest)
    if ready.exists():
        if not target.is_file() or file_sha256(target)!=ready.read_text().strip():raise ContractError('INDEX_CORRUPT','Existing READY generation is corrupt')
        previous=json.loads(target.read_text(encoding='utf-8'))
        if previous.get('inputManifestHash')!=input_hash:raise ContractError('IMMUTABLE_GENERATION','Cannot overwrite a READY generation with different input')
        return {'status':'READY','generationId':generation,'manifestPath':str(target),'manifestSha256':file_sha256(target),'partResults':previous['partResults']}
    documents=[dict(item) for item in manifest.get('documents',[]) if item.get('text','').strip()]
    result={'generationId':generation,'inputManifestHash':input_hash,'producerConfigs':{key:models[key] for key in ('textConfig','imageConfig')},
            'documents':documents,'images':[],'enabledReferenceWorkIds':[],'partResults':[],'qualityFlags':[]}
    for document in documents:result['partResults'].append({'sourceRevisionId':str(document['sourceRevisionId']),'key':document.get('sourceKey','BODY'),'status':'AVAILABLE'})
    for source in manifest.get('images',[]):
        image_config=models['imageConfig']
        if 'vector' in source:validate_feature_space(source,image_config)
        try:
            path=controlled_file(source['path'],source['fileSha256'],models['allowedRoots'])
            key=artifact_cache_key(source['fileSha256'],image_config);cache_file=cache/(key+'.json')
            cached=None
            if cache_file.exists():
                try:
                    candidate=json.loads(cache_file.read_text(encoding='utf-8'));validate_feature_space(candidate,image_config)
                    validate_image_feature(candidate)
                    if candidate.get('fileSha256')==source['fileSha256'] and candidate.get('producerConfigHash')==digest_json(image_config):cached=candidate
                except (ValueError,ContractError):pass
            if cached is None:
                vector=encode_images([path],models)[0].tolist()
                cached={'vector':vector,'fileSha256':source['fileSha256'],'featureSpaceId':image_config['featureSpaceId'],'producerConfigHash':digest_json(image_config)}
                validate_image_feature(cached)
                atomic_json(cache_file,cached)
            entry={key:value for key,value in source.items() if key not in ('path','vector')};entry.update(cached)
            result['images'].append(entry)
            result['partResults'].append({'sourceRevisionId':str(source['sourceRevisionId']),'key':'IMAGE:'+str(source.get('nodeId',source['fileId'])),'status':'AVAILABLE','cacheKey':key})
        except Exception as error:
            result['partResults'].append({'sourceRevisionId':str(source['sourceRevisionId']),'key':'IMAGE:'+str(source.get('nodeId',source['fileId'])),'status':'FAILED','errorCode':getattr(error,'code',type(error).__name__)})
    index=prepare_text_index(result,models)
    if index['matrix'] is not None:
        temporary=directory/'text-index.joblib.tmp';joblib.dump(index,temporary);temporary.replace(directory/'text-index.joblib')
        result['textIndex']={'file':'text-index.joblib','sha256':file_sha256(directory/'text-index.joblib'),'featureSpaceId':models['textConfig']['featureSpaceId']}
    usable={str(item['sourceWorkId']) for item in documents+result['images']}
    result['enabledReferenceWorkIds']=sorted(usable)
    if not usable:result['qualityFlags'].append('EMPTY_LIBRARY')
    atomic_json(target,result);checksum=file_sha256(target)
    ready_temporary=directory/'READY.tmp';ready_temporary.write_text(checksum);ready_temporary.replace(ready)
    return {'status':'READY','generationId':generation,'manifestPath':str(target),'manifestSha256':checksum,'partResults':result['partResults']}
