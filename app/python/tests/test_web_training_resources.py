"""Exercise the real CLI resource lane without loading models or starting training."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.training import compute_slot
from campus_workbench import training_resume

spec=importlib.util.spec_from_file_location('web_training_resource_cli',ROOT/'app/scripts/workbench_training.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)

class WebTrainingResourcesTest(unittest.TestCase):
    def run_cli(self,folder,action='TRAIN',device='cuda'):
        config=Path(folder)/'config.json'
        config.write_text(json.dumps({'action':action,'device':device,'family':'cnn','runtime':str(folder),'preparation':str(folder),'output':str(Path(folder)/'output'),'parameters':{'device':device}}),encoding='utf-8')
        with patch.object(sys,'argv',['workbench_training.py','--config-file',str(config)]),patch('socket.socket.connect_ex',return_value=0),patch.object(cli,'send'),patch.object(training_resume,'train',return_value={'status':'COMPLETED'}) as train:
            cli.main()
            return train.call_count

    def test_idle_online_service_does_not_block_gpu_model_training(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as folder:
            self.assertEqual(1,self.run_cli(folder))

    def test_active_online_compute_lock_still_blocks_gpu_model_training(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as folder,compute_slot(folder,False):
            with self.assertRaises(BlockingIOError):self.run_cli(folder)

    def test_gpu_generation_keeps_its_existing_online_service_guard(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as folder:
            with self.assertRaisesRegex(BlockingIOError,'在线检测'):self.run_cli(folder,'GENERATE')

    def test_cpu_training_retains_its_independent_lane(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as folder,compute_slot(folder,False):
            self.assertEqual(1,self.run_cli(folder,device='cpu'))

if __name__=='__main__':unittest.main()
