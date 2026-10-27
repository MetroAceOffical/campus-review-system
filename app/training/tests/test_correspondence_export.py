import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast,XLMRobertaConfig,XLMRobertaForSequenceClassification,AutoModelForSequenceClassification

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train_correspondence import attach_adapter,correspondence_loss
import export_correspondence as export


class CorrespondenceExportTests(unittest.TestCase):
    def test_export_preserves_the_frozen_training_backbone_bfloat16_values(self):
        torch.manual_seed(33)
        config=XLMRobertaConfig(vocab_size=64,hidden_size=32,num_hidden_layers=1,num_attention_heads=4,intermediate_size=64,num_labels=1,max_position_embeddings=64)
        model=XLMRobertaForSequenceClassification(config)
        expected=model.roberta.embeddings.word_embeddings.weight.detach().to(torch.bfloat16).float()
        self.assertFalse(torch.equal(expected,model.roberta.embeddings.word_embeddings.weight.detach()))
        with tempfile.TemporaryDirectory() as folder:
            model.save_pretrained(folder)
            restored=export.load_export_base(Path(folder),'BF16')
            self.assertEqual(restored.roberta.embeddings.word_embeddings.weight.dtype,torch.float32)
            self.assertTrue(torch.equal(expected,restored.roberta.embeddings.word_embeddings.weight.detach()))
            with self.assertRaises(ValueError):export.load_export_base(Path(folder),'unknown')

    def test_trained_tiny_adapter_and_head_merge_to_a_plain_reloadable_model(self):
        torch.manual_seed(90);torch.set_num_threads(2)
        config=XLMRobertaConfig(vocab_size=64,hidden_size=32,num_hidden_layers=1,num_attention_heads=4,intermediate_size=64,num_labels=1,max_position_embeddings=64)
        model=attach_adapter(XLMRobertaForSequenceClassification(config))
        inputs={'input_ids':torch.tensor([[0,8,12,2],[0,15,21,2]]),'attention_mask':torch.ones(2,4,dtype=torch.long)}
        optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=.01)
        correspondence_loss(model(**inputs).logits,torch.tensor([1.,0.])).backward();optimizer.step();model.eval()
        expected=model(**inputs).logits.detach()
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'model'
            result=export.merge_for_inference(model,tokenizer,inputs,output)
            self.assertTrue(result['mergeVerified'])
            self.assertTrue(result['reloadVerified'])
            self.assertEqual(result['precision'],'FP32_CPU')
            reloaded=AutoModelForSequenceClassification.from_pretrained(output,local_files_only=True)
            self.assertFalse(any('lora_' in name or 'modules_to_save' in name for name,_ in reloaded.named_parameters()))
            self.assertTrue(torch.allclose(expected,reloaded(**inputs).logits,atol=1e-5,rtol=1e-5))
            self.assertTrue((output/'tokenizer.json').exists())
            with self.assertRaises(ValueError):export.merge_for_inference(model,tokenizer,inputs,output)
            # The real export writer must produce exactly the bundle consumed by
            # the production loader; independent hand-written fixtures can miss
            # a producer/consumer schema mismatch.
            manifest=export.freeze_export(Path(folder),{'scope':'Tiny CPU engineering fixture; no formal campus training.'},result)
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
            from campus_detection import task_model
            self.assertEqual(task_model.verify_export(Path(folder))['exportId'],manifest['exportId'])
            loaded=task_model.load_correspondence_model(Path(folder),expected_export_id=manifest['exportId'],device='cpu',precision='FP32')
            score=loaded['scorePair']({'queryText':'query words','sourceText':'source words'})
            self.assertGreaterEqual(score,0.);self.assertLessEqual(score,1.)
            with self.assertRaises(ValueError):export.freeze_export(Path(folder),{},result)

    def test_completed_run_requires_verified_final_checkpoint_and_formal_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);checkpoint=root/'checkpoint-000004';checkpoint.mkdir()
            (checkpoint/'state.pt').write_bytes(b'checkpoint test fixture')
            digest=hashlib.sha256((checkpoint/'state.pt').read_bytes()).hexdigest()
            (checkpoint/'READY').write_text(json.dumps({'state.pt':digest}))
            config={'taskType':'CONTENT_CORRESPONDENCE','pairCount':20000,'epochs':2,'baseManifestSha256':'a'*64,'pairsSha256':'b'*64}
            status={'state':'CORRESPONDENCE_TRAINING_COMPLETE','checkpoint':checkpoint.name,'reloadVerified':True,'epochs':2}
            (root/'run.json').write_text(json.dumps(config));(root/'status.json').write_text(json.dumps(status))
            found=export.completed_run(root)
            self.assertEqual(found['checkpoint'],checkpoint)
            for changed in [{**status,'reloadVerified':False},{**status,'state':'CORRESPONDENCE_TRAINING'},
                            {**status,'checkpoint':'../outside'}]:
                (root/'status.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError):export.completed_run(root)
            (root/'status.json').write_text(json.dumps(status))
            (root/'run.json').write_text(json.dumps({**config,'pairCount':19999}))
            with self.assertRaises(ValueError):export.completed_run(root)
            (root/'run.json').write_text(json.dumps(config))
            (checkpoint/'state.pt').write_bytes(b'tampered')
            with self.assertRaises(ValueError):export.completed_run(root)


if __name__=='__main__':unittest.main()
