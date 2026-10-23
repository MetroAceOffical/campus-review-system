import os
import unittest

@unittest.skipUnless(os.environ.get('CAMPUS_REAL_MODELS')=='1','RealModels not requested; not counted as model success')
class RealImageTest(unittest.TestCase):
    def test_actual_dino_encoding_matches_reference(self):
        from campus_detection.probe import run_image_probe
        result=run_image_probe()
        self.assertTrue(result['actualEncoding'])
        self.assertGreater(result['similarity'],0.99)
        self.assertTrue(result['configCompatible'])

if __name__=='__main__': unittest.main()
