import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer,models,pre_tokenizers,processors
from transformers import BertConfig,BertModel,PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import retrieval_model


class RetrievalModelTests(unittest.TestCase):
    def artifact(self,root):
        torch.manual_seed(19);torch.set_num_threads(2)
        model=BertModel(BertConfig(vocab_size=64,hidden_size=768,num_hidden_layers=1,num_attention_heads=12,intermediate_size=64,max_position_embeddings=1024))
        model.save_pretrained(root)
        vocab={'[UNK]':0,'[PAD]':1,'[CLS]':2,'[SEP]':3,'alpha':4,'beta':5}
        backend=Tokenizer(models.WordLevel(vocab,unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        backend.post_processor=processors.TemplateProcessing(single='[CLS] $A [SEP]',special_tokens=[('[CLS]',2),('[SEP]',3)])
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]',pad_token='[PAD]',cls_token='[CLS]',sep_token='[SEP]');tokenizer.save_pretrained(root)
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
        return model,tokenizer,hashes

    def test_fixed_plain_encoder_matches_normalized_cls_and_refuses_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);model,tokenizer,hashes=self.artifact(root)
            loaded=retrieval_model.load_retrieval_model(root,expected_hashes=hashes,device='cpu',precision='FP32')
            texts=['alpha beta','beta alpha']
            with torch.inference_mode():
                expected=torch.nn.functional.normalize(model.eval()(**tokenizer(texts,padding=True,return_tensors='pt')).last_hidden_state[:,0].float(),dim=-1).numpy()
            actual=loaded['encode'](texts)
            np.testing.assert_allclose(actual,expected,atol=1e-6)
            self.assertEqual(actual.shape,(2,768))
            np.testing.assert_allclose(np.linalg.norm(actual,axis=1),1.,atol=1e-6)
            self.assertEqual(loaded['identity']['pooling'],'CLS')
            self.assertEqual(loaded['identity']['normalization'],'L2')
            self.assertEqual(loaded['encode']([]).shape,(0,768))
            with self.assertRaises(ValueError):loaded['encode'](['alpha '*513])
            with self.assertRaises(ValueError):retrieval_model.load_retrieval_model(root,expected_hashes=hashes,device='cpu',precision='BF16')

    def test_tokenizer_settings_and_weights_are_both_bound_to_expected_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);_,_,hashes=self.artifact(root)
            incomplete={key:value for key,value in hashes.items() if key!='special_tokens_map.json'}
            with self.assertRaises(ValueError):retrieval_model.load_retrieval_model(root,expected_hashes=incomplete,device='cpu',precision='FP32')
            with (root/'tokenizer_config.json').open('a') as stream:stream.write(' ')
            with self.assertRaises(ValueError):retrieval_model.load_retrieval_model(root,expected_hashes=hashes,device='cpu',precision='FP32')


if __name__=='__main__':unittest.main()
