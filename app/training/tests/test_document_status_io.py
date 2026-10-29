import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'app/training'))
import run_document_evaluation as evaluation

class DocumentStatusIOTests(unittest.TestCase):
    def test_transient_windows_replace_conflict_is_retried_and_persistent_failure_surfaces(self):
        metrics=evaluation.aggregate([{'error':'status write failed','metrics':{'falseNegative':1}}])
        self.assertEqual(metrics['failedQueries'],1)
        self.assertEqual(metrics['falseNegative'],0)
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime/workbench-implementation') as folder:
            target=Path(folder)/'status.json'
            with patch.object(evaluation,'_atomic_json',create=True,side_effect=[PermissionError('sharing conflict'),None]) as writer,patch.object(evaluation.time,'sleep'):
                evaluation.atomic_json(target,{'state':'RUNNING'})
                self.assertEqual(writer.call_count,2)
            with patch.object(evaluation,'_atomic_json',create=True,side_effect=PermissionError('persistent')) as writer,patch.object(evaluation.time,'sleep'):
                with self.assertRaises(PermissionError):evaluation.atomic_json(target,{'state':'RUNNING'})
                self.assertEqual(writer.call_count,8)

if __name__=='__main__':unittest.main()
