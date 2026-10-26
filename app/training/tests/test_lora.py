import sys
import tempfile
import unittest
from pathlib import Path
import torch
from transformers import XLMRobertaConfig,XLMRobertaForSequenceClassification
from peft import PeftModel

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train_correspondence import attach_adapter, correspondence_loss, validate_rows


class LoraTests(unittest.TestCase):
    def test_bfloat16_frozen_backbone_keeps_trainable_adapter_and_classifier_in_float32(self):
        torch.manual_seed(34);torch.set_num_threads(2)
        config=XLMRobertaConfig(vocab_size=64,hidden_size=32,num_hidden_layers=1,num_attention_heads=4,intermediate_size=64,num_labels=1,max_position_embeddings=64)
        model=attach_adapter(XLMRobertaForSequenceClassification(config).to(dtype=torch.bfloat16))
        self.assertTrue(all(parameter.dtype==torch.float32 for parameter in model.parameters() if parameter.requires_grad))
        self.assertTrue(any(parameter.dtype==torch.bfloat16 and not parameter.requires_grad for parameter in model.parameters()))
        classifier=next(parameter for name,parameter in model.named_parameters() if parameter.requires_grad and name.endswith('out_proj.weight'))
        before=classifier.detach().clone();optimizer=torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad),lr=5e-5)
        # This CPU cannot run oneDNN BF16 backbone backward. Check the actual
        # trainable FP32 classifier here; the full FP32 adapter/reload test is
        # separate, and CUDA BF16 is verified in the formal training job.
        hidden=torch.randn(2,config.hidden_size,dtype=torch.float32)
        classifier_module=model.base_model.model.classifier.modules_to_save['default']
        loss=correspondence_loss(classifier_module.out_proj(hidden),torch.tensor([1.,0.]))
        loss.backward();optimizer.step()
        self.assertFalse(torch.equal(before,classifier))

    def test_formal_training_rejects_tiny_or_repeated_reverse_pairs(self):
        base={'taskType':'CONTENT_CORRESPONDENCE','labelOrigin':'controlled_construction','labelConfidence':'known','split':'train','sourceIds':['a'],'sourceOffsets':{'start':0,'end':6}}
        positive={**base,'query':'甲方事实','source':'保留甲方事实','target':1}
        negative={**base,'query':'乙方事实','source':'其他主要过程','target':0}
        with self.assertRaises(ValueError):validate_rows([positive,negative])
        validate_rows([positive,negative],minimum=2)
        reversed_pair={**positive,'query':positive['source'],'source':positive['query'],'sourceOffsets':{'start':0,'end':4}}
        with self.assertRaises(ValueError):validate_rows([positive,reversed_pair,negative],minimum=3)

    def test_query_value_and_classifier_update_and_adapter_reload_reproduces_scores(self):
        torch.manual_seed(71);torch.set_num_threads(2)
        config=XLMRobertaConfig(vocab_size=64,hidden_size=32,num_hidden_layers=1,num_attention_heads=4,intermediate_size=64,num_labels=1,max_position_embeddings=64)
        original=XLMRobertaForSequenceClassification(config)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original.save_pretrained(root/'base')
            model=attach_adapter(XLMRobertaForSequenceClassification.from_pretrained(root/'base'))
            parameters=[p for p in model.parameters() if p.requires_grad]
            self.assertGreater(len(parameters),0)
            before={name:p.detach().clone() for name,p in model.named_parameters() if p.requires_grad}
            optimizer=torch.optim.AdamW(parameters,lr=.01)
            inputs={'input_ids':torch.tensor([[0,8,12,2],[0,15,21,2]]),'attention_mask':torch.ones(2,4,dtype=torch.long)}
            logits=model(**inputs).logits
            correspondence_loss(logits,torch.tensor([1.,0.])).backward();optimizer.step()
            changed=[name for name,p in model.named_parameters() if name in before and not torch.equal(before[name],p)]
            self.assertTrue(any('lora_' in name for name in changed))
            self.assertTrue(any('classifier' in name for name in changed))
            self.assertTrue(all(not p.requires_grad for name,p in model.named_parameters() if 'lora_' not in name and 'modules_to_save' not in name))
            model.eval();expected=model(**inputs).logits.detach()
            model.save_pretrained(root/'adapter')
            restored=PeftModel.from_pretrained(XLMRobertaForSequenceClassification.from_pretrained(root/'base'),root/'adapter').eval()
            self.assertTrue(torch.allclose(expected,restored(**inputs).logits,atol=1e-6))

    def test_non_binary_target_cannot_enter_correspondence_bce(self):
        with self.assertRaises(ValueError):
            correspondence_loss(torch.zeros(1,1),torch.tensor([3.]))
