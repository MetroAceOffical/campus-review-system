import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

@unittest.skipUnless(os.environ.get('CAMPUS_REAL_MODELS')=='1','RealModels not requested; not counted as model success')
class RealHttpTest(unittest.TestCase):
    def test_http_and_offline_use_identical_real_text_calculation(self):
        from campus_detection.models import ROOT,load_models
        from campus_detection.probe import identity,jsonl,probe_documents
        from campus_detection.text import detect_text
        from campus_detection.http_service import Runtime,make_server
        models=load_models()
        case=next(row for row in jsonl(ROOT/'validation/remaining/text/cases.jsonl') if row['split']=='development' and row['kind']=='copy')
        library={'generationId':'1','documents':probe_documents(case['source_id'])}
        request=dict(identity(models['textConfig']['configId'],hashlib.sha256(case['text'].encode()).hexdigest()),text=case['text'])
        offline=detect_text(request,library,models)
        parent=ROOT/'runtime/test-tmp';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            directory=Path(folder)/'1';directory.mkdir();manifest=directory/'manifest.json'
            manifest.write_text(json.dumps({key:value for key,value in library.items() if not key.startswith('_')},ensure_ascii=False),encoding='utf-8')
            (directory/'READY').write_text(hashlib.sha256(manifest.read_bytes()).hexdigest())
            runtime=Runtime(Path(folder),'real-probe-token');runtime.models=models
            server=make_server(runtime,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=120)
                connection.request('POST','/detect/text',body=json.dumps(request,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','X-Internal-Token':'real-probe-token'})
                response=connection.getresponse();status=response.status;result=json.loads(response.read());connection.close()
                self.assertEqual(status,200)
                self.assertEqual(result['evidence'],offline['evidence'])
                self.assertEqual(result['configId'],offline['configId'])
                (ROOT/'docs/midterm/evidence/M04-http.json').write_text(json.dumps({'actualHttp':True,'sameCalculation':True,'identicalEvidence':True,'sourceCount':194,'configId':result['configId'],'runId':result['processRunId'],'scene':'isolated formal-shape probe; no live submission row'},indent=2),encoding='utf-8')
            finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
