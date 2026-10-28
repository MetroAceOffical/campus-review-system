import sys
import tempfile
import unittest
from pathlib import Path
import json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import analyze_image_evaluation as analysis


class ImageErrorAnalysisTests(unittest.TestCase):
    def test_source_acceptance_regression_and_geometry_reason_are_separate(self):
        expected=[dict(queryId='a',sha256='1',imageFamilyId='f',transformation='jpeg'),
                  dict(queryId='b',sha256='2',imageFamilyId='f',transformation='crop'),
                  dict(queryId='c',sha256='3',imageFamilyId='g',transformation='crop')]
        rows=[dict(queryId='a',querySha256='1',runId='run',imageFamilyId='f',transformation='jpeg',sourceRank=1,
                   baselineAccepted=True,enhancedAccepted=False,scopeCorrect=False,error=None,
                   geometry={'qualityFlags':['INSUFFICIENT_SPATIAL_SUPPORT']},unknownAcceptedSources=0),
              dict(queryId='b',querySha256='2',runId='run',imageFamilyId='f',transformation='crop',sourceRank=11,
                   baselineAccepted=False,enhancedAccepted=True,scopeCorrect=False,error=None,
                   geometry={'scope':'WHOLE_IMAGE'},unknownAcceptedSources=0)]
        value=analysis.summarize(rows,expected)
        self.assertEqual(value['processed'],2)
        self.assertEqual(value['pendingQueries'],1)
        self.assertEqual(value['completedFamilies'],1)
        self.assertEqual(value['enhancedGainCount'],1)
        self.assertEqual(value['enhancedRegressionCount'],1)
        self.assertEqual(value['reasonCounts'],{'INSUFFICIENT_SPATIAL_SUPPORT':1,'WRONG_SCOPE':1})
        self.assertIsNone(value['falsePositiveRate'])
        self.assertEqual(value['byTransformation']['crop']['pending'],1)

    def test_only_committed_prefix_is_read_and_previous_prefix_cannot_change(self):
        expected=[dict(queryId='a',sha256='1'),dict(queryId='b',sha256='2')]
        with tempfile.TemporaryDirectory(dir=analysis.ROOT/'runtime') as directory:
            path=Path(directory)/'predictions.jsonl'
            row=dict(queryId='a',querySha256='1',runId='run')
            raw=(json.dumps(row)+'\n').encode()
            path.write_bytes(raw+b'{unfinished')
            rows,receipt=analysis.read_prefix(path,1,expected,'run')
            self.assertEqual(len(rows),1)
            path.write_bytes(raw+(json.dumps(dict(queryId='b',querySha256='2',runId='run'))+'\n').encode())
            self.assertEqual(len(analysis.read_prefix(path,2,expected,'run',receipt)[0]),2)
            path.write_bytes(raw.replace(b'"1"',b'"x"'))
            with self.assertRaises(ValueError):analysis.read_prefix(path,1,expected,'run',receipt)


if __name__=='__main__':unittest.main()
