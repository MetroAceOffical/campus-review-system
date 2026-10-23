import hashlib
import json
from pathlib import Path
import re

IDENTITY_KEYS=('taskId','attemptId','scene','inputSnapshotKey','inputSha256','libraryGenerationId','configId')

class ContractError(ValueError):
    def __init__(self,code,message):
        super().__init__(message)
        self.code=code

def digest_json(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()

def file_sha256(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

def validate_request(request,config,library):
    if not isinstance(request,dict):raise ContractError('INVALID_REQUEST','Request must be an object')
    for key in IDENTITY_KEYS:
        if not isinstance(request.get(key),str) or not request[key] or len(request[key])>128:
            raise ContractError('INVALID_IDENTITY','Missing or invalid '+key)
    if request['scene'] not in ('FORMAL','PRECHECK','EXTERNAL'):
        raise ContractError('INVALID_SCENE','Unsupported calculation scene')
    if request['scene']=='FORMAL' and (not re.fullmatch(r'[1-9][0-9]*',str(request.get('versionId',''))) or request['inputSnapshotKey']!='submission:'+request['versionId']):
        raise ContractError('INVALID_SNAPSHOT','Formal input identity does not match version')
    if not re.fullmatch(r'[0-9a-f]{64}',request['inputSha256']):raise ContractError('INVALID_INPUT_HASH','Invalid snapshot hash')
    if request['configId']!=config.get('configId'):raise ContractError('CONFIG_UNAVAILABLE','Requested frozen configuration is unavailable')
    if request['libraryGenerationId']!=str(library.get('generationId')):raise ContractError('LIBRARY_MISMATCH','Library generation does not match request')

def validate_result(result,request):
    for key in (*IDENTITY_KEYS,'versionId'):
        if result.get(key)!=request.get(key):raise ContractError('RESULT_IDENTITY_MISMATCH','Result identity mismatch: '+key)

def result_header(request,config):
    return {**{key:request[key] for key in IDENTITY_KEYS},
            **({'versionId':request['versionId']} if 'versionId' in request else {}),
            'status':'COMPLETED','actualConfig':config,'evidence':[],'qualityFlags':[],
            'noReuseClaim':False}

def controlled_file(path,expected_sha,roots):
    resolved=Path(path).resolve(strict=True)
    if not any(resolved.is_relative_to(Path(root).resolve()) for root in roots):raise ContractError('FILE_OUTSIDE_ROOT','Input file is outside the allowed project roots')
    if not re.fullmatch(r'[0-9a-f]{64}',str(expected_sha)) or file_sha256(resolved)!=expected_sha:
        raise ContractError('FILE_HASH_MISMATCH','Input file hash does not match registered identity')
    return resolved

def evidence_id(attempt_id,kind,identity):
    return str(attempt_id)+':'+kind+':'+digest_json(identity)[:20]
