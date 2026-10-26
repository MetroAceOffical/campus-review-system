import sys
import unittest
import tempfile
import json
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from campus_partitions import assign_partitions, training_overlap
from corpus import read_jsonl


class CampusPartitionTests(unittest.TestCase):
    def test_jsonl_keeps_unicode_line_separators_inside_the_original_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rows.jsonl'
            path.write_text(json.dumps({'text':'甲\u2028乙\u0085丙'},ensure_ascii=False)+'\n',encoding='utf-8')
            self.assertEqual(list(read_jsonl(path)),[{'text':'甲\u2028乙\u0085丙'}])

    def test_related_sources_never_cross_partitions_and_contaminated_events_are_train_only(self):
        rows=[{'documentId':key,'text':text,'institutionName':'南京传媒学院','sourceClusterId':cluster,'title':key} for key,text,cluster in [('a','原作内容','a'),('b','近重复原作','a'),('c','同一个事件其他报道','c'),('d','无关的其他事件','d')]]
        result=assign_partitions(rows,[('b','c')],{'c'})
        self.assertEqual(result['a']['split'],'train')
        self.assertEqual(result['a']['eventClusterId'],result['c']['eventClusterId'])
        self.assertEqual(result['a']['split'],result['b']['split'])
        self.assertEqual(result,assign_partitions(list(reversed(rows)),[('c','b')],{'c'}))

    def test_selected_training_sentence_quarantines_source_without_matching_short_template(self):
        sentence=''.join(f'志愿者第{i}组开展独立的乡村调研并整理研究资料' for i in range(12))
        campus={'a':sentence+'。新的后续内容。','b':'欢迎参加校园活动。这里介绍另一个不相同的研究过程。'}
        flagged=training_overlap(campus,iter([sentence,'欢迎参加校园活动。']))
        self.assertIn('a',flagged)
        self.assertNotIn('b',flagged)
