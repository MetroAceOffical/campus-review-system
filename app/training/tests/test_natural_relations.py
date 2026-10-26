import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_natural_relations as natural


class NaturalRelationsTests(unittest.TestCase):
    def test_webplus_and_vsb_column_aliases_are_the_same_publication_identity(self):
        self.assertEqual(natural.publication_identity('https://news.school.edu.cn/_t8/2026/1026/c12a345/page.htm'),natural.publication_identity('http://news.school.edu.cn/2026/1026/c19a345/page.htm'))
        self.assertEqual(natural.publication_identity('https://news.school.edu.cn/info/1001/123.htm'),natural.publication_identity('https://news.school.edu.cn/info/1002/123.htm'))
        self.assertNotEqual(natural.publication_identity('https://news.school.edu.cn/info/1001/123.htm'),natural.publication_identity('https://news.school.edu.cn/info/1001/124.htm'))

    def test_distinct_records_need_verified_exact_normalized_bodies_without_rewriting_originals(self):
        source={'url':'https://news.school.edu.cn/info/1001/123.htm','text':'学校组织２００名学生\n参加服务。','pageSha256':'a'*64}
        alternate={'url':'https://news.school.edu.cn/info/1001/124.htm','text':'学校组织200名学生参加服务。','pageSha256':'b'*64}
        result=natural.content_relation(source,alternate)
        self.assertTrue(result['accepted'])
        self.assertFalse(result['exactCodepointEquality'])
        self.assertEqual(source['text'],'学校组织２００名学生\n参加服务。')
        self.assertFalse(natural.content_relation(source,{**alternate,'url':source['url']})['accepted'])
        self.assertFalse(natural.content_relation(source,{**alternate,'text':'另一场不同活动。'})['accepted'])
        self.assertFalse(natural.content_relation(source,{**alternate,'pageSha256':source['pageSha256']})['accepted'])


if __name__=='__main__':unittest.main()
