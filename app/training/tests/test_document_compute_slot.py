import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.document_compute import document_slot

class DocumentComputeTests(unittest.TestCase):
    def test_online_and_document_work_share_lock_and_legacy_gpu_is_still_guarded(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime/workbench-implementation') as folder:
            with patch('psutil.process_iter',return_value=[]):
                with document_slot(folder,neural=True):
                    with self.assertRaises(BlockingIOError):
                        with document_slot(folder):pass
                with document_slot(folder):
                    with self.assertRaises(BlockingIOError):
                        with document_slot(folder,neural=True):pass
            legacy=SimpleNamespace(pid=-1,info={'cmdline':['python','run_campus_stage.py']})
            with patch('psutil.process_iter',return_value=[legacy]):
                with self.assertRaises(BlockingIOError):
                    with document_slot(folder,neural=True):pass

if __name__=='__main__':unittest.main()
