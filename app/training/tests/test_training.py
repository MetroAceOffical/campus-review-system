import sys
import unittest
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast
from pathlib import Path
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train_text_models import retrieval_loss, explicit_groups


class TrainingTests(unittest.TestCase):
    def test_campus_tokenization_keeps_the_full_source_and_rejects_over_budget(self):
        import train_text_models as training
        backend=Tokenizer(models.WordLevel({'[UNK]':0,'[PAD]':1},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]',pad_token='[PAD]')
        text=' '.join(['word']*300)
        self.assertEqual(training.tokenize_retrieval(tokenizer,[text],512,strict=True)['input_ids'].shape[1],300)
        self.assertEqual(training.tokenize_retrieval(tokenizer,[text],256,strict=False)['input_ids'].shape[1],256)
        with self.assertRaises(ValueError):training.tokenize_retrieval(tokenizer,[' '.join(['word']*513)],512,strict=True)

    def test_default_auxiliary_configuration_is_unchanged_and_campus_labels_are_explicit(self):
        import train_text_models as training
        old={'taskType':'RETRIEVAL_RELEVANCE','maxTokensPerSide':256,'microbatch':2,'stage':'public_event_story_auxiliary_only'}
        self.assertEqual(training.configure_stage(old,{},campus=False),old)
        manifest={'taskType':'CONTENT_CORRESPONDENCE','formalScaleAndBalanceReady':True,'trainGroups':1000}
        configured=training.configure_stage(old,manifest,campus=True,max_tokens=512,microbatch=1)
        self.assertEqual(configured['taskType'],'CONTENT_CORRESPONDENCE')
        self.assertTrue(configured['strictTokenBudget'])
        self.assertEqual(configured['microbatch'],1)
        with self.assertRaises(ValueError):training.configure_stage(old,{**manifest,'taskType':'RETRIEVAL_RELEVANCE'},campus=True,max_tokens=512,microbatch=1)

    def test_directed_retrieval_never_turns_a_passage_into_the_query(self):
        pairs = [('q','p',1)]+[('q',key,0) for key in ['a','b','c','d']]+[(key,'p',0) for key in ['x1','x2','x3','x4']]
        groups = explicit_groups(pairs,symmetric=False)
        self.assertEqual(groups,[{'queryId':'q','positiveId':'p','negativeIds':['a','b','c','d']}])

    def test_each_of_four_explicit_negatives_receives_gradient(self):
        query = torch.tensor([[1.,.4]],requires_grad=True)
        passages = torch.tensor([[[.8,.2],[.5,.1],[.7,.6],[.2,.9],[.3,.1]]],requires_grad=True)
        loss = retrieval_loss(query,passages)
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        for index in range(1,5):
            self.assertGreater(passages.grad[0,index].abs().sum().item(),0)

    def test_groups_never_invent_or_duplicate_missing_explicit_negatives(self):
        pairs = [('q','p',1),('q','a',0),('q','b',0),('q','c',0)]
        self.assertEqual(explicit_groups(pairs),[])
        groups = explicit_groups(pairs+[('q','d',0),('q','d',0)])
        self.assertEqual(len(groups),1)
        self.assertEqual(set(groups[0]['negativeIds']),{'a','b','c','d'})


if __name__ == '__main__':
    unittest.main()
