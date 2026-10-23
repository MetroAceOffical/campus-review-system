import http.client
import json
import threading
import unittest
from campus_ocr.http_service import Runtime,make_server

class OcrHttpTest(unittest.TestCase):
    def test_auth_and_readiness_without_loading_paddle(self):
        runtime=Runtime('local-test-token');server=make_server(runtime,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request('GET','/health');response=connection.getresponse();self.assertEqual(response.status,401);response.read();connection.close()
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request('GET','/health',headers={'X-Internal-Token':'local-test-token'});response=connection.getresponse();self.assertFalse(json.loads(response.read())['ready']);connection.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
