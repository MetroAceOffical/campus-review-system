"""Opt-in real-model probe; never train and never overwrite frozen outputs."""
import os
import unittest

@unittest.skipUnless(os.environ.get('CAMPUS_REAL_MODELS')=='1','RealModels not requested; not counted as model success')
class RealTextTest(unittest.TestCase):
    def test_new_text_matches_real_source_and_filters_self_before_topk(self):
        from campus_detection.probe import run_text_probe
        result=run_text_probe()
        self.assertTrue(result['matchingSourceFound'])
        self.assertTrue(result['selfExcluded'])
        self.assertEqual(result['semanticAlpha'],0)

if __name__=='__main__': unittest.main()
