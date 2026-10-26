import hashlib
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from download_assets import download_ranges


class DownloadTests(unittest.TestCase):
    def test_resume_requires_correct_ranges_and_verifies_completed_hash(self):
        content = b'0123456789abcdefghijklmnopqrstuv'
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start,end = map(int,self.headers['Range'].removeprefix('bytes=').split('-'))
                body = content[start:end+1]
                self.send_response(206)
                self.send_header('Content-Range',f'bytes {start}-{end}/{len(content)}')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder)/'asset.bin'
                target.with_suffix('.bin.part').write_bytes(content[:5])
                download_ranges(f'http://127.0.0.1:{server.server_port}/asset',target,len(content),hashlib.sha256(content).hexdigest(),chunk_size=8)
                self.assertEqual(target.read_bytes(),content)
                self.assertFalse(target.with_suffix('.bin.part').exists())
        finally:
            server.shutdown();server.server_close();thread.join()
