import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_campus_stage as stage


class CampusStageTests(unittest.TestCase):
    def freeze(self,root,manifest):
        root.mkdir(exist_ok=True)
        (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (root/'pairs.jsonl').write_text('test data fixture',encoding='utf-8')
        (root/'READY').write_text(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['manifest.json','pairs.jsonl']}))

    def test_ready_file_alone_cannot_start_a_small_or_imbalanced_formal_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'pairs'
            self.assertEqual(stage.material_state(root),'WAITING_FORMAL_MATERIAL')
            manifest={'formalScaleAndBalanceReady':True,'pairCount':20000,'classCounts':{'0':10000,'1':10000}}
            for changed in [{**manifest,'formalScaleAndBalanceReady':False},{**manifest,'pairCount':19999,'classCounts':{'0':9999,'1':10000}},
                            {**manifest,'classCounts':{'0':1000,'1':19000}}]:
                self.freeze(root,changed)
                self.assertEqual(stage.material_state(root),'NEEDS_MORE_SUPPORTED_MATERIAL')
            self.freeze(root,manifest)
            self.assertEqual(stage.material_state(root),'FORMAL_MATERIAL_READY')
            (root/'pairs.jsonl').write_text('changed')
            with self.assertRaises(ValueError):stage.material_state(root)

    def test_existing_unfinished_neural_runs_are_preserved_and_not_restarted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertIsNone(stage.completed_stage(root,'CORRESPONDENCE_TRAINING_COMPLETE'))
            (root/'run.json').write_text('{}')
            with self.assertRaises(RuntimeError):stage.completed_stage(root,'CORRESPONDENCE_TRAINING_COMPLETE')
            checkpoint=root/'checkpoint-000002';checkpoint.mkdir();(checkpoint/'state.pt').write_bytes(b'test checkpoint')
            (checkpoint/'READY').write_text(json.dumps({'state.pt':hashlib.sha256((checkpoint/'state.pt').read_bytes()).hexdigest()}))
            status={'state':'CORRESPONDENCE_TRAINING_COMPLETE','reloadVerified':True,'epochs':2,'checkpoint':checkpoint.name}
            (root/'status.json').write_text(json.dumps(status))
            self.assertEqual(stage.completed_stage(root,'CORRESPONDENCE_TRAINING_COMPLETE'),checkpoint)
            (checkpoint/'state.pt').write_bytes(b'changed')
            with self.assertRaises(ValueError):stage.completed_stage(root,'CORRESPONDENCE_TRAINING_COMPLETE')

    def test_source_identity_is_rechecked_after_long_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'app/training';source.mkdir(parents=True)
            for name in stage.TRAINING_SCRIPTS:(source/name).write_text('original code')
            script=source/'train_correspondence.py'
            identity=stage.implementation_identity(root)
            stage.assert_identity(identity,root)
            (source/'unrelated_evaluation.py').write_text('new evaluation code')
            stage.assert_identity(identity,root)
            script.write_text('changed while queued')
            with self.assertRaises(RuntimeError):stage.assert_identity(identity,root)

    def test_only_one_stage_controller_can_hold_the_project_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'training.lock'
            with stage.stage_lock(path):
                with self.assertRaises(RuntimeError):
                    with stage.stage_lock(path):pass
            with stage.stage_lock(path):pass


if __name__=='__main__':unittest.main()
