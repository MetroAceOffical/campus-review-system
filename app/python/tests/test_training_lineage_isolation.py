import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.training_identities import collect,require_disjoint

class LineageIsolationTest(unittest.TestCase):
    def test_sources_and_near_duplicate_material_stay_in_their_historical_partition(self):
        row={'sentence1':'新闻中心组织师生开展校园采访与新闻写作活动，参与同学围绕素材选择和现场记录进行交流。'*3,'sentence2':'学生整理采访笔记并核对消息来源，教师对稿件结构提出具体修改建议。'*3,'source_id':'news-001','_partitionGroup':'old-id-group'}
        old=collect([row]);new={**row,'source_id':'news-001','sentence1':'同一篇新闻的另一段新内容','sentence2':'不同于原段落的表达','_partitionGroup':'new-id-group'}
        with self.assertRaises(ValueError):require_disjoint(collect([new]),old,'来源重合')
        almost={**row,'source_id':'changed-id','sentence1':row['sentence1'].replace('教师','老师').replace('活动','实践',1),'sentence2':'完全独立的一段评估文字','_partitionGroup':'another'}
        with self.assertRaises(ValueError):require_disjoint(collect([almost]),old,'近重复')
        require_disjoint(collect([{'sentence1':'图书馆新增借阅设备与阅读空间','sentence2':'新闻学院组织青年教师参加教学研讨','source_id':'unrelated','_partitionGroup':'unique'}]),old,'不应拒绝')

if __name__=='__main__':unittest.main()
