import unittest
from campus_workbench.curated_bundles import isolate,partition

class CuratedBundlesTest(unittest.TestCase):
    def test_cross_split_normalized_sentence_is_quarantined_not_moved(self):
        rows=[dict(sentence1='南京传媒学院',sentence2='开展讲座',label=1,split='train'),dict(sentence1='南京 传媒学院',sentence2='不同事件',label=0,split='test')]
        kept,bad,counts=isolate(rows)
        self.assertEqual([],kept);self.assertEqual(2,len(bad));self.assertEqual(2,counts['cross_partition_sentence'])
    def test_conflict_and_symmetric_duplicate_do_not_pad_dataset(self):
        rows=[dict(sentence1='来源甲',sentence2='改写乙',label=1,split='train'),dict(sentence1='改写乙',sentence2='来源甲',label=1,split='train'),dict(sentence1='来源甲',sentence2='改写乙',label=0,split='train')]
        kept,bad,counts=isolate(rows)
        self.assertEqual([],kept);self.assertEqual(1,len(bad));self.assertEqual(1,counts['duplicate'])
        self.assertEqual(partition('event1'),partition('event1'))
