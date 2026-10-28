import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection import service_profile,v3_runtime,retrieval
from campus_detection.http_service import Runtime


class ServiceProfileTests(unittest.TestCase):
    def test_explicit_v3_load_keeps_v2_default_and_advertises_both(self):
        base={'configId':'v2','schemaVersion':'text-v2'};v3={'configId':'v3','schemaVersion':'text-v3'}
        original={'textConfig':base,'textConfigs':{'v2':base},'imageConfig':{'configId':'image'}}
        with patch.object(v3_runtime,'service_configuration',return_value=v3):
            loaded=v3_runtime.attach_runtime(original,{}, {}, {})
        self.assertEqual(loaded['textConfig'],base)
        self.assertNotIn('v3',original['textConfigs'])
        runtime=Runtime(ROOT/'runtime/indexes','test-only');runtime.models=loaded;runtime.loaded_profile_id='profile-test'
        self.assertEqual(runtime.health()['availableTextConfigs'],[{'configId':'v2','profileId':None},{'configId':'v3','profileId':'profile-test'}])
        library={'documents':[]}
        loaded['v3Runtime']['index']={'manifest':{'inputManifestSha256':retrieval._digest([])}}
        with patch('campus_detection.text.detect_text',return_value={'status':'NOT_APPLICABLE'}):
            report=v3_runtime.detect({'configId':'v3'},library,loaded)
        self.assertEqual(report['actualConfig'],v3)
        with self.assertRaisesRegex(ValueError,'not loaded'):
            v3_runtime.detect({'configId':'another-v3'},library,loaded)

    @unittest.skipUnless((ROOT/'runtime/indexes/18/READY').is_file(),'Requires existing local business reference generation')
    def test_real_business_snapshot_reconstructs_all_fields_without_changing_library(self):
        descriptor,library=service_profile.library_snapshot('18')
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as directory:
            output=Path(directory)/'snapshot';result=service_profile.snapshot_references('18',output)
            rows=[json.loads(line) for line in (output/'references.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(rows,library['documents']);self.assertEqual(result['documentsDigest'],descriptor['documentsDigest'])
            v3_runtime.verify_files(output)
            with self.assertRaisesRegex(ValueError,'immutable'):service_profile.snapshot_references('18',output)
        self.assertEqual(service_profile.library_snapshot('18')[0],descriptor)

    def test_evaluation_bank_cannot_be_relabelled_as_business_bank(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as directory:
            references=Path(directory)/'references.jsonl';references.write_text('{"text":"evaluation-bank"}\n',encoding='utf-8')
            library={'generationId':'18','documentsDigest':retrieval._digest([{'text':'business-bank'}])}
            spec={'bundle':directory,'library':library}
            with patch.object(v3_runtime,'verify_bundle',return_value={'references':{'path':str(references)}}),patch.object(service_profile,'library_snapshot',return_value=(library,{})):
                with self.assertRaisesRegex(ValueError,'cannot substitute'):service_profile._verified_material(spec)

    def test_incomplete_material_never_creates_a_ready_profile_and_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as directory:
            profiles=Path(directory)/'profiles'
            with patch.object(service_profile,'PROFILE_ROOT',profiles),patch.object(service_profile,'library_snapshot',return_value=({},{})),patch.object(service_profile,'_verified_material',side_effect=ValueError('Training/evaluation pending')):
                with self.assertRaisesRegex(ValueError,'pending'):
                    service_profile.create_profile(name='候选模型',generation='18',bundle=directory,index=directory,calibration=directory,quality_evidence={})
            self.assertFalse(profiles.exists())
        with self.assertRaises(ValueError):service_profile.profile_directory('../another')


if __name__=='__main__':unittest.main()
