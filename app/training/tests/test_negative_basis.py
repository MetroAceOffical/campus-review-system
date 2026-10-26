import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from negative_basis import assess_difference
from corpus import eligible_correspondence


class NegativeBasisTests(unittest.TestCase):
    def row(self,text,key,date):
        return {'text':text,'sourceId':key,'sourceClusterId':key,'eventClusterId':key,'publishedAt':date,'start':0,'end':len(text)}

    def test_different_named_processes_have_explicit_basis_but_unknown_labels_stay_rejected(self):
        a=self.row('研究团队围绕“水体微生物检测”开展实验，研究论文总结了测量方法及样本分析结果。','a','2026-01-01')
        b=self.row('“校园青年影像展”正式开幕，艺术展览集中展示学生创作，展演交流了摄影作品的创作过程。','b','2026-06-01')
        basis=assess_difference(a,b)
        self.assertTrue(basis['supported'])
        self.assertTrue(all(item['text']==(a if item['side']=='query_source' else b)['text'][item['start']:item['end']] for item in basis['factSpans']))
        row={'taskType':'CONTENT_CORRESPONDENCE','target':0,'labelOrigin':'rule_inferred_noncorrespondence','labelConfidence':'supported_rule','negativeBasis':basis}
        self.assertTrue(eligible_correspondence(row))
        self.assertFalse(eligible_correspondence({**row,'negativeBasis':{}}))

    def test_merely_changing_dates_does_not_make_a_reuse_negative(self):
        text='学校举办教育交流会议，参会人员共同讨论课程改革，组织团队展示教学成果，并围绕实践教学分享经验，会议最后总结合作安排。'
        a=self.row('2026年1月1日，'+text,'a','2026-01-01')
        b=self.row('2026年6月1日，'+text,'b','2026-06-01')
        self.assertFalse(assess_difference(a,b)['supported'])

    def test_same_research_category_can_have_different_explicit_process_and_subject(self):
        a=self.row('“古籍纸张耐久性”研究团队开展实验，提出了利用水分迁移监测古籍纤维老化状态的测量方法，论文记录了研究结果。','a','2026-01-01')
        b=self.row('“卫星轨道重建”研究团队完成研究，构建了面向深空探测器飞行轨迹规划的多目标优化模型，论文报告了研究数据。','b','2026-06-01')
        self.assertTrue(assess_difference(a,b)['supported'])

    def test_unquoted_reports_can_use_distinct_substantive_title_and_process_facts(self):
        a=self.row('研究团队完成了海底声波传播实验，研究论文提出了利用水下阵列观测海洋环境变化的检测方法。','a',None)
        b=self.row('志愿服务队走进养老社区，志愿者组织义诊并开展助老帮扶，为居民提供健康咨询和日常生活协助。','b',None)
        a['title']='海洋声学观测研究提出水下阵列新方法'
        b['title']='青年志愿者为养老社区居民提供义诊帮扶'
        self.assertTrue(assess_difference(a,b)['supported'])
