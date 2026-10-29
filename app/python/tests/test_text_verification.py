import unittest
from campus_workbench.text_verification import quoted_support,indexed_support,indexed_units


class QuotedSupportTest(unittest.TestCase):
    def test_requires_exact_unique_nonoverlapping_quotes(self):
        q='师生讨论了新闻采访中的人物选择和问题设计。学生随后分组完成现场采访，整理录音并交叉核对报道事实。'
        s='教师带领学生分析如何选择采访对象和设计问题。随后各组实地采访，整理录音资料并核查新闻中的事实。'
        pairs=[dict(query=q[:22],source=s[:23]),dict(query=q[22:],source=s[23:])]
        good=quoted_support(q,s,dict(reuse=True,pairs=pairs))
        self.assertEqual(2,len(good['pairs']))
        self.assertEqual(len(q),good['matchedQueryCharacters'])
        self.assertFalse(good['suspectedReuse']) # below the unchanged64-character support budget
        with self.assertRaises(ValueError):quoted_support(q,s,dict(reuse=True,pairs=[dict(query='模型臆造的查询片段不能作为任何证据',source=s[:23])]))
        with self.assertRaises(ValueError):quoted_support(q,s,dict(reuse=True,pairs=[pairs[0],pairs[0]]))
        with self.assertRaises(ValueError):quoted_support(q+q,s,dict(reuse=True,pairs=[pairs[0]]))
        with self.assertRaises(ValueError):quoted_support('甲'*13,s,dict(reuse=True,pairs=[dict(query='甲'*12,source=s[:23])]))
        self.assertFalse(quoted_support(q,s,dict(reuse=False,pairs=pairs))['suspectedReuse'])
        q_more='小组还讨论了如何保护受访者隐私并检查引用材料的来源。'
        s_more='各组随后交流了采访对象隐私保护和来源核对的工作方法。'
        self.assertTrue(quoted_support(q+q_more,s+s_more,dict(reuse=True,pairs=pairs+[dict(query=q_more,source=s_more)]))['suspectedReuse'])

    def test_indexed_support_resolves_real_spans_without_model_copied_quotes(self):
        text='师生讨论新闻采访中的人物选择、问题设计及核实信息的方法。学生随后分组完成现场采访，整理录音并交叉核对报道事实。小组还讨论了如何保护受访者隐私并检查引用材料的来源。'
        units=indexed_units(text)
        value=dict(reuse=True,pairs=[dict(queryId=i,sourceId=i) for i in range(len(units))])
        self.assertTrue(indexed_support(units,units,value)['suspectedReuse'])
        with self.assertRaises(ValueError):indexed_support(units,units,dict(reuse=True,pairs=[dict(queryId=999,sourceId=0)]))
        with self.assertRaises(ValueError):indexed_support(units,units,dict(reuse=True,pairs=[dict(queryId=0,sourceId=0)]*2))


if __name__=='__main__':unittest.main()
