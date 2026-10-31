"""Loopback-only authenticated adapter. Calculation functions also serve offline callers."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import uuid
from campus_shared.contracts import ContractError,file_sha256,validate_result
from campus_detection.models import ROOT,load_models
from campus_detection.text import detect_text
from campus_detection.image import detect_image


class Runtime:
    def __init__(self,index_root,token,v3_profile=None,enhanced_images=False,contextual=False,refined=False):
        self.index_root=Path(index_root).resolve()
        if not self.index_root.is_relative_to(ROOT/'runtime'):raise ValueError('Index root must stay inside project runtime')
        self.token=token;self.run_id=str(uuid.uuid4());self.models=None;self.load_error=None;self.v3_profile=v3_profile
        self.compute=threading.Lock();self.active_attempt=None;self.libraries={};self.loaded_profile_id=None;self.enhanced_images=enhanced_images;self.contextual=contextual;self.refined=refined
    def load(self):
        try:
            profile=None
            if self.v3_profile:
                from campus_detection.service_profile import verify_profile,profile_directory
                location=Path(self.v3_profile).resolve()
                if location!=profile_directory(location.parent.name)/'profile.json':raise ValueError('Select a prepared production service profile')
                profile=verify_profile(location.parent.name)
            models=load_models(enhanced_images=True) if self.enhanced_images else load_models()
            if self.contextual or self.refined:
                if profile:raise ValueError('Select either the formal v3 profile or context refinement')
                from campus_detection.contextual_text import configuration
                context=configuration(models['textConfig'])
                models={**models,'textConfig':context,'textConfigs':{**models['textConfigs'],context['configId']:context}}
                if self.refined:
                    from campus_detection.text_refinement import configuration as refined_configuration
                    refined=refined_configuration(context)
                    models={**models,'textConfig':refined,'textConfigs':{**models['textConfigs'],refined['configId']:refined}}
                    from campus_detection.mutual_text import configuration as mutual_configuration
                    guarded=mutual_configuration(refined)
                    models={**models,'textConfig':guarded,'textConfigs':{**models['textConfigs'],guarded['configId']:guarded}}
            if profile:
                from campus_detection.v3_runtime import controlled,read,verify_files,load_bundle,attach_runtime
                from campus_detection.retrieval import load_dense_index
                calibration_folder=controlled(profile['calibration']);verify_files(calibration_folder)
                calibration=read(calibration_folder/'calibration.json')
                if calibration.get('operatingPointFrozen') is not True:raise ValueError('Require a frozen operating point for service activation')
                session=load_bundle(controlled(profile['bundle']),device='cuda',precision='BF16')
                index=load_dense_index(controlled(profile['index']),session['retriever']['identity'])
                models=attach_runtime(models,session,index,calibration)
                if models['textConfigs'][models['v3Runtime']['configId']]!=profile['textConfig']:raise ValueError('Loaded profile configuration differs')
                self.loaded_profile_id=profile['profileId']
            self.models=models
        except Exception as error:self.load_error=getattr(error,'code',type(error).__name__)
    def health(self):
        return {'ready':self.models is not None,'runId':self.run_id,'busy':self.compute.locked(),
                'activeAttemptId':self.active_attempt,'errorCode':self.load_error,
                'availableTextConfigs':[] if self.models is None else [
                    {'configId':key,'profileId':self.loaded_profile_id if value.get('schemaVersion')=='text-v3' else None}
                    for key,value in self.models['textConfigs'].items()],
                'availableImageConfigs':[] if self.models is None else list(self.models.get('imageConfigs',{}).values()),
                'configs':None if self.models is None else {name:self.models[name] for name in ('textConfig','imageConfig')}}
    def library(self,request):
        generation=request.get('libraryGenerationId')
        if not isinstance(generation,str) or not re.fullmatch(r'[1-9][0-9]*',generation):raise ContractError('INVALID_LIBRARY_ID','Invalid library generation')
        directory=self.index_root/generation
        manifest=directory/'manifest.json';ready=directory/'READY'
        if not ready.is_file() or not manifest.is_file():raise ContractError('INDEX_UNAVAILABLE','Library is missing or not READY')
        checksum=file_sha256(manifest)
        if ready.read_text().strip()!=checksum:raise ContractError('INDEX_CORRUPT','Library checksum does not match READY marker')
        if request.get('libraryManifestSha256',checksum)!=checksum:raise ContractError('LIBRARY_MISMATCH','Requested manifest hash differs')
        if generation in self.libraries:
            cached=self.libraries[generation]
            if cached['_manifestSha256']!=checksum:raise ContractError('INDEX_MUTATED','An immutable generation was modified')
            return cached
        value=json.loads(manifest.read_text(encoding='utf-8'))
        if str(value.get('generationId'))!=generation:raise ContractError('LIBRARY_MISMATCH','Manifest generation does not match request')
        if value.get('textIndex'):
            import joblib
            descriptor=value['textIndex'];index=directory/descriptor['file']
            if index.parent!=directory or not index.is_file() or file_sha256(index)!=descriptor['sha256']:raise ContractError('INDEX_CORRUPT','Text index checksum differs')
            value['_textIndex']=joblib.load(index)
        if self.enhanced_images:
            from campus_detection.image_enhanced import attach_sources
            try:attach_sources(value,directory)
            except (ValueError,KeyError,OSError):pass
        value['_manifestSha256']=checksum;self.libraries[generation]=value
        return value


def make_server(runtime,port=18081):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def reply(self,status,body):
            payload=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
        def authorized(self):
            if not hmac.compare_digest(self.headers.get('X-Internal-Token',''),runtime.token):
                self.reply(401,{'status':'FAILED','errorCode':'INTERNAL_AUTH_REQUIRED'});return False
            return True
        def do_GET(self):
            if not self.authorized():return
            if self.path!='/health':self.reply(404,{'errorCode':'ENDPOINT_NOT_FOUND'});return
            self.reply(200,runtime.health())
        def do_POST(self):
            if not self.authorized():return
            if self.path not in ('/detect/text','/detect/image','/library/build','/models/text'):
                self.reply(404,{'errorCode':'ENDPOINT_NOT_FOUND'});return
            if runtime.models is None:self.reply(503,{'status':'FAILED','errorCode':'MODELS_NOT_READY'});return
            if not runtime.compute.acquire(blocking=False):self.reply(409,{'status':'FAILED','errorCode':'PROCESS_BUSY','runId':runtime.run_id});return
            from contextlib import ExitStack
            from campus_shared.document_compute import document_slot
            slot=ExitStack()
            try:
                try:slot.enter_context(document_slot(ROOT/'runtime'))
                except BlockingIOError:
                    self.reply(409,{'status':'FAILED','errorCode':'PROCESS_BUSY','runId':runtime.run_id});return
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>4*1024*1024:raise ContractError('INVALID_REQUEST_SIZE','Invalid request size')
                request=json.loads(self.rfile.read(length));runtime.active_attempt=request.get('attemptId')
                if self.path=='/models/text':
                    from campus_detection.web_bert import register
                    location=(ROOT/request['path']).resolve()
                    if location.name!='adapter.json' or location.parent.parent!=ROOT/'runtime/delivery/releases' or file_sha256(location)!=request['sha256']:raise ValueError('正文适配工件身份无效')
                    descriptor=json.loads(location.read_text(encoding='utf8'))
                    if descriptor.get('schemaVersion')=='six-model-adapter-v1':
                        from campus_detection.six_model_bundle import register
                    config=register(runtime.models,ROOT/request['path'],request['sha256'])
                    self.reply(200,{'configId':config['configId'],'ready':True});return
                if self.path=='/library/build':
                    from campus_detection.library import build_library
                    location=Path(request.get('manifestPath','')).resolve()
                    if not location.is_relative_to(ROOT/'runtime') or not location.is_file():raise ContractError('FILE_OUTSIDE_ROOT','Library input manifest must stay in project runtime')
                    if request.get('manifestSha256')!=file_sha256(location):raise ContractError('FILE_HASH_MISMATCH','Library input manifest hash differs')
                    manifest=json.loads(location.read_text(encoding='utf-8'))
                    result=build_library(manifest,{'models':runtime.models,'indexRoot':runtime.index_root})
                    self.reply(200,result);return
                library=runtime.library(request)
                function=detect_text if self.path=='/detect/text' else detect_image
                if self.path=='/detect/text' and runtime.models.get('textConfigs',{}).get(request.get('configId'),{}).get('contextPolicy'):
                    from campus_detection.contextual_text import detect
                    function=detect
                if self.path=='/detect/text' and runtime.models.get('textConfigs',{}).get(request.get('configId'),{}).get('refinementPolicy'):
                    from campus_detection.text_refinement import detect
                    function=detect
                if self.path=='/detect/text' and runtime.models.get('textConfigs',{}).get(request.get('configId'),{}).get('mutualEvidencePolicy'):
                    from campus_detection.mutual_text import detect
                    function=detect
                selected=runtime.models
                if self.path=='/detect/text' and runtime.models.get('textConfigs',{}).get(request.get('configId'),{}).get('sixModelBundle'):
                    from campus_detection.six_model_bundle import detect
                    function=detect
                if self.path=='/detect/text':
                    from campus_detection.web_bert import register,select_models
                    key=request.get('configId')
                    if key in runtime.models.get('textAdapterDescriptors',{}) and key not in runtime.models.get('webBertModels',{}):
                        saved=runtime.models['textAdapterDescriptors'][key];register(runtime.models,saved['path'],saved['sha256'])
                    selected=select_models(runtime.models,key)
                result=function(request,library,selected);validate_result(result,request)
                if self.path=='/detect/text' and selected['textConfigs'].get(request.get('configId'),{}).get('webBert'):
                    result['modelBinding']=selected['textConfigs'][request['configId']]['webBert']
                result['processRunId']=runtime.run_id
                self.reply(200,result)
            except (ContractError,ValueError,KeyError,FileNotFoundError) as error:
                self.reply(400,{'status':'FAILED','errorCode':getattr(error,'code','INVALID_REQUEST'),'message':str(error)[:200],'runId':runtime.run_id})
            except Exception:
                self.reply(500,{'status':'FAILED','errorCode':'DETECTION_ERROR','message':'Calculation failed; immutable input and attempt were not changed','runId':runtime.run_id})
            finally:runtime.active_attempt=None;slot.close();runtime.compute.release()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18081)
    parser.add_argument('--index-root',type=Path,default=ROOT/'runtime/indexes')
    parser.add_argument('--v3-profile',type=Path,help='Explicit verified bundle/index/calibration profile; default v2 remains available')
    parser.add_argument('--enhanced-images',action='store_true')
    parser.add_argument('--contextual-text',action='store_true',help='Use version-budgeted BERT contexts; retain old configurations')
    parser.add_argument('--refined-text',action='store_true',help='Exclude structured navigation tails and corroborate anchored contexts; retain older IDs')
    args=parser.parse_args()
    token_path=ROOT/'runtime/private-config/internal-token'
    if not token_path.is_file():raise RuntimeError('Run project initialization to create its private internal token')
    runtime=Runtime(args.index_root,token_path.read_text().strip(),args.v3_profile,args.enhanced_images,args.contextual_text,args.refined_text)
    server=make_server(runtime,args.port)
    threading.Thread(target=runtime.load,daemon=True).start()
    print(json.dumps({'event':'listening','port':server.server_port,'runId':runtime.run_id,'ready':False}),flush=True)
    server.serve_forever()

if __name__=='__main__':main()
