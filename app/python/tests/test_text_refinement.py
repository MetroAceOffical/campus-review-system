import unittest
from unittest.mock import patch
from campus_detection.text_refinement import summarize, chrome_ranges, literal_pieces, reference_chrome, refine


def window(q, s, n, m, score, lexical):
    return dict(queryStart=q,queryEnd=q+n,sourceStart=s,sourceEnd=s+m,
                queryText='甲'*n,sourceText='乙'*m,score=score,tfidfScore=lexical)


class TextRefinementTest(unittest.TestCase):
    def test_opt_in_retains_context_and_legacy_configs(self):
        from campus_detection.models import ROOT,configurations
        from campus_detection.contextual_text import configuration
        from campus_detection.http_service import Runtime
        base,image=configurations();context=configuration(base)
        with patch('campus_detection.http_service.load_models',return_value=dict(textConfig=base,textConfigs={base['configId']:base},imageConfig=image)):
            runtime=Runtime(ROOT/'runtime/indexes','test-only',refined=True);runtime.load()
        self.assertIsNone(runtime.load_error)
        self.assertEqual(context,runtime.models['textConfigs'][context['configId']])
        self.assertEqual(base,runtime.models['textConfigs'][base['configId']])
        self.assertTrue(runtime.models['textConfig']['refinementPolicy'])
        self.assertEqual(base['featureSpaceId'],runtime.models['textConfig']['featureSpaceId'])

    def test_independent_anchor_can_corroborate_reworded_context(self):
        rows=[window(110,139,52,39,.553,.408),window(0,0,30,40,.628,.170)]
        summary,support=summarize(rows)
        self.assertTrue(summary['suspectedReuse'])
        self.assertEqual(82,summary['matchedQueryCharacters'])
        self.assertEqual(2,len(support))
        self.assertEqual(.25,summary['lexicalFloor'])

    def test_generic_short_anchor_cannot_promote_shared_topic(self):
        rows=[window(77,519,16,18,.773,.752),window(475,2397,46,26,.637,.301),window(205,168,30,13,.648,.177)]
        summary,_=summarize(rows)
        self.assertFalse(summary['suspectedReuse'])
        summary,_=summarize([window(0,0,60,12,.8,.5),window(70,20,30,30,.7,.2)])
        self.assertFalse(summary['suspectedReuse'])

    def test_navigation_requires_metadata_and_does_not_hide_real_text(self):
        body='😀正文事实'+('采访材料需要核对。'*5)
        text=body+'\n本文分类：新闻\n本文链接：https://example.org/a/1\n上一篇 >其他新闻\n收藏 分享\n推荐文章'
        ranges=chrome_ranges(text,{'推荐文章'})
        self.assertEqual([(len(body)+1,len(text))],ranges)
        match=dict(queryStart=0,queryEnd=len(text),sourceStart=5,sourceEnd=5+len(text),queryText=text,sourceText=text)
        pieces=literal_pieces([match],ranges,[],32)
        self.assertEqual(body+'\n',pieces[0]['queryText'])
        self.assertEqual(5,pieces[0]['sourceStart'])
        self.assertEqual([],chrome_ranges('新闻讨论“上一篇”文章的内容，保留真实叙事。'))
        self.assertEqual([],chrome_ranges('本文链接：https://example.org/a/1\n仍有正常正文，没有导航按钮。'))
        continued=text+'\n这是尾部标记之后继续编写的实际正文，不能被导航规则吞掉。'
        self.assertLess(chrome_ranges(continued,{'推荐文章'})[-1][1],len(continued))
        prefix='本文分类：记者介绍分类方法\n这是正文内容。\n'
        self.assertEqual(len(prefix)+len(body)+1,chrome_ranges(prefix+text,{'推荐文章'})[0][0])
        documents={str(i):dict(text=text.replace('/a/1',f'/a/{i}')) for i in range(3)}
        self.assertEqual(len(text),reference_chrome(documents)['0'][0][1])
        documents['2']=documents['1']
        self.assertLess(reference_chrome(documents)['0'][0][1],len(text))
        multiline=text.replace('本文链接：https','本文链接：\nhttps').replace('上一篇 >其他新闻','上一篇 >\n其他新闻').replace('收藏 分享','收藏\n分享')
        self.assertEqual(len(multiline),chrome_ranges(multiline,{'推荐文章'})[0][1])

    def test_author_footer_cannot_hide_following_reuse(self):
        prefix='本文分类：新闻\n本文链接：https://example.org/a/1\n上一篇 >文章\n收藏 分享\n'
        text=prefix+'甲'*82;offset=len(prefix)
        rows=[window(offset+30,100,52,39,.553,.408),window(offset,0,30,40,.628,.170)]
        item=dict(sourceKey='1',sourceRevisionId='1',matches=[],literalSummary={},acceptedCandidate=False,
                  semanticSummary=dict(status='EVALUATED'),semanticWindows=rows)
        report=dict(actualConfig=dict(params=dict(literal_minimum=32,min_chars=64,min_coverage=.25)),evidence=[item])
        refine(report,dict(documents=[dict(sourceRevisionId='1',text='乙'*200)]),text)
        self.assertTrue(item['semanticSummary']['suspectedReuse'])
        self.assertTrue(all(w['citationSupport'] for w in rows))


if __name__=='__main__':unittest.main()
