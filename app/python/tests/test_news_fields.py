import unittest
from campus_workbench.news_fields import fields


class NewsFieldsTest(unittest.TestCase):
    def test_ocr_spacing_labeled_dot_dates_and_explicit_host_aliases(self):
        self.assertEqual({'2026/10/29'},fields('日期：2026年 10 月 29 日')['日期'])
        self.assertEqual({'2026/10/29'},fields('活动时间：2026.10.29')['日期'])
        self.assertEqual({'新闻中心'},fields('主办方：新闻中心')['主办单位'])
        self.assertEqual({'新闻中心'},fields('主办：新闻中心')['主办单位'])

    def test_invalid_dates_and_unlabeled_versions_do_not_become_facts(self):
        self.assertEqual(set(),fields('日期：2025年2月29日')['日期'])
        self.assertEqual(set(),fields('版本：2026.10.29')['日期'])
        self.assertEqual(set(),fields('新闻中心负责承办活动')['主办单位'])
        self.assertEqual({'2024/2/29'},fields('日期：２０２４年２月２９日')['日期'])


if __name__=='__main__':unittest.main()
