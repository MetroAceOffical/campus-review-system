import json
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.preparation import prepare,sha
from campus_workbench.training_warmstart import check_parent
from campus_workbench.training_resume import train

class WarmstartTest(unittest.TestCase):
    def prepare(self,root,name,new=False,leak=False):
        rows=[]
        for split in ('train','validation','test'):
            for i in range(4):
                text=f'{split}原稿内容{i}'
                if new and split=='train':text=f'新增训练报道{i}'
                if leak and split!='train':text=f'独立的新评价材料{split}{i}'
                if leak and split=='train' and i==0:text='validation原稿内容0'
                rows.append(dict(id=f'{name}-{split}-{i}',sentence1=text,sentence2=text+'句子',label=i%2,source_id=f'{split}-{i}',split=split))
        source=root/(name+'.jsonl');source.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        folder=root/name;prepare(source,folder,'PAIRS',{},lambda e:None);return folder
    def test_loads_parent_weights_expands_vocab_updates_and_protects_holdout(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as temp:
            root=Path(temp);first=self.prepare(root,'first');second=self.prepare(root,'second',True)
            cfg=dict(epochs=1,batch_size=4,width=16,max_length=24,device='cpu',patience=0)
            parent=root/'parent';train(first,parent,'cnn',cfg,lambda e:None)
            descriptor=dict(folder=str(parent),manifestSha256=sha(parent/'manifest.json'),preparation=str(first),preparationSha256=sha(first/'manifest.json'))
            self.assertEqual('cnn',check_parent(descriptor,second,'cnn')['family'])
            events=[];result=train(second,root/'child','cnn',cfg,events.append,warmstart=descriptor)
            self.assertEqual(0,result['warmstart']['initialInheritedMaxDifference'])
            self.assertGreater(result['warmstart']['trainedInheritedMaxDifference'],0)
            self.assertGreater(result['warmstart']['addedTokens'],0)
            old=json.loads((parent/'vocab.json').read_text(encoding='utf-8'));new=json.loads((root/'child/vocab.json').read_text(encoding='utf-8'))
            self.assertTrue(all(new[k]==v for k,v in old.items()))
            self.assertTrue(any(e['stage']=='WARM_STARTED' for e in events))
            self.assertLessEqual(result['reloadMaxDifference'],1e-5)
            with self.assertRaisesRegex(ValueError,'验证|测试|隔离'):
                check_parent(descriptor,self.prepare(root,'leak',True,True),'cnn')
if __name__=='__main__':unittest.main()
