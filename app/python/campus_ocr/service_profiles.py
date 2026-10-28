"""Serve the original OCR contract and the adaptive version under separate IDs."""
from pathlib import Path
from campus_shared.contracts import ContractError,controlled_file,digest_json,file_sha256
from . import recognizer

def configurations(baseline):
    from .fallback import fallback_configuration
    adaptive=fallback_configuration(baseline)
    adaptive.pop('configId');adaptive.pop('featureSpaceId')
    adaptive['serviceAlgorithms']={name:file_sha256(Path(__file__).with_name(name)) for name in ('service_profiles.py','recognizer.py')}
    adaptive['featureSpaceId']='ocr-'+digest_json(adaptive)
    adaptive['configId']='ocr-'+digest_json(adaptive)
    return {baseline['configId']:baseline,adaptive['configId']:adaptive}

def recognize(image,config):
    if config.get('schemaVersion')=='ocr-v1':return recognizer.recognize(image,config)
    pipeline,baseline=recognizer.load_pipeline();available=configurations(baseline)
    if config.get('schemaVersion')!='ocr-v2' or available.get(config.get('configId'))!=config or image.get('configId')!=config['configId']:
        raise ContractError('CONFIG_UNAVAILABLE','Requested OCR configuration is unavailable')
    for key in ('taskId','attemptId','fileId'):
        if not isinstance(image.get(key),str) or not image[key]:raise ContractError('INVALID_IDENTITY','Missing '+key)
    path=controlled_file(image.get('path',''),image.get('fileSha256'),[recognizer.ROOT/'runtime',recognizer.ROOT/'validation'])
    from .fallback import recognize_adaptive
    result=recognize_adaptive(pipeline,path,baseline,config['policy'])['adaptive']
    result.update({key:image[key] for key in ('taskId','attemptId','fileId','fileSha256')});result['actualConfig']=config
    return result
