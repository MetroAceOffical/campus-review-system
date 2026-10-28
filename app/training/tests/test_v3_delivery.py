import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection.v3_delivery import merge_report, prediction_record

class V3DeliveryTests(unittest.TestCase):
    def test_merge_keeps_literal_acceptance_and_real_task_scores(self):
        base={'evidence':[{'sourceRevisionId':'s','sourceKey':'BODY','sourceWorkId':'w','acceptedCandidate':False,'semanticWindows':[]}]}
        result={'pairs':[{'sourceRevisionId':'s','sourceKey':'BODY','queryStart':0,'queryEnd':2,'sourceStart':1,'sourceEnd':3,'queryText':'甲乙','sourceText':'甲乙','score':.9,'scoreType':'CONTENT_CORRESPONDENCE_SCORE','evidenceId':'p'}],
                'aggregation':{'sources':[{'sourceRevisionId':'s','sourceKey':'BODY','features':{'informativeQueryCoverage':.5,'informativeSourceCoverage':.4},'supportedWindowPairs':1,'queryIntervals':[[0,2]]}]},
                'sourceDecisions':[{'sourceRevisionId':'s','sourceKey':'BODY','semanticDecision':'LOCAL_CORRESPONDENCE','decisionScores':{'whole':.1,'local':.9}}],
                'featureConfig':{'pairScoreThreshold':.5},'coverageStatus':'PARTIAL','checkedRegions':[{'start':0,'end':2}],'evaluatedPairCount':1,'candidateCount':1,'configId':'v3','calibrationStatus':'APPLIED'}
        merged=merge_report(base,result,[{'sourceRevisionId':'s','sourceKey':'BODY','sourceWorkId':'w','title':'来源','text':'。甲乙'}])
        self.assertFalse(merged['evidence'][0]['acceptedCandidate'])
        self.assertTrue(merged['evidence'][0]['semanticSummary']['suspectedReuse'])
        self.assertEqual(merged['evidence'][0]['semanticWindows'][0]['scoreType'],'CONTENT_CORRESPONDENCE_SCORE')
        self.assertEqual(merged['coverageStatus'],'PARTIAL')
        self.assertNotIn('semanticSummary',base['evidence'][0])
        with self.assertRaises(ValueError):merge_report(base,result,[])
    def test_prediction_failure_and_actual_method_identity_are_preserved(self):
        query={'queryId':'q','querySha256':'qhash'}
        result={'coverageStatus':'FAILED','pairs':[],'sourceDecisions':[],'candidateSources':[],'featureConfig':{'pairScoreThreshold':.5},'elapsedMs':12}
        record=prediction_record(query,result,'m','r')
        self.assertEqual(record['coverageStatus'],'FAILED')
        self.assertIsNone(record['decisionScore'])
        self.assertEqual(record['methodConfigId'],'m')

if __name__=='__main__':unittest.main()
