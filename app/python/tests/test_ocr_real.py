import os
import unittest

@unittest.skipUnless(os.environ.get('CAMPUS_REAL_MODELS')=='1','RealModels not requested; not counted as OCR success')
class RealOcrTest(unittest.TestCase):
    def test_clear_and_blurred_images_are_actually_recognized(self):
        from campus_ocr.probe import run_probe
        result=run_probe()
        self.assertEqual(result['actualRuns'],2)
        self.assertGreater(result['clearLineCount'],0)
        self.assertFalse(result['blurNoReuseClaim'])
    def test_http_uses_same_real_recognizer(self):
        import http.client,json,threading
        from campus_ocr.recognizer import ROOT,load_pipeline,recognize
        from campus_ocr.http_service import Runtime,make_server
        from campus_shared.contracts import file_sha256
        _,config=load_pipeline();path=ROOT/'validation/remaining/vision/inputs/mixed-known.png'
        request={'taskId':'1','attemptId':'1','fileId':'probe-clear','path':str(path),'fileSha256':file_sha256(path),'configId':config['configId']}
        direct=recognize(request,config)
        runtime=Runtime('real-ocr-probe-token');runtime.config=config;server=make_server(runtime,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=180)
            connection.request('POST','/recognize',body=json.dumps(request).encode(),headers={'X-Internal-Token':'real-ocr-probe-token','Content-Type':'application/json'})
            response=connection.getresponse();status=response.status;result=json.loads(response.read());connection.close()
            self.assertEqual(status,200);self.assertEqual(result['recognitionLines'],direct['recognitionLines'])
            self.assertEqual(result['fileSha256'],request['fileSha256'])
            (ROOT/'docs/midterm/evidence/M05-http.json').write_text(json.dumps({'actualHttp':True,'sameRecognizer':True,'identicalLines':True,'configId':config['configId'],'runId':runtime.run_id},indent=2),encoding='utf-8')
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
