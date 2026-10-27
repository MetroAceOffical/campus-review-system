import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import text_evaluation as evaluation


class TextEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.references=[{'sourceRevisionId':key,'sourceKey':'BODY','text':text} for key,text in [('a','甲方🙂报道事实内容'),('b','乙方不同的事实内容')]]
        self.query={'queryId':'q','query':'新的🙂报道事实内容','querySha256':hashlib.sha256('新的🙂报道事实内容'.encode()).hexdigest(),
                    'category':'whole_synonym','split':'final','eventClusterIds':['event-a'],'expectedSourceIds':['a'],
                    'truthScope':'known_positive_sources_only','labelConfidence':'known','labelOrigin':'controlled_construction',
                    'sourceMappings':[{'sourceRevisionId':'a','sourceKey':'BODY','queryStart':0,'queryEnd':9,'sourceStart':0,'sourceEnd':9,'mappingType':'PARAPHRASE_SEGMENT'}]}

    def prediction(self,query=None,source='a',status='COMPLETE'):
        query=query or self.query;reference=next(r for r in self.references if r['sourceRevisionId']==source)
        return {'queryId':query['queryId'],'querySha256':query['querySha256'],'methodConfigId':'method1','referenceManifestSha256':'a'*64,'coverageStatus':status,
                'candidateSources':[{'sourceRevisionId':source}],
                'sourceDecisions':[{'sourceRevisionId':source,'sourceKey':'BODY','semanticDecision':'LOCAL_CORRESPONDENCE'}],
                'pairs':[{'sourceRevisionId':source,'sourceKey':'BODY','queryStart':0,'queryEnd':len(query['query']),'queryText':query['query'],
                          'sourceStart':0,'sourceEnd':len(reference['text']),'sourceText':reference['text'],'supported':True}]}

    def score(self,queries,predictions):
        return evaluation.score_predictions(queries,predictions,self.references,'method1',reference_sha256='a'*64,bootstrap_resamples=50)

    def test_missing_failed_and_wrong_source_predictions_stay_in_recall_denominators(self):
        second={**self.query,'queryId':'missing','eventClusterIds':['event-b']}
        result=self.score([self.query,second],[self.prediction()])
        self.assertEqual(result['queries'],2)
        self.assertEqual(result['missingPredictions'],1)
        self.assertEqual(result['rates']['correctSourceEvidenceRate'],{'numerator':1,'denominator':2,'value':.5})
        wrong=self.score([self.query],[self.prediction(source='b')])
        self.assertEqual(wrong['rates']['correctSourceEvidenceRate']['value'],0.)
        self.assertEqual(wrong['unknownExtraSourceAcceptances'],1)
        failed=self.score([self.query],[self.prediction(status='FAILED')])
        self.assertEqual(failed['rates']['correctSourceEvidenceRate']['value'],0.)

    def test_codepoint_text_and_source_identity_are_validated_before_evidence_counts(self):
        prediction=self.prediction();prediction['pairs'][0]['queryText']='wrong'
        result=self.score([self.query],[prediction])
        self.assertEqual(result['invalidEvidence'],1)
        self.assertEqual(result['rates']['correctSourceEvidenceRate']['value'],0.)
        self.assertEqual(result['rates']['validEvidenceOffsets']['value'],0.)
        with self.assertRaises(ValueError):self.score([self.query],[{**self.prediction(),'querySha256':'0'*64}])
        with self.assertRaises(ValueError):self.score([self.query],[{**self.prediction(),'methodConfigId':'other'}])
        with self.subTest('reference manifest'):
            with self.assertRaises(ValueError):self.score([self.query],[{**self.prediction(),'referenceManifestSha256':'b'*64}])
        with self.subTest('accepted field identity'):
            wrong_field=self.prediction();wrong_field['sourceDecisions'][0]['sourceKey']='CAPTION:other'
            result=self.score([self.query],[wrong_field])
            self.assertEqual(result['rates']['correctSourceEvidenceRate']['value'],0.)

    def test_unknown_negative_scope_is_not_a_zero_false_positive_rate(self):
        normal={**self.query,'queryId':'normal','category':'template_normal','expectedSourceIds':[],
                'sourceMappings':[],'truthScope':'unknown_negative_scope','labelConfidence':'unknown'}
        result=self.score([normal],[self.prediction(normal)])
        self.assertIsNone(result['rates']['normalAnySourceFalsePromptRate']['value'])
        self.assertEqual(result['unscoredNormalQueries'],1)
        self.assertIsNone(result['precisionRecall']['curve'])

    def test_closed_normal_scope_counts_any_source_alert_and_unresolved_failures(self):
        normal={**self.query,'queryId':'normal','category':'template_normal','expectedSourceIds':[],'sourceMappings':[],
                'truthScope':'closed_reference_set','negativeScope':{'referenceManifestSha256':'a'*64,
                'excludedSourceRevisionIds':[],'supportedNegativeSources':['a','b'],'auditVerified':True}}
        other={**normal,'queryId':'missing-normal','eventClusterIds':['other-event']}
        result=self.score([normal,other],[self.prediction(normal,source='b')])
        self.assertEqual(result['rates']['normalAnySourceFalsePromptRate']['value'],.5)
        self.assertEqual(result['rates']['normalFalsePromptWorstCaseRate']['value'],1.)
        incomplete={**normal,'negativeScope':{**normal['negativeScope'],'supportedNegativeSources':['a']}}
        with self.assertRaises(ValueError):self.score([incomplete],[])

    def test_multi_source_all_found_and_bootstrap_use_connected_event_families(self):
        multi={**self.query,'queryId':'multi','category':'multi_source','eventClusterIds':['event-a','event-b'],
               'expectedSourceIds':['a','b'],'sourceMappings':self.query['sourceMappings']+[
                   {'sourceRevisionId':'b','sourceKey':'BODY','queryStart':0,'queryEnd':9,'sourceStart':0,'sourceEnd':9,'mappingType':'PARAPHRASE_SEGMENT'}]}
        other={**self.query,'queryId':'other','eventClusterIds':['event-b']}
        result=self.score([self.query,multi,other],[self.prediction(),self.prediction(multi),self.prediction(other)])
        self.assertEqual(result['automaticQueryFamilies'],1)
        self.assertEqual(result['rates']['multiSourceAllFoundRate']['value'],0.)
        self.assertEqual(result['rates']['correctSourceEvidenceRate']['value'],1.)
        self.assertEqual(result['multiSourceExpectedSources'],2)

    def test_pr_tied_scores_are_grouped_and_missing_scores_never_become_zeroes(self):
        normal={**self.query,'queryId':'normal','category':'template_normal','eventClusterIds':['event-b'],
                'expectedSourceIds':[],'sourceMappings':[],'truthScope':'closed_reference_set',
                'negativeScope':{'referenceManifestSha256':'a'*64,'excludedSourceRevisionIds':[],
                                 'supportedNegativeSources':['a','b'],'auditVerified':True}}
        positive={**self.prediction(),'decisionScore':.8}
        negative={**self.prediction(normal,source='b'),'decisionScore':.8}
        result=self.score([self.query,normal],[positive,negative])
        self.assertEqual(result['precisionRecall']['curve'],[{'threshold':.8,'precision':.5,'recall':1.,'truePositives':1,'falsePositives':1}])
        result=self.score([self.query,normal],[positive,self.prediction(normal,source='b')])
        self.assertIsNone(result['precisionRecall']['curve'])
        self.assertEqual(result['precisionRecall']['measuredScores'],1)


if __name__=='__main__':unittest.main()
