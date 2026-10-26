import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import aggregation


class V3AggregationTests(unittest.TestCase):
    def setUp(self):
        self.config={'modelConfigId':'pending-trained-model-test-fixture','pairScoreThreshold':.5}
        self.calibration_events={'event'+str(i) for i in range(6)}

    def pair(self,source,qstart,qend,sstart,send):
        return {'sourceRevisionId':source,'sourceKey':'BODY','queryStart':qstart,'queryEnd':qend,
                'sourceStart':sstart,'sourceEnd':send,'score':.9,'scoreType':'CONTENT_CORRESPONDENCE_SCORE'}

    def test_overlapping_windows_and_templates_do_not_inflate_coverage(self):
        pairs=[self.pair('a',0,60,0,60),self.pair('a',40,80,30,70)]
        result=aggregation.summarize_sources(pairs,100,{'a:BODY':120},self.config,query_templates=[(0,20)],source_templates={'a:BODY':[(0,10)]})
        features=result['sources'][0]['features']
        self.assertAlmostEqual(features['rawQueryCoverage'],.8)
        self.assertAlmostEqual(features['informativeQueryCoverage'],.75)
        self.assertAlmostEqual(features['informativeSourceCoverage'],60/110)
        duplicate=aggregation.summarize_sources(pairs*3,100,{'a:BODY':120},self.config,query_templates=[(0,20)],source_templates={'a:BODY':[(0,10)]})
        self.assertEqual(result,duplicate)

    def test_shared_query_regions_are_merged_across_sources_and_bad_offsets_rejected(self):
        pairs=[self.pair('a',0,20,0,20),self.pair('b',0,20,0,20),self.pair('b',20,40,20,40)]
        result=aggregation.summarize_sources(pairs,100,{'a:BODY':100,'b:BODY':100},self.config)
        self.assertAlmostEqual(result['allSourceQueryCoverage'],.4)
        with self.assertRaises(ValueError):aggregation.summarize_sources([self.pair('a',90,110,0,20)],100,{'a:BODY':100},self.config)
        template_only=aggregation.summarize_sources([pairs[0]],100,{'a:BODY':100},self.config,query_templates=[(0,20)])
        self.assertEqual(template_only['sources'][0]['features']['informativeQueryCoverage'],0.)

    def test_caption_identity_with_colons_is_preserved_without_parsing_the_composite_key(self):
        pair={**self.pair('revision',0,20,0,20),'sourceKey':'CAPTION:node:one'}
        result=aggregation.summarize_sources([pair],100,{'revision:CAPTION:node:one':100},self.config)
        self.assertEqual(result['sources'][0]['sourceRevisionId'],'revision')
        self.assertEqual(result['sources'][0]['sourceKey'],'CAPTION:node:one')

    def test_calibrator_rejects_noncalibration_events_and_binds_the_feature_configuration(self):
        rows=[]
        for i in range(6):
            features={name:float(i>=3) for name in aggregation.FEATURE_NAMES}
            rows.append({'features':features,'wholeTarget':int(i>=3),'localTarget':int(i>=3),
                         'split':'calibration','queryEventClusterId':'event'+str(i),'labelOrigin':'controlled_construction','labelConfidence':'known',
                         'featureConfigSha256':aggregation._feature_identity(self.config)})
        with self.assertRaises(ValueError):aggregation.fit_calibrator([{**rows[0],'split':'final'}]+rows[1:],self.config,'a'*64,calibration_events=self.calibration_events,minimum_rows=6,minimum_events=3)
        with self.assertRaises(ValueError):aggregation.fit_calibrator(rows,self.config,'a'*64,forbidden_events={'event0'},calibration_events=self.calibration_events,minimum_rows=6,minimum_events=3)
        model=aggregation.fit_calibrator(rows,self.config,'a'*64,calibration_events=self.calibration_events,minimum_rows=6,minimum_events=3)
        self.assertEqual(len(model['aggregationAlgorithmSha256']),64)
        model=json.loads(json.dumps(model))
        with self.assertRaises(ValueError):aggregation.decide(rows[-1]['features'],model,self.config,{'whole':.5,'local':.5})
        decision=aggregation.decide(rows[-1]['features'],model,self.config,{'whole':.5,'local':.5},coverage_status='COMPLETE',require_formal_scale=False)
        self.assertEqual(decision['semanticDecision'],'WHOLE_CORRESPONDENCE')
        with self.assertRaises(ValueError):aggregation.decide(rows[0]['features'],model,{**self.config,'modelConfigId':'different'},{'whole':.5,'local':.5})
        partial=aggregation.decide(rows[0]['features'],model,self.config,{'whole':.5,'local':.5},coverage_status='PARTIAL',require_formal_scale=False)
        self.assertEqual(partial['semanticDecision'],'INSUFFICIENT_EVIDENCE')
        self.assertFalse(partial['noReuseClaim'])

    def test_calibrator_cannot_relabel_features_from_another_model_or_unknown_event(self):
        rows=[]
        for i in range(6):
            rows.append({'features':{name:float(i>=3) for name in aggregation.FEATURE_NAMES},'wholeTarget':int(i>=3),'localTarget':int(i>=3),
                         'split':'calibration','queryEventClusterId':'event'+str(i),'labelOrigin':'controlled_construction','labelConfidence':'known',
                         'featureConfigSha256':aggregation._feature_identity(self.config)})
        mismatched=[{**rows[0],'featureConfigSha256':'0'*64}]+rows[1:]
        with self.assertRaises(ValueError):aggregation.fit_calibrator(mismatched,self.config,'a'*64,calibration_events=self.calibration_events,minimum_rows=6,minimum_events=3)
        unknown=[{**rows[0],'queryEventClusterId':'neural-training-event'}]+rows[1:]
        with self.assertRaises(ValueError):aggregation.fit_calibrator(unknown,self.config,'a'*64,calibration_events=self.calibration_events,minimum_rows=6,minimum_events=3)


if __name__=='__main__':unittest.main()
