import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast,XLMRobertaConfig,XLMRobertaForSequenceClassification

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import task_model


class V3TaskModelTests(unittest.TestCase):
    def artifact(self,root):
        torch.manual_seed(31);torch.set_num_threads(2)
        config=XLMRobertaConfig(vocab_size=64,hidden_size=32,num_hidden_layers=1,num_attention_heads=4,intermediate_size=64,num_labels=1,max_position_embeddings=1024)
        model=XLMRobertaForSequenceClassification(config);model.save_pretrained(root/'model')
        backend=Tokenizer(models.WordLevel({'[UNK]':0,'[PAD]':1},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]',pad_token='[PAD]');tokenizer.save_pretrained(root/'model')
        files={path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in (root/'model').iterdir() if path.is_file()}
        manifest={'schemaVersion':'merged-correspondence-v1','taskType':'CONTENT_CORRESPONDENCE',
                  'scoreType':'CONTENT_CORRESPONDENCE_SCORE','inferenceRuntime':'TRANSFORMERS_NO_PEFT',
                  'files':files,'baseManifestSha256':'a'*64,'pairsSha256':'b'*64,'trainingRunSha256':'c'*64,
                  'comparison':{'mergeVerified':True,'reloadVerified':True,'precision':'FP32_CPU'},
                  'mergePrecision':'FP32','frozenBackbonePrecision':'BF16','productActivated':False,'qualityAccepted':False,
                  'scope':'Tiny random model for engineering tests; not a formal campus training artifact.'}
        manifest['exportId']='m3-merged-'+hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (root/'export-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        ready={**files,'export-manifest.json':hashlib.sha256((root/'export-manifest.json').read_bytes()).hexdigest()}
        (root/'READY').write_text(json.dumps(ready),encoding='utf-8')
        return model,tokenizer,manifest

    def test_plain_model_callback_matches_real_logits_and_alignment_execution(self):
        from campus_detection import alignment
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);model,tokenizer,manifest=self.artifact(root)
            loaded=task_model.load_correspondence_model(root,expected_export_id=manifest['exportId'],device='cpu',precision='FP32')
            tokens=tokenizer('query words','source words',return_tensors='pt',truncation=False)
            with torch.inference_mode():expected=torch.sigmoid(model.eval()(**tokens).logits.float()).item()
            pair={'queryText':'query words','sourceText':'source words'}
            self.assertAlmostEqual(loaded['scorePair'](pair),expected,places=6)
            query={'start':0,'end':11,'text':'query words'}
            hit={'start':0,'end':12,'text':'source words','sourceRevisionId':'a','sourceWorkId':'a','score':.2}
            result=alignment.evaluate_pairs(alignment.schedule_pairs([query],[[hit]],tokenizer),loaded['scorePair'],loaded['configuration']['configId'])
            self.assertEqual(result['evaluatedPairCount'],1)
            self.assertEqual(result['coverageStatus'],'COMPLETE')
            self.assertEqual(loaded['configuration']['exportId'],manifest['exportId'])
            with self.assertRaises(ValueError):loaded['scorePair']({'queryText':'word '*513,'sourceText':'source'})
            with self.assertRaises(ValueError):task_model.load_correspondence_model(root,expected_export_id=manifest['exportId'],device='cpu',precision='BF16')
            with self.assertRaises(ValueError):task_model.load_correspondence_model(root,expected_export_id='other-export',device='cpu',precision='FP32')

    def test_tampered_weights_missing_ready_and_manifest_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.artifact(root)
            task_model.verify_export(root)
            ready=(root/'READY').read_bytes();(root/'READY').unlink()
            with self.assertRaises(ValueError):task_model.verify_export(root)
            (root/'READY').write_bytes(ready)
            original=(root/'export-manifest.json').read_bytes()
            manifest=json.loads(original);manifest['exportId']='m3-merged-'+'0'*64
            (root/'export-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            hashes=json.loads(ready);hashes['export-manifest.json']=hashlib.sha256((root/'export-manifest.json').read_bytes()).hexdigest()
            (root/'READY').write_text(json.dumps(hashes),encoding='utf-8')
            with self.assertRaises(ValueError):task_model.verify_export(root)
            (root/'READY').write_bytes(ready);(root/'export-manifest.json').write_bytes(original)
            with (root/'model/model.safetensors').open('ab') as stream:stream.write(b'changed')
            with self.assertRaises(ValueError):task_model.verify_export(root)


if __name__=='__main__':unittest.main()
