import copy
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import retrieval,v3_pipeline


class V3PipelineTests(unittest.TestCase):
    def setUp(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        self.identity={'weightSha256':'a'*64,'tokenizerSha256':'b'*64,'pooling':'CLS','normalization':'L2','precision':'FP32'}
        self.retriever={'identity':self.identity,'tokenizer':self.tokenizer,'encode':self.encode}
        self.called=[]
        self.reranker={'configuration':{'configId':'task-fixture'},'scorePair':self.score,'tokenizer':self.tokenizer}
        self.documents=[{'sourceRevisionId':key,'sourceWorkId':'w-'+key,'sourceKey':'CAPTION:node:one' if key=='a' else 'BODY',
                         'manuscriptId':'own' if key=='self' else 'm-'+key,'text':text} for key,text in
                        [('self','alpha query phrase'),('a','alpha reference narrative'),('b','beta reference narrative'),('c','gamma reference narrative')]]

    def encode(self,texts):
        result=np.zeros((len(texts),768),dtype=np.float32)
        for i,text in enumerate(texts):
            value=.9 if 'alpha' in text else -.1 if 'beta' in text else -.2
            result[i,0]=value;result[i,1]=np.sqrt(1-value*value)
        return result

    def score(self,pair):
        self.called.append(pair['sourceRevisionId'])
        return .9 if pair['sourceRevisionId']=='a' else .2

    def run_pipeline(self,root,**kwargs):
        retrieval.build_dense_index(self.documents,self.tokenizer,self.encode,root,self.identity)
        index=retrieval.load_dense_index(root,self.identity)
        try:
            return v3_pipeline.analyze_correspondence('alpha query phrase',index,self.documents,self.retriever,self.reranker,
                literal_hits=[{'sourceRevisionId':'self'},{'sourceRevisionId':'b'}],exclude_manuscript_id='own',**kwargs)
        finally:index['vectors']._mmap.close()

    def test_dense_and_literal_pool_flow_through_real_execution_and_source_features(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_pipeline(Path(folder)/'index')
        self.assertEqual(set(self.called),{'a','b','c'})
        self.assertEqual({row['sourceRevisionId'] for row in result['candidateSources']},{'a','b','c'})
        self.assertEqual(result['candidateCount'],3)
        self.assertEqual(result['evaluatedPairCount'],3)
        self.assertEqual(result['coverageStatus'],'COMPLETE')
        self.assertEqual(result['calibrationStatus'],'PENDING_CALIBRATION')
        self.assertEqual(result['sourceDecisions'],[])
        a=next(row for row in result['aggregation']['sources'] if row['sourceRevisionId']=='a')
        self.assertEqual(a['sourceKey'],'CAPTION:node:one')
        self.assertEqual(a['features']['informativeQueryCoverage'],1.)
        self.assertNotIn('acceptedCandidate',result)
        self.assertFalse(result['noReuseClaim'])

    def test_budget_failure_and_unfitted_calibration_are_not_full_or_negative_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_pipeline(Path(folder)/'index',policy={'pairBudget':1})
        self.assertEqual(result['coverageStatus'],'PARTIAL')
        self.assertEqual(result['evaluatedPairCount'],1)
        self.assertEqual(result['deferredCandidatePairs'],2)
        self.assertEqual(result['sourceDecisions'],[])
        def failed(pair):raise RuntimeError('model call failed')
        self.reranker={**self.reranker,'scorePair':failed}
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_pipeline(Path(folder)/'index')
        self.assertEqual(result['coverageStatus'],'FAILED')
        self.assertEqual(result['failedPairCount'],3)
        self.assertEqual(result['checkedRegions'],[])

    def test_changed_library_or_encoder_cannot_reuse_a_frozen_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'index';retrieval.build_dense_index(self.documents,self.tokenizer,self.encode,root,self.identity)
            index=retrieval.load_dense_index(root,self.identity)
            try:
                changed=copy.deepcopy(self.documents);changed[1]['text']+=' changed'
                with self.assertRaises(ValueError):v3_pipeline.analyze_correspondence('query',index,changed,self.retriever,self.reranker)
                wrong={**self.retriever,'identity':{**self.identity,'weightSha256':'c'*64}}
                with self.assertRaises(ValueError):v3_pipeline.analyze_correspondence('query',index,self.documents,wrong,self.reranker)
                with self.assertRaises(ValueError):v3_pipeline.analyze_correspondence('query',index,self.documents,self.retriever,self.reranker,calibrator={})
                no_tokenizer={key:value for key,value in self.reranker.items() if key!='tokenizer'}
                with self.subTest('missing task tokenizer'):
                    with self.assertRaises(ValueError):v3_pipeline.analyze_correspondence('query',index,self.documents,self.retriever,no_tokenizer)
                def failed(pair):raise RuntimeError('failed')
                with self.subTest('invalid calibrator with failed inference'):
                    with self.assertRaises(ValueError):v3_pipeline.analyze_correspondence('query',index,self.documents,self.retriever,
                        {**self.reranker,'scorePair':failed},calibrator={},thresholds={'whole':.5,'local':.5})
            finally:index['vectors']._mmap.close()

    def test_repeated_literal_fields_do_not_consume_distinct_source_rank_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'index';retrieval.build_dense_index(self.documents,self.tokenizer,self.encode,root,self.identity)
            index=retrieval.load_dense_index(root,self.identity)
            try:
                result=v3_pipeline.analyze_correspondence('query',index,self.documents,self.retriever,self.reranker,
                    literal_hits=[{'sourceRevisionId':'a'}]*30+[{'sourceRevisionId':'b'},{'sourceRevisionId':'c'}])
            finally:index['vectors']._mmap.close()
        b=next(row for row in result['candidateSources'] if row['sourceRevisionId']=='b')
        self.assertIn('literal',b['retrievalBranches'])

    def test_shared_template_regions_are_removed_before_source_features(self):
        text='shared campus bulletin message'
        self.documents=[{'sourceRevisionId':str(i),'sourceWorkId':str(i),'sourceKey':'BODY','text':text+' unique '+str(i)} for i in range(3)]
        self.reranker={**self.reranker,'scorePair':lambda pair:.9}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'index';retrieval.build_dense_index(self.documents,self.tokenizer,self.encode,root,self.identity)
            index=retrieval.load_dense_index(root,self.identity)
            try:result=v3_pipeline.analyze_correspondence(text,index,self.documents,self.retriever,self.reranker)
            finally:index['vectors']._mmap.close()
        self.assertEqual(result['aggregation']['allSourceQueryCoverage'],0.)
        self.assertTrue(all(row['features']['informativeQueryCoverage']==0. for row in result['aggregation']['sources']))

    def test_protocol_excluded_sources_never_enter_topk_or_reranking(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_pipeline(Path(folder)/'index',exclude_source_revision_ids={'a'})
        self.assertEqual(set(self.called),{'b','c'})
        self.assertEqual({r['sourceRevisionId'] for r in result['candidateSources']},{'b','c'})


if __name__=='__main__':unittest.main()
