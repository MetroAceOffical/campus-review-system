"""CPU Web training must progress while the original compute lane is occupied."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.training import compute_slot
from campus_workbench.preparation import sha,write_json

class WebCpuLaneTests(unittest.TestCase):
    def test_real_cli_cpu_training_while_shared_lane_is_locked(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as temporary:
            folder=Path(temporary);prepared=folder/'prepared';prepared.mkdir();artifacts={}
            for split,count in [('train',16),('validation',6),('test',6),('calibration',0)]:
                rows=[{'id':split+str(i),'sentence1':f'校园讲座{i}介绍学生活动','sentence2':f'校园消息{i}讨论教学安排','label':i%2,'_partitionGroup':split+str(i)} for i in range(count)]
                path=prepared/(split+'.jsonl');path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8');artifacts[path.name]=sha(path)
            write_json(prepared/'manifest.json',{'taskType':'PREPARATION','trainReady':True,'inputSha256':'a'*64,'artifacts':artifacts})
            config=folder/'config.json';write_json(config,{'action':'TRAIN','runtime':str(folder),'preparation':str(prepared),'output':str(folder/'output'),'family':'lr','device':'cpu','parameters':{'device':'cpu','max_iter':100}})
            with compute_slot(folder):
                result=subprocess.run([sys.executable,'-B',str(ROOT/'app/scripts/workbench_training.py'),'--config-file',str(config)],capture_output=True,text=True,encoding='utf-8',timeout=45,env=dict(os.environ,PYTHONIOENCODING='utf-8',OMP_NUM_THREADS='1'))
                self.assertEqual(result.returncode,0,result.stdout[-1500:]+result.stderr[-500:])
            manifest=json.loads((folder/'output/manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['trainRows'],16);self.assertEqual(manifest['status'],'COMPLETED')

if __name__=='__main__':unittest.main()
