import unittest
from campus_detection.reference_versions import reference_groups


class ReferenceVersionsTest(unittest.TestCase):
    def test_only_supported_versions_share_compute_group_and_records_survive(self):
        text='新闻中心组织师生研讨新闻采访、事实核对、选题策划和录音整理，随后各小组完成现场实践。'*5
        url='https://example.edu/news/123.html'
        published=dict(sourceKey='1:BODY',sourceKind='BODY',sourceWorkId='1',sourceRevisionId='1',title='新闻中心开展业务交流',text=text+'\n原文发布日期：2026-10-20。原文链接：'+url+'。',sourceMetadata={'sourceType':'PUBLISHED','bodySources':[{'url':url}]})
        imported=dict(published,sourceKey='2:BODY',sourceWorkId='2',sourceRevisionId='2',text=text+text,url=url,sourceMetadata={'sourceType':'DATASET'})
        independent=dict(published,sourceKey='3:BODY',sourceWorkId='3',sourceRevisionId='3',text='作者独立撰写的评论文章。'+text,sourceMetadata={'sourceType':'PUBLISHED','bodySources':[{'url':url}]})
        changed=dict(imported,sourceKey='4:BODY',sourceWorkId='4',sourceRevisionId='4',text=text+'活动共32人参加。')
        docs=[published,imported,independent,changed];before=repr(docs);groups=reference_groups(docs)
        self.assertEqual(groups['1:BODY'],groups['2:BODY'])
        self.assertNotEqual(groups['1:BODY'],groups['3:BODY'])
        self.assertNotEqual(groups['1:BODY'],groups['4:BODY'])
        self.assertEqual(before,repr(docs))
        self.assertEqual(groups,reference_groups(list(reversed(docs))))


if __name__=='__main__':unittest.main()
