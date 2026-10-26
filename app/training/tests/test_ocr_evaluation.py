import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evaluate_ocr_recovery as evaluation


class OcrEvaluationTests(unittest.TestCase):
    def test_known_rendered_text_has_cer_and_region_coverage_but_real_untranscribed_text_does_not(self):
        polygon=[[0,0],[100,0],[100,20],[0,20]]
        sample={'cerEligible':True,'groundTruthText':'活动通知','groundTruthLines':[{'text':'活动通知','polygon':polygon}]}
        prediction={'combinedText':'活动通告','recognitionLines':[{'polygon':polygon}]}
        metric=evaluation.score_sample(sample,prediction)
        self.assertEqual(metric['editDistance'],1)
        self.assertEqual(metric['CER'],.25)
        self.assertEqual(metric['coveredTruthLines'],1)
        real=evaluation.score_sample({'cerEligible':False,'groundTruthText':None},prediction)
        self.assertIsNone(real['CER'])
        failure=evaluation.score_sample(sample,{'combinedText':'','recognitionLines':[]})
        self.assertEqual(failure['CER'],1.)


if __name__=='__main__':unittest.main()
