"""Prevent navigation contamination, task confusion and split leakage."""
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from corpus import extract_article, cluster_splits, eligible_correspondence, near_source_edges
from prepare_training_data import parse_header
from collect_corpus import crawl_link, open_crawl_db


class CorpusTests(unittest.TestCase):
    def test_near_repost_merges_but_shared_footer_does_not_merge_unrelated_articles(self):
        body = ''.join(f'第{i}场校园活动介绍了独立的研究项目与志愿成果。' for i in range(30))
        footer = '校园新闻编辑部版权所有欢迎提供新闻线索。'
        documents = {'a':body+footer,'b':body.replace('研究项目','研究课题')+footer,
                     'c':'青年教师深入乡村开展法律援助与社会调研。'*30+footer}
        edges = {frozenset(pair) for pair in near_source_edges(documents)}
        self.assertIn(frozenset(('a','b')),edges)
        self.assertNotIn(frozenset(('a','c')),edges)
        self.assertNotIn(frozenset(('b','c')),edges)

    def test_a_progress_reader_does_not_block_crawl_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            writer = open_crawl_db(Path(folder)/'crawl.sqlite')
            reader = open_crawl_db(Path(folder)/'crawl.sqlite')
            try:
                reader.execute('BEGIN')
                reader.execute('SELECT * FROM pages').fetchall()
                writer.execute("INSERT INTO pages VALUES('https://school.edu.cn/a.htm','PENDING',0,NULL)")
                writer.commit()
                reader.rollback()
                self.assertEqual(reader.execute('SELECT count(*) FROM pages').fetchone()[0],1)
            finally:
                reader.close();writer.close()

    def test_pagination_is_kept_but_tracking_search_and_other_hosts_are_not(self):
        base = 'https://school.edu.cn/c/news.html'
        self.assertEqual(crawl_link(base,'?page=2'), 'https://school.edu.cn/c/news.html?page=2')
        self.assertIsNone(crawl_link(base,'?search=people'))
        self.assertIsNone(crawl_link(base,'https://other.edu.cn/news.html'))
        self.assertIsNone(crawl_link(base,'/a.jpg'))

    def test_public_pipe_header_is_parsed_and_wrong_schema_rejected(self):
        fields = 'label|doc_id1|doc_id2|title1|title2|content1|content2|keywords1|keywords2|main_keywords1|main_keywords2|ner_keywords1|ner_keywords2|ner1|ner2|category1|category2|time1|time2'
        self.assertEqual(parse_header(fields)[:3], ['label','doc_id1','doc_id2'])
        with self.assertRaises(ValueError):
            parse_header('label\ttext1\ttext2')

    def test_extracts_article_without_navigation_and_keeps_paragraphs(self):
        html = '''<html><title>示例 - 学校</title><nav>导航垃圾</nav><h1>校园活动</h1>
        <meta name="publishdate" content="2026-10-21"><div class="wp_articlecontent">
        <p>学生参与志愿服务。</p><p>活动取得了成果。<img src="/photo.jpg"></p></div><footer>版权垃圾</footer></html>'''
        result = extract_article(html, 'https://school.edu.cn/a/1.htm')
        self.assertEqual(result['text'], '学生参与志愿服务。\n活动取得了成果。')
        self.assertEqual(result['title'], '校园活动')
        self.assertEqual(result['publishedAt'], '2026-10-21')
        self.assertEqual(result['images'], ['https://school.edu.cn/photo.jpg'])

    def test_public_wechat_body_preserves_publisher_and_excludes_subscription_footer(self):
        html = '<h1 id="activity-name">学校活动</h1><span id="js_name">学校官方号</span><div id="js_content"><p>一项活动的公开正文。</p></div><footer>关注我们</footer>'
        result = extract_article(html,'https://mp.weixin.qq.com/s/example')
        self.assertIsNotNone(result)
        self.assertEqual(result['text'],'一项活动的公开正文。')
        self.assertEqual(result['publisher'],'学校官方号')

    def test_visible_publication_date_wins_over_url_and_sidebar_dates(self):
        html = '<h1>校园新闻</h1><div class="detail_box"><div class="time">2026年10月24日 新闻网 浏览次数15</div></div><div class="wp_articlecontent"><p>正文内容。</p></div><div class="news_time">2025.01.01</div>'
        row = extract_article(html,'https://school.edu.cn/2026/1023/article.htm')
        self.assertEqual(row['publishedAt'],'2026-10-24')

    def test_duplicate_text_and_transitive_event_links_cannot_cross_splits(self):
        docs = {'a':'同一个正文', 'b':'同一个正文', 'c':'另一篇', 'd':'其他事件'}
        result = cluster_splits(docs, [('b','c')], seed=20261026)
        self.assertEqual(result['a'], result['c'])
        self.assertEqual(result, cluster_splits(dict(reversed(list(docs.items()))), [('c','b')], seed=20261026))

    def test_correspondence_head_rejects_auxiliary_and_unknown_labels(self):
        self.assertFalse(eligible_correspondence({'taskType':'RETRIEVAL_RELEVANCE','labelOrigin':'published_event_label','labelConfidence':'known'}))
        self.assertFalse(eligible_correspondence({'taskType':'CONTENT_CORRESPONDENCE','labelOrigin':'unknown','labelConfidence':'unknown'}))
        self.assertTrue(eligible_correspondence({'taskType':'CONTENT_CORRESPONDENCE','labelOrigin':'controlled_construction','labelConfidence':'known'}))


if __name__ == '__main__':
    unittest.main()
