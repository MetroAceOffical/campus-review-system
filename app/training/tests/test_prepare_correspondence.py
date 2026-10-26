import sys
import unittest
from pathlib import Path
from collections import Counter
from tokenizers import Tokenizer, models, pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_correspondence as prepare


class PrepareCorrespondenceTests(unittest.TestCase):
    def setUp(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'))
        backend.pre_tokenizer=pre_tokenizers.Whitespace()
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        self.source=' '.join('sourceword'+str(i) for i in range(300))
        self.query=' '.join('changedword'+str(i) for i in range(300))
        self.original={'documentId':'a','text':'prefix '+self.source,'institutionName':'school',
                       'sourceClusterId':'cluster','eventClusterId':'event','split':'train'}
        self.record={'sourceIds':['a'],'sourceOffsets':{'start':7,'end':7+len(self.source)},
                     'source':self.source,'query':self.query,'checks':{'accepted':True}}

    def test_partial_queries_keep_the_late_body_and_full_original_source_ranges(self):
        stats=Counter()
        rows=list(prepare.generated_pairs({'a':self.original},[self.record],self.tokenizer,stats))
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[-1]['queryOffsets']['end'],len(self.query))
        for row in rows:
            span=row['queryOffsets'];self.assertEqual(row['query'],self.query[span['start']:span['end']])
            self.assertEqual(row['source'],self.original['text'][row['sourceOffsets']['start']:row['sourceOffsets']['end']])
            self.assertLessEqual(len(self.tokenizer(row['query'],row['source'])['input_ids']),512)
            self.assertEqual(row['target'],1)
            self.assertEqual(row['constructionParent']['query'],self.query)

    def test_generation_cannot_supply_heldout_wrong_ranges_or_fact_failed_pairs(self):
        cases=[({'a':{**self.original,'split':'dev'}},self.record),
               ({'a':self.original},{**self.record,'source':self.source+'wrong'}),
               ({'a':self.original},{**self.record,'query':self.query.replace('word299','word399')}),
               ({'a':self.original},{**self.record,'checks':{'accepted':False}})]
        for originals,record in cases:
            with self.subTest(record=record['checks']):
                with self.assertRaises(ValueError):list(prepare.generated_pairs(originals,[record],self.tokenizer,Counter()))

    def test_copy_and_reorder_controls_cannot_dominate_generated_training(self):
        self.assertEqual(prepare.control_budget(100),50)
        self.assertEqual(prepare.control_budget(1),0)

    def test_a_literal_slice_in_a_paraphrase_still_counts_as_a_copy_control(self):
        query=' '.join(('sourceword' if i<120 else 'changedword')+str(i) for i in range(300))
        rows=list(prepare.generated_pairs({'a':self.original},[{**self.record,'query':query}],self.tokenizer,Counter()))
        self.assertEqual(rows[0]['transformationKind'],'COPY_CONTROL')
        self.assertEqual(rows[-1]['transformationKind'],'PARAPHRASE')


if __name__=='__main__':unittest.main()
