import sys
import unittest
from pathlib import Path
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import alignment


class V3AlignmentTests(unittest.TestCase):
    def setUp(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')

    def test_oversize_pairs_split_with_exact_offsets_and_no_late_body_truncation(self):
        query='first 🙂 words then the important late query fact'
        source='reference words before another important final source fact'
        pairs=alignment.split_pair({'start':17,'end':17+len(query),'text':query},{'start':100,'end':100+len(source),'text':source},self.tokenizer,max_joint=8)
        self.assertGreater(len(pairs),1)
        self.assertEqual(max(row['queryEnd'] for row in pairs),17+len(query))
        self.assertEqual(max(row['sourceEnd'] for row in pairs),100+len(source))
        for row in pairs:
            self.assertEqual(row['queryText'],query[row['queryStart']-17:row['queryEnd']-17])
            self.assertEqual(row['sourceText'],source[row['sourceStart']-100:row['sourceEnd']-100])
            self.assertLessEqual(len(self.tokenizer(row['queryText'],row['sourceText'])['input_ids']),8)

    def test_budget_spreads_first_pairs_across_the_whole_query_and_marks_deferrals(self):
        blocks=[{'start':i*10,'end':i*10+7,'text':'query x'} for i in range(5)]
        hits=[[{'start':0,'end':8,'text':'source x','sourceRevisionId':str(j),'sourceWorkId':str(j),'sourceKey':'BODY','score':-.2} for j in range(2)] for _ in blocks]
        result=alignment.schedule_pairs(blocks,hits,self.tokenizer,max_pairs=3)
        self.assertEqual([row['queryStart'] for row in result['pairs']],[0,20,40])
        self.assertEqual(result['coveragePlan'],'PARTIAL')
        self.assertEqual(result['deferredCandidatePairs'],7)
        self.assertFalse(result['neuralInferencePerformed'])

    def test_repeated_blocks_from_one_source_cannot_consume_the_three_source_slots(self):
        query={'start':0,'end':7,'text':'query x'}
        hits=[{'start':0,'end':8,'text':'source x','sourceRevisionId':key,'sourceWorkId':key,'sourceKey':'BODY','score':.9-i*.01} for i,key in enumerate(['a','a','a','b','c'])]
        result=alignment.schedule_pairs([query],[hits],self.tokenizer,max_pairs=10)
        self.assertEqual({row['sourceRevisionId'] for row in result['pairs']},{'a','b','c'})

    def test_neighbor_context_uses_the_same_revision_field_and_original_ranges(self):
        text='before one middle two after three'
        blocks=[{'start':0,'end':10,'text':text[:10]},
                {'start':11,'end':21,'text':text[11:21]},
                {'start':22,'end':len(text),'text':text[22:]}]
        hit={**blocks[1],'sourceRevisionId':'a','sourceWorkId':'work-a','sourceKey':'CAPTION:node:one','score':.8}
        context={('a','CAPTION:node:one'):{'text':text,'blocks':blocks}}
        query={'start':0,'end':7,'text':'query x'}
        result=alignment.schedule_pairs([query],[[hit]],self.tokenizer,source_contexts=context)
        pair=result['pairs'][0]
        self.assertEqual(pair['sourceText'],text)
        self.assertEqual((pair['sourceStart'],pair['sourceEnd']),(0,len(text)))
        self.assertEqual(pair['retrievedSourceRange'],{'start':11,'end':21})
        self.assertEqual(pair['sourceKey'],'CAPTION:node:one')
        with self.assertRaises(ValueError):
            alignment.schedule_pairs([query],[[hit]],self.tokenizer,source_contexts={('a','BODY'):context[('a','CAPTION:node:one')]})
        changed={('a','CAPTION:node:one'):{'text':'WRONG '+text,'blocks':blocks}}
        with self.assertRaises(ValueError):alignment.schedule_pairs([query],[[hit]],self.tokenizer,source_contexts=changed)

    def test_pair_runner_counts_only_successful_calls_and_does_not_hide_failures(self):
        blocks=[{'start':i*10,'end':i*10+7,'text':'query x'} for i in range(3)]
        hits=[[{'start':0,'end':8,'text':'source x','sourceRevisionId':'a','sourceWorkId':'w','sourceKey':'BODY','score':.5}] for _ in blocks]
        plan=alignment.schedule_pairs(blocks,hits,self.tokenizer)
        called=[]
        def score(pair):
            called.append(pair['queryStart'])
            if pair['queryStart']==10:raise RuntimeError('Inference failed')
            return .7
        result=alignment.evaluate_pairs(plan,score,model_config_id='trained-test-fixture')
        self.assertEqual(called,[0,10,20])
        self.assertEqual(result['evaluatedPairCount'],2)
        self.assertEqual(result['failedPairCount'],1)
        self.assertEqual(result['coverageStatus'],'PARTIAL')
        self.assertEqual(result['checkedRegions'],[{'start':0,'end':7},{'start':20,'end':27}])
        self.assertEqual(result['pairs'][0]['scoreType'],'CONTENT_CORRESPONDENCE_SCORE')
        self.assertEqual(result['pairs'][0]['modelConfigId'],'trained-test-fixture')
        self.assertEqual(result['failures'][0]['errorType'],'RuntimeError')
        self.assertFalse(result['noReuseClaim'])
        from campus_detection import aggregation
        summary=aggregation.summarize_sources(result['pairs'],27,{'a:BODY':8},
                                              {'modelConfigId':'trained-test-fixture','pairScoreThreshold':.5})
        self.assertAlmostEqual(summary['allSourceQueryCoverage'],14/27)

    def test_invalid_scores_and_budget_deferrals_cannot_become_full_coverage(self):
        query={'start':0,'end':7,'text':'query x'}
        hits=[{'start':0,'end':8,'text':'source x','sourceRevisionId':key,'sourceWorkId':key,'score':.8} for key in ['a','b']]
        plan=alignment.schedule_pairs([query],[hits],self.tokenizer,max_pairs=1)
        partial=alignment.evaluate_pairs(plan,lambda pair:0.,model_config_id='fixture')
        self.assertEqual(partial['coverageStatus'],'PARTIAL')
        self.assertEqual(partial['deferredCandidatePairs'],1)
        self.assertFalse(partial['noReuseClaim'])
        for score in [float('nan'),float('inf'),-1.,1.1,True]:
            result=alignment.evaluate_pairs(plan,lambda pair:score,model_config_id='fixture')
            self.assertEqual(result['coverageStatus'],'FAILED')
            self.assertEqual(result['evaluatedPairCount'],0)
            self.assertEqual(result['checkedRegions'],[])
        empty=alignment.schedule_pairs([query],[[]],self.tokenizer)
        result=alignment.evaluate_pairs(empty,lambda pair:1.,model_config_id='fixture')
        self.assertEqual(result['coverageStatus'],'PARTIAL')
        self.assertEqual(result['emptyCandidateRegions'],[{'start':0,'end':7}])
        no_text=alignment.evaluate_pairs(alignment.schedule_pairs([],[],self.tokenizer),lambda pair:1.,model_config_id='fixture')
        self.assertEqual(no_text['coverageStatus'],'PARTIAL')
        with self.assertRaises(ValueError):alignment.evaluate_pairs(plan,lambda pair:.5,model_config_id='')


if __name__=='__main__':unittest.main()
