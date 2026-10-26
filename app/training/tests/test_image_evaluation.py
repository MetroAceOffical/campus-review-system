import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evaluate_image_geometry as evaluation


class ImageEvaluationTests(unittest.TestCase):
    def test_failures_remain_in_denominator_and_bootstrap_uses_image_families(self):
        rows=[{'imageFamilyId':'one','transformation':'resize','acceptedCorrespondence':True,'scopeCorrect':True,'elapsedMs':5.,'error':None},
              {'imageFamilyId':'one','transformation':'jpeg','acceptedCorrespondence':True,'scopeCorrect':True,'elapsedMs':6.,'error':None},
              {'imageFamilyId':'two','transformation':'crop','acceptedCorrespondence':False,'scopeCorrect':False,'elapsedMs':7.,'error':'decode failed'}]
        summary=evaluation.summarize(rows)
        self.assertEqual(summary['queries'],3)
        self.assertEqual(summary['failedQueries'],1)
        self.assertEqual(summary['automaticImageFamilies'],2)
        self.assertAlmostEqual(summary['knownSourceAcceptance'],2/3)
        self.assertEqual(summary['byTransformation']['crop']['queries'],1)
        self.assertEqual(summary['realHardNegativeTruthCount'],0)
        self.assertFalse(summary['qualityAccepted'])


if __name__=='__main__':unittest.main()
