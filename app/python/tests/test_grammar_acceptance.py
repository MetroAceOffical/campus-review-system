import unittest
from types import SimpleNamespace
from campus_workbench.grammar_acceptance import accept_edit


class GrammarAcceptanceTest(unittest.TestCase):
    def test_optional_rewriting_names_and_spacing_are_not_errors(self):
        lex=SimpleNamespace(counts={'新闻':100,'参与':100})
        for text,a,b,new in [('摄影图像',2,4,'作品'),('新闻中心',4,4,'部门'),('学　术',1,2,''),('天际新闻网',4,5,'網')]:
            self.assertFalse(accept_edit(text,a,b,new,lex))

    def test_attested_homophone_and_repetition_remain_available(self):
        lex=SimpleNamespace(counts={'参与':100,'参于':0})
        self.assertTrue(accept_edit('学生参于交流',3,4,'与',lex))
        self.assertTrue(accept_edit('开展开展工作',2,4,'',lex))
        self.assertTrue(accept_edit('开心的说',2,3,'地',lex))

    def test_normal_reduplicated_words_are_not_shortened(self):
        lex=SimpleNamespace(counts={})
        for text,at in [('人人参与',0),('好好学习',0),('看看材料',0),('研究研究方案',0)]:
            length=2 if text.startswith('研究') else 1
            self.assertFalse(accept_edit(text,at,at+length,'',lex))


if __name__=='__main__':unittest.main()
