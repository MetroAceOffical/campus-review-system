import unittest
from text_verifier_metrics import summarize_cases


class VerifierCoverageTest(unittest.TestCase):
    def test_unassessed_normal_is_abstention_not_correct_negative(self):
        normal=dict(normal=True,completeExpectedSources=False,expectedSources=[],correctSources=[],scopedNormalAlert=False,alerts=[],unjudgedAlerts=[])
        positive=dict(normal=False,completeExpectedSources=True,expectedSources=['a'],correctSources=['a'],scopedNormalAlert=False,alerts=['a'],unjudgedAlerts=[])
        rows=[dict(caseId='unknown-normal',allSelectedSourcesAssessed=False,sources=[dict(result=dict(assessed=False,status='INVALID_MODEL_SUPPORT'))],baseline=normal,candidate=normal),
              dict(caseId='good-normal',allSelectedSourcesAssessed=True,sources=[dict(result=dict(assessed=True,status='ASSESSED'))],baseline=normal,candidate=normal),
              dict(caseId='good-positive',allSelectedSourcesAssessed=True,sources=[dict(result=dict(assessed=True,status='ASSESSED'))],baseline=positive,candidate=positive)]
        result=summarize_cases(rows)
        self.assertEqual(1,result['coverage']['abstainedNormalDocuments'])
        self.assertEqual(2,result['coverage']['comparableDocuments'])
        self.assertEqual(1,result['completeSelectedCandidateComparison']['candidate']['normalDocuments'])
        self.assertEqual(2,result['operationalAlertsWithAbstentions']['candidate']['normalDocuments'])
        self.assertIsNone(result['normalPopulationFpr'])


if __name__=='__main__':unittest.main()
