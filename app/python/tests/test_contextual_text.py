import unittest
from unittest.mock import patch
from campus_detection.contextual_text import context_units,select_versions


class Tokenizer:
    def __call__(self,text,**kwargs):
        return {'input_ids':list(range(len(text))),'offset_mapping':[(i,i+1) for i in range(len(text))]}


class ContextualTextTest(unittest.TestCase):
    def test_context_offsets_and_version_budget_preserve_distinct_sources(self):
        text='新闻中心组织师生开展专题讨论，重点交流采访准备和资料核对的方法。随后各小组完成现场采访并整理录音材料。'
        units=context_units(text,Tokenizer(),60,48)
        self.assertTrue(all(text[u['start']:u['end']]==u['text'] and len(u['text'])<=60 for u in units))
        self.assertTrue(any(u['end']==len(text) for u in units))
        self.assertEqual(len(units),len({(u['start'],u['end']) for u in units}))
        repeated=('甲'*39+'。'+'乙'*39+'。')*2
        self.assertEqual([(0,40),(40,80),(80,120),(120,160)],[(u['start'],u['end']) for u in context_units(repeated,Tokenizer(),60,48)])
        records=[dict(key=str(i),group=g) for i,g in enumerate(['a','a','a','b','c','d'])]
        self.assertEqual(['0','1','3','4'],[r['key'] for r in select_versions(records,3,2)])

    def test_opt_in_keeps_old_model_id_and_feature_space_available(self):
        from campus_detection.models import ROOT,configurations
        from campus_detection.http_service import Runtime
        base,image=configurations();loaded=dict(textConfig=base,textConfigs={base['configId']:base},imageConfig=image)
        with patch('campus_detection.http_service.load_models',return_value=loaded):
            runtime=Runtime(ROOT/'runtime/indexes','test-only',contextual=True);runtime.load()
        self.assertIsNone(runtime.load_error)
        self.assertEqual(base,runtime.models['textConfigs'][base['configId']])
        self.assertEqual(base['featureSpaceId'],runtime.models['textConfig']['featureSpaceId'])
        self.assertNotEqual(base['configId'],runtime.models['textConfig']['configId'])


if __name__=='__main__':unittest.main()
