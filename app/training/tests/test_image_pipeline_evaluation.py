import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluate_image_pipeline as evaluation


class PipelineEvaluationTests(unittest.TestCase):
    def test_correct_source_failures_and_unknown_sources_are_separate(self):
        rows = [dict(queryId='a', imageFamilyId='one', transformation='resize',
                     sourceRank=1, baselineAccepted=True, top20Accepted=True,
                     enhancedAccepted=True, scopeCorrect=True, elapsedMs=10,
                     unknownAcceptedSources=2, error=None),
                dict(queryId='b', imageFamilyId='two', transformation='crop',
                     sourceRank=11, baselineAccepted=False, top20Accepted=True,
                     enhancedAccepted=False, scopeCorrect=False, elapsedMs=20,
                     unknownAcceptedSources=1, error='geometry failed'),
                dict(queryId='c', imageFamilyId='two', transformation='crop',
                     sourceRank=None, baselineAccepted=False, top20Accepted=False,
                     enhancedAccepted=False, scopeCorrect=False, elapsedMs=30,
                     unknownAcceptedSources=0, error='decode failed')]
        result = evaluation.summarize(rows)
        self.assertEqual(result['queries'], 3)
        self.assertEqual(result['failedQueries'], 2)
        self.assertEqual(result['automaticImageFamilies'], 2)
        self.assertEqual(result['dinoTop20Retrieved'], 2)
        self.assertEqual(result['baselineAccepted'], 1)
        self.assertEqual(result['top20Accepted'], 2)
        self.assertEqual(result['enhancedAccepted'], 1)
        self.assertAlmostEqual(result['rates']['enhancedAccepted'], 1/3)
        self.assertEqual(result['byTransformation']['crop']['queries'], 2)
        self.assertEqual(result['unknownAcceptedSources'], 3)
        self.assertIsNone(result['falsePositiveRate'])
        self.assertFalse(result['qualityAccepted'])
        self.assertEqual(result['finalQueriesEvaluated'], 0)

    def test_resume_requires_exact_order_and_immutable_query_identity(self):
        queries = [dict(queryId='a', sha256='1'), dict(queryId='b', sha256='2')]
        evaluation.validate_saved([dict(queryId='a', querySha256='1', runId='r')], queries, 'r')
        for saved in ([dict(queryId='b', querySha256='2', runId='r')],
                      [dict(queryId='a', querySha256='changed', runId='r')],
                      [dict(queryId='a', querySha256='1', runId='other')]):
            with self.assertRaises(ValueError):
                evaluation.validate_saved(saved, queries, 'r')


if __name__ == '__main__':
    unittest.main()
