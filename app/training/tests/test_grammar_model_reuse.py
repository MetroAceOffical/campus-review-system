import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_workbench import inspection

class GrammarReuseTests(unittest.TestCase):
    def test_one_model_is_reused_across_evaluation_batches(self):
        class Model:
            def eval(self):return self
        with patch('transformers.AutoTokenizer.from_pretrained',return_value=object()) as tokenizer,patch('transformers.AutoModelForCausalLM.from_pretrained',return_value=Model()) as model:
            inspection._grammar_pipeline.cache_clear()
            try:
                first=inspection._grammar_pipeline('cuda');second=inspection._grammar_pipeline('cuda')
                self.assertIs(first,second);self.assertEqual(model.call_count,1);self.assertEqual(tokenizer.call_count,1)
            finally:inspection._grammar_pipeline.cache_clear()

if __name__=='__main__':unittest.main()
