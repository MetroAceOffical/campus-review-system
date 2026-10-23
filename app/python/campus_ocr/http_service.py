import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import uuid
from campus_ocr.recognizer import ROOT,load_pipeline,recognize
from campus_shared.contracts import ContractError

class Runtime:
    def __init__(self,token):
        self.token=token;self.run_id=str(uuid.uuid4());self.config=None;self.error=None;self.compute=threading.Lock();self.active_attempt=None
    def load(self):
        try:_,self.config=load_pipeline()
        except Exception as error:self.error=getattr(error,'code',type(error).__name__)
    def health(self):return {'ready':self.config is not None,'runId':self.run_id,'busy':self.compute.locked(),'activeAttemptId':self.active_attempt,'errorCode':self.error,'config':self.config}

def make_server(runtime,port=18082):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body):
            data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def authorized(self):
            if not hmac.compare_digest(self.headers.get('X-Internal-Token',''),runtime.token):self.reply(401,{'status':'FAILED','errorCode':'INTERNAL_AUTH_REQUIRED'});return False
            return True
        def do_GET(self):
            if not self.authorized():return
            if self.path!='/health':self.reply(404,{'errorCode':'ENDPOINT_NOT_FOUND'});return
            self.reply(200,runtime.health())
        def do_POST(self):
            if not self.authorized():return
            if self.path!='/recognize':self.reply(404,{'errorCode':'ENDPOINT_NOT_FOUND'});return
            if runtime.config is None:self.reply(503,{'status':'FAILED','errorCode':'MODELS_NOT_READY'});return
            if not runtime.compute.acquire(blocking=False):self.reply(409,{'status':'FAILED','errorCode':'PROCESS_BUSY','runId':runtime.run_id});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=65536:raise ContractError('INVALID_REQUEST_SIZE','Invalid request size')
                image=json.loads(self.rfile.read(length));runtime.active_attempt=image.get('attemptId')
                result=recognize(image,runtime.config);result['processRunId']=runtime.run_id
                self.reply(200,result)
            except (ContractError,ValueError,KeyError,FileNotFoundError) as error:
                self.reply(400,{'status':'FAILED','errorCode':getattr(error,'code','INVALID_REQUEST'),'message':str(error)[:200],'runId':runtime.run_id})
            except Exception:self.reply(500,{'status':'FAILED','errorCode':'OCR_FAILED','runId':runtime.run_id})
            finally:runtime.active_attempt=None;runtime.compute.release()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18082);args=parser.parse_args()
    token=(ROOT/'runtime/private-config/internal-token').read_text().strip()
    runtime=Runtime(token);server=make_server(runtime,args.port)
    threading.Thread(target=runtime.load,daemon=True).start()
    print(json.dumps({'event':'listening','port':server.server_port,'runId':runtime.run_id,'ready':False}),flush=True)
    server.serve_forever()

if __name__=='__main__':main()
