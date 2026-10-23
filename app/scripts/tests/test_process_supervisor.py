import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from process_supervisor import verify_process,stop_owned

class ProcessSafetyTest(unittest.TestCase):
    def test_unknown_process_is_not_stopped(self):
        process=Mock();process.create_time.return_value=999
        record={'pid':42,'created':1,'exe':'expected','cmdline':['expected'],'cwd':'project'}
        with patch('process_supervisor.psutil.Process',return_value=process):
            with self.assertRaises(RuntimeError):stop_owned(record)
        process.terminate.assert_not_called();process.kill.assert_not_called()
    def test_changed_arguments_or_working_directory_are_not_owned(self):
        process=Mock();process.create_time.return_value=1;process.exe.return_value='expected';process.cmdline.return_value=['foreign'];process.cwd.return_value='project'
        with patch('process_supervisor.psutil.Process',return_value=process):
            with self.assertRaises(RuntimeError):verify_process({'pid':42,'created':1,'exe':'expected','cmdline':['expected'],'cwd':'project'})

if __name__=='__main__':unittest.main()
