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


if __name__=='__main__':unittest.main()
