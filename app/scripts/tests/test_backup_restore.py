import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup_restore import validate_restore_target,verify_backup,same_counts
from runtime_manager import ROOT

class BackupSafetyTest(unittest.TestCase):
    def test_restore_counts_compare_values_across_windows_line_endings(self):
        self.assertTrue(same_counts('manuscript\t7\r\npublication\t2','manuscript\t7\npublication\t2'))
        self.assertFalse(same_counts('manuscript\t8\r\npublication\t2','manuscript\t7\npublication\t2'))
    def test_restore_rejects_business_path_existing_target_and_unknown_files(self):
        with self.assertRaises(ValueError):validate_restore_target(ROOT/'runtime',3318)
        with self.assertRaises(ValueError):validate_restore_target(ROOT/'runtime/restores/new',3308)
        parent=ROOT/'runtime/test-tmp';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            with self.assertRaises(ValueError):validate_restore_target(Path(temporary),3318)
            with self.assertRaises(ValueError):verify_backup(Path(temporary))

if __name__=='__main__':unittest.main()
