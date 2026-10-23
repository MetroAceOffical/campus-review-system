import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from campus_detection.http_service import Runtime,make_server
from campus_detection.models import ROOT
from test_detection_contract import request


class HttpAdapterTest(unittest.TestCase):
    def setUp(self):
        temporary_root=ROOT/'runtime/test-tmp';temporary_root.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=temporary_root)
        self.runtime=Runtime(Path(self.temporary.name),'local-test-token')
        directory=self.runtime.index_root/'1';directory.mkdir()
        self.manifest=directory/'manifest.json'
        self.manifest.write_text(json.dumps({'generationId':'1','documents':[]}))
        (directory/'READY').write_text(hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.server=make_server(self.runtime,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5);self.temporary.cleanup()
    def call(self,path,body=None,token='local-test-token'):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            connection.request('GET' if body is None else 'POST',path,body=None if body is None else json.dumps(body),headers={'X-Internal-Token':token,'Content-Type':'application/json'})
            response=connection.getresponse();return response.status,json.loads(response.read())
        finally:connection.close()
    def test_private_auth_readiness_and_busy_are_explicit(self):
        self.assertEqual(self.call('/health',token='wrong')[0],401)
        self.assertFalse(self.call('/health')[1]['ready'])
        self.assertEqual(self.call('/detect/text',request())[0],503)
        self.runtime.models={'textConfig':{'configId':'text-test'}}
        self.runtime.compute.acquire()
        try:self.assertEqual(self.call('/detect/text',request())[1]['errorCode'],'PROCESS_BUSY')
        finally:self.runtime.compute.release()
    def test_empty_library_and_corrupt_manifest_do_not_claim_no_match(self):
        self.runtime.models={'textConfig':{'configId':'text-test'}}
        status,result=self.call('/detect/text',request())
        self.assertEqual(status,200);self.assertIn('EMPTY_LIBRARY',result['qualityFlags']);self.assertFalse(result['noReuseClaim'])
        self.manifest.write_text('{}')
        status,result=self.call('/detect/text',request())
        self.assertEqual(status,400);self.assertEqual(result['errorCode'],'INDEX_CORRUPT')

if __name__=='__main__':unittest.main()
