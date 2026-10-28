import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_workbench import document_profiles as profiles

class DocumentProfileTests(unittest.TestCase):
    def test_policy_and_model_identities_are_pinned_and_resource_wait_does_not_fall_back(self):
        profile=profiles.configuration({'grammar':'a'*64,'imageText':'b'*64})
        profiles.validate(profile)
        wrong=copy.deepcopy(profile);wrong['devicePreference']='cpu'
        with self.assertRaises(ValueError):profiles.validate(wrong)
        torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:True,mem_get_info=lambda:(int(7.5*1024**3),8*1024**3)))
        with patch.dict(sys.modules,{'torch':torch}):
            self.assertEqual(profiles.device('GRAMMAR_MODEL',profile),'cuda')
            torch.cuda.mem_get_info=lambda:(1024**3,8*1024**3)
            with self.assertRaises(BlockingIOError):profiles.device('GRAMMAR_MODEL',profile)

if __name__=='__main__':unittest.main()
