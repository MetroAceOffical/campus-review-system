import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from article_extraction import extract_article
from repair_campus_material import inherited_split
from run_campus_stage import recipe_paths
from prepare_corrected_training import remap_span

class MaterialQualityTests(unittest.TestCase):
    def test_nested_nodes_read_once_and_intentional_repeated_paragraphs_preserved(self):
        result=extract_article('<h1>校园报道</h1><article><p>首段<p>活动内容<span>与人物</span>。</p>尾段</p><p>活动内容与人物。</p><p>时间<br>地点<img src="/a.jpg"></p></article>','https://a.edu.cn/news.html')
        self.assertEqual(result['text'],'首段\n活动内容与人物。\n尾段\n活动内容与人物。\n时间\n地点')
        self.assertEqual(result['images'],['https://a.edu.cn/a.jpg'])
        self.assertEqual(result['nestedParagraphs'],1)
    def test_old_heldout_is_never_moved_to_training(self):
        self.assertEqual(inherited_split(['final'],False,'train'),'final')
        self.assertEqual(inherited_split(['train','final'],False,'train'),'QUARANTINE')
        self.assertEqual(inherited_split(['dev'],True,'train'),'QUARANTINE')
        self.assertEqual(inherited_split([],True,'final'),'train')
    def test_training_recipe_cannot_reduce_scale_or_epochs(self):
        root=Path(__file__).resolve().parents[3];value={'formalMinimums':{'correspondencePairs':20000,'retrievalGroups':1000,'bgeEpochs':2,'m3Epochs':2,'effectiveBatch':32},'paths':{'pairs':str(root/'runtime/pairs'),'partitions':str(root/'runtime/partitions')}}
        self.assertEqual(len(recipe_paths(value,root)),2)
        value['formalMinimums']['m3Epochs']=1
        with self.assertRaises(ValueError):recipe_paths(value,root)
    def test_reuse_requires_one_exact_normalized_source_occurrence(self):
        self.assertEqual(remap_span('甲 乙\n丙丁','开头。甲乙\n丙丁。',0,6),(3,8))
        self.assertIsNone(remap_span('甲乙','甲乙。甲乙',0,2))
        self.assertIsNone(remap_span('甲乙','甲丙',0,2))

if __name__=='__main__':unittest.main()
