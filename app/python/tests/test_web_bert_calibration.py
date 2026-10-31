import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection.web_bert_calibration import choose_threshold
class CalibrationTest(unittest.TestCase):
    def test_uses_interior_operating_points_rather_than_an_observed_score(self):
        scores=[.1,.49,.49175673723220825,.8];fit=choose_threshold([0,0,1,1],scores)
        self.assertNotIn(fit['threshold'],scores);self.assertGreater(fit['minimumValidationMargin'],0)
        self.assertEqual(1,fit['macroF1']);self.assertEqual(128,fit['maxTokens'])
if __name__=='__main__':unittest.main()
