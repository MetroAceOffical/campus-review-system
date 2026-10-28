"""Tiny CPU engineering checks; these are not formal campus training results."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench import training_resume as resume
from campus_workbench.preparation import sha,write_json


class WebResumeTests(unittest.TestCase):
    def test_actual_optimizer_boundary_resume_matches_continuous_cpu_training(self):
        import torch
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as temporary:
            folder=Path(temporary);prepared=folder/'data';prepared.mkdir();files={}
            for split,count in [('train',16),('validation',8),('test',8),('calibration',0)]:
                rows=[{'id':split+str(i),'sentence1':f'校园新闻第{i}条报道本次活动','sentence2':f'学院第{i}条消息介绍讲座内容','label':i%2,'_partitionGroup':split+str(i)} for i in range(count)]
                path=prepared/(split+'.jsonl');path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8');files[path.name]=sha(path)
            write_json(prepared/'manifest.json',{'taskType':'PREPARATION','trainReady':True,'inputSha256':'a'*64,'artifacts':files})
            cfg={'epochs':2,'batch_size':4,'width':16,'device':'cpu','dropout':.2,'patience':0,'gradient_accumulation':2,'max_length':24}
            full=resume.train(prepared,folder/'full','cnn',cfg,lambda e:None)
            class StopAfterSave(Exception):pass
            def interrupt(event):
                if event['stage']=='CHECKPOINT_SAVED':raise StopAfterSave()
            with self.assertRaises(StopAfterSave):resume.train(prepared,folder/'stopped','cnn',cfg,interrupt)
            meta=resume.checkpoint_metadata(folder/'stopped');self.assertEqual(meta['cursor'],8)
            descriptor={'folder':str(folder/'stopped'),'metadataSha256':sha(folder/'stopped/resume.json')}
            with self.assertRaisesRegex(ValueError,'参数'):
                resume.train(prepared,folder/'wrong','cnn',{**cfg,'epochs':3},lambda e:None,descriptor)
            events=[];actual=resume.train(prepared,folder/'continued','cnn',cfg,events.append,descriptor)
            self.assertEqual(len([e for e in events if e['stage']=='TRAINING']),6)
            self.assertEqual(len(actual['history']),2);self.assertEqual(actual['parameters']['epochs'],2)
            left=torch.load(folder/'full/best.pt',weights_only=True);right=torch.load(folder/'continued/best.pt',weights_only=True)
            for key in left:self.assertTrue(torch.allclose(left[key],right[key],atol=1e-7,rtol=1e-7),key)
            self.assertAlmostEqual(full['validation']['macro_f1'],actual['validation']['macro_f1'],places=7)
            for name,digest in actual['artifacts'].items():self.assertEqual(sha(folder/'continued'/name),digest)


if __name__=='__main__':unittest.main()
