import sys
import unittest
import numpy as np
from pathlib import Path
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mine_correspondence_candidates import aligned_windows,rank_outside_event


class AlignmentWindowTests(unittest.TestCase):
    def test_large_same_event_family_does_not_consume_other_source_ranking_budget(self):
        scores=np.array([1.]*150+[.4,.2],dtype=np.float32)
        self.assertEqual(rank_outside_event(scores,np.arange(150),maximum=2),[150,151])
        self.assertEqual(float(scores[0]),1.)

    def test_windows_keep_original_offsets_and_cover_the_late_body(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        text='甲🙂 early body sentence words followed by the last important fact'
        rows=aligned_windows(text,tokenizer,window=4,overlap=1)
        self.assertEqual(rows[0]['start'],0)
        self.assertEqual(rows[-1]['end'],len(text))
        self.assertTrue(all(row['text']==text[row['start']:row['end']] for row in rows))
        self.assertTrue(all(row['tokens']<=4 for row in rows))
        self.assertTrue(all(a['end']>=b['start'] for a,b in zip(rows,rows[1:])))
