import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import alignment,aggregation,retrieval,v3_pipeline,v3_runtime
from ablation_models import register,verify_bundle,validate_variant
from text_evaluation import _supported


class AblationModelsTests(unittest.TestCase):
    def test_unadapted_scores_keep_their_type_and_require_matching_feature_policy(self):
        pair={'queryStart':0,'queryEnd':2,'queryText':'甲乙','sourceStart':0,'sourceEnd':2,'sourceText':'甲丙','sourceRevisionId':'a','sourceKey':'BODY'}
        plan={'pairs':[pair],'scheduledPairCount':1,'coveragePlan':'COMPLETE','candidatePairsBeforeBudget':1,'deferredCandidatePairs':0,'emptyCandidateRegions':[],'pairBudget':2048,'jointTokenBudget':512}
        for kind in ('LEGACY_SEMANTIC_SCORE','PRETRAINED_RELEVANCE_SCORE'):
            result=alignment.evaluate_pairs(plan,lambda p:.8,'fixed-test-head',score_type=kind)
            self.assertEqual(result['pairs'][0]['scoreType'],kind)
            feature={'modelConfigId':'fixed-test-head','pairScoreThreshold':.5,'pairScoreType':kind}
            summary=aggregation.summarize_sources(result['pairs'],2,{'a:BODY':2},feature)
            self.assertEqual(summary['sources'][0]['supportedWindowPairs'],1)
            with self.assertRaises(ValueError):aggregation.summarize_sources(result['pairs'],2,{'a:BODY':2},{'pairScoreThreshold':.5})
        with self.assertRaises(ValueError):alignment.evaluate_pairs(plan,lambda p:.8,'fixed',score_type='COSINE')

    def test_variant_cannot_substitute_bert_for_unadapted_m3_or_claim_training(self):
        for variant,head,trained in [('untrained-dense','LEGACY_SEMANTIC_SCORE',False),('trained-dense-unadapted-reranker','PRETRAINED_RELEVANCE_SCORE',True)]:
            row={'variant':variant,'reranker':{'scoreType':head},'campusRetrieverTrainingComplete':trained,'correspondenceTrainingComplete':False,'productActivated':False}
            validate_variant(row)
            wrong=copy.deepcopy(row);wrong['correspondenceTrainingComplete']=True
            with self.assertRaises(ValueError):validate_variant(wrong)
            wrong=copy.deepcopy(row);wrong['reranker']['scoreType']='CONTENT_CORRESPONDENCE_SCORE'
            with self.assertRaises(ValueError):validate_variant(wrong)

    def test_typed_heads_follow_actual_pipeline_and_exclusions_before_topk(self):
        import test_v3_pipeline as baseline
        fixture=baseline.V3PipelineTests();fixture.setUp()
        for kind in ('LEGACY_SEMANTIC_SCORE','PRETRAINED_RELEVANCE_SCORE','CONTENT_CORRESPONDENCE_SCORE'):
            fixture.called=[];fixture.reranker['configuration']={'configId':'typed-'+kind}
            if kind!='CONTENT_CORRESPONDENCE_SCORE':fixture.reranker['configuration']['scoreType']=kind
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'runtime') as tmp:
                result=fixture.run_pipeline(Path(tmp)/'index',exclude_source_revision_ids={'a'})
            self.assertEqual(set(fixture.called),{'b','c'})
            self.assertEqual(result['featureConfig'].get('pairScoreType','CONTENT_CORRESPONDENCE_SCORE'),kind)
            self.assertTrue(all(p['scoreType']==kind for p in result['pairs']))
            self.assertEqual(result['coverageStatus'],'COMPLETE')
            pair={**result['pairs'][0],'score':.9}
            self.assertTrue(_supported(pair,{'featureConfig':result['featureConfig']}))
            self.assertFalse(_supported({**pair,'scoreType':'COSINE'},{'featureConfig':result['featureConfig']}))
            other='LEGACY_SEMANTIC_SCORE' if kind=='PRETRAINED_RELEVANCE_SCORE' else 'PRETRAINED_RELEVANCE_SCORE'
            self.assertFalse(_supported({**pair,'scoreType':other},{'featureConfig':result['featureConfig']}))

    @unittest.skipUnless((Path(__file__).resolve().parents[3]/'runtime/datasets/text-evaluation-corrected-20261028-v3/READY').is_file(),'Local downloaded assets and frozen protocol required')
    def test_real_base_assets_register_offline_only_and_unfinished_campus_run_is_refused(self):
        root=Path(__file__).resolve().parents[3]
        references=root/'runtime/datasets/text-evaluation-corrected-20261028-v3/references.jsonl'
        with tempfile.TemporaryDirectory(dir=root/'runtime') as tmp:
            bundle=Path(tmp)/'base';manifest=register('untrained-dense',references,bundle)
            self.assertEqual(verify_bundle(bundle)['bundleId'],manifest['bundleId'])
            self.assertFalse(manifest['campusRetrieverTrainingComplete'])
            self.assertEqual(manifest['reranker']['scoreType'],'LEGACY_SEMANTIC_SCORE')
            with self.assertRaises(ValueError):v3_runtime.verify_bundle(bundle)
            with self.assertRaises(ValueError):register('trained-dense-unadapted-reranker',references,Path(tmp)/'missing',root/'runtime/experiments/final-training-20261028/retriever-campus-v2')
            changed=v3_runtime.read(bundle/'bundle.json');changed['references']['sha256']='0'*64
            (bundle/'bundle.json').write_text(__import__('json').dumps(changed),encoding='utf-8')
            with self.assertRaises(ValueError):verify_bundle(bundle)


if __name__=='__main__':unittest.main()
