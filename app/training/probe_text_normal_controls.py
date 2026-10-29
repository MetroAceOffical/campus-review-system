"""New authored normal controls, never inserted into business news or training."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'app/python'),str(ROOT/'validation/text')]
from campus_shared.contracts import file_sha256,digest_json
from campus_shared.document_compute import document_slot
from campus_detection import contextual_text,reference_versions
from campus_detection.models import configurations
from campus_detection.text import detect_text
from run_document_evaluation import atomic_json


def material():
    originals=[
      ('采编资料归档服务调整','新闻中心完成了本学期采访资料目录的整理工作。工作人员按采访项目建立文件夹，将录音、照片、采访提纲和授权记录分别登记，并为每个项目补充检索关键词。资料室本周起采用预约方式提供查阅服务，申请人需要说明用途和所需范围。涉及个人隐私的原始材料由专人处理，借阅者只能取得经确认可以使用的部分。中心还设置了问题反馈表，用来记录缺失文件和错误链接，方便后续修复。此次调整针对内部资料管理，不涉及课程教学或对外招生。'),
      ('学生服务窗口增加材料预审','学生事务服务窗口开始试行材料预审。申请人可先提交材料清单，由工作人员检查文件是否齐全，再预约现场办理时段。预审只核对格式和材料完整性，具体业务仍由对应部门决定。窗口在等候区摆放了常见问题说明，并安排工作人员帮助不熟悉线上流程的同学填写申请。对需要补充材料的事项，系统会保留原申请编号，申请人不必重复填写已经确认的信息。试行期间，服务团队将记录等候时间和退补原因，据此调整窗口安排。'),
      ('校园网络设备维护安排','信息技术服务部门将对部分楼宇的网络接入设备开展维护。维护前，工作人员先核对设备编号和线路标记，并为正在使用的业务准备临时接入方案。各教学单位可提前登记需要连续联网的课程和活动，以便安排维护顺序。维护结束后，技术人员会逐层检查连接状态，确认常用教学平台可以正常访问。师生发现网络异常时，可通过统一服务入口提交所在位置、发生时间和故障现象，避免在多个群聊重复报修。'),
      ('图书馆优化预约书架','图书馆根据读者取书记录重新调整了预约书架的分区。新分区按取书期限设置清晰标识，读者收到到书提醒后，可在规定时间内凭校园身份完成借阅。超过保留期限的图书将返回流通环节，工作人员会在系统中更新状态。此次调整同时增加了无障碍取书协助，行动不便的读者可以提前联系服务台。图书馆将观察高峰时段的书架使用情况，并收集读者对标识、提醒方式和取书流程的意见。'),
      ('志愿服务队整理物资台账','校内志愿服务队对常用物资开展盘点。队员依次核对反光背心、应急药箱、指示牌和便携扩音设备，记录数量、完好情况及存放位置。对已经损坏的物品，物资管理员单独登记并安排处理。今后的活动负责人需要在领用前确认清单，活动结束后由双方核对归还情况。团队还制作了简明的交接说明，使新加入的成员能够按统一流程办理借还。该项工作主要改善日常保障，不安排校外走访或文艺演出。'),
      ('体育场地预约规则调整','体育场地管理部门汇总了近期预约记录，发现部分时段存在预约后未使用的情况。新的预约规则增加了到场确认和提前取消入口，临时不能参加的同学可以及时释放名额。工作人员将定期检查场地照明、饮水设施和安全提示牌，遇到设备故障时先暂停对应区域预约，再通知维修人员处理。使用者可以在预约页面查看场地开放状态，并提交设施问题。管理部门将根据实际使用情况逐步调整时段设置。'),
      ('学生作品文件提交规范说明','作品资料接收小组发布了文件提交说明。说明要求提交者保留可编辑的原始文件，同时提供便于预览的副本，并在目录中注明作品名称、参与人员和授权范围。文件名称应当清楚对应项目，不以最终版、最新版等模糊字样区分多个版本。小组将先检查文件能否打开，再核对目录与实际内容是否一致。发现缺失时会将问题集中反馈给提交者，避免多个工作人员分别提出重复要求。规范面向资料保存，不对作品作艺术评价。'),
      ('实验室完善器材借还登记','实验室对摄影摄像器材的借还登记表作了调整。借用者需要说明使用地点、预计归还时间和配件清单，工作人员在交接时核对电池、存储卡及连接线的状态。归还时发现异常的，双方应先记录现象，再由设备管理员安排检查，不自行拆卸维修。实验室为常用器材增加了操作提示，帮助初次借用的同学了解基本注意事项。后续将根据登记记录补充易遗漏配件的提示，并完善保管位置标识。'),
    ]
    notice='咨询事项请通过学校统一办事平台提交。涉及个人信息的材料须按通知指定方式递交，不在开放群聊中转发。具体受理时段以负责部门后续通知为准。'
    rows=[]
    for i,(title,body) in enumerate(originals):
        for variant,text in [('body',body),('department','供稿部门：校新闻中心。\n'+body),('notice',body+'\n'+notice)]:
            rows.append(dict(caseId=f'NORMAL-{i+1:02d}-{variant}',family=f'normal-authored-{i+1:02d}',title=title,text=text,expected='NO_REUSE',
                             truthOrigin='assistant_authored_control',humanVerified=False,referenceScope='Current library18; no source copying used when authoring',trainingExample=False))
    return rows


def main():
    import torch,psutil,joblib,round2
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(ROOT/'runtime/experiments') or out.exists():raise ValueError('New experiment directory required')
    out.mkdir();samples=material();atomic_json(out/'material.json',dict(cases=samples,independentAuthoredFamilies=8,variantsPerFamily=3,notNaturalGold=True))
    hashes={p.relative_to(ROOT).as_posix():file_sha256(p) for p in [Path(__file__),Path(contextual_text.__file__),Path(reference_versions.__file__),out/'material.json',ROOT/'runtime/indexes/18/manifest.json']}
    atomic_json(out/'run.json',dict(hashes=hashes,queries=24,requests=48,families=8,newNeuralTrainingSamples=0,productActivated=False,scope='Supplementary authored normal controls, not24independent natural documents'))
    started=time.perf_counter();deadline=time.monotonic()+3600;done=0
    def status(state,**extra):atomic_json(out/'status.json',dict(state=state,processed=done,total=48,elapsedSeconds=time.perf_counter()-started,**extra))
    def guard():
        for p,h in hashes.items():
            if file_sha256(ROOT/p)!=h:raise ValueError('Bound source changed')
    while True:
        guard()
        if time.monotonic()>deadline:raise TimeoutError('Finite evaluation wait expired')
        if psutil.virtual_memory().available<1.5*1024**3 or not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<1.2*1024**3:status('WAITING_GPU_RESOURCE');time.sleep(15);continue
        try:
            with document_slot(ROOT/'runtime',neural=True):
                torch.set_num_threads(2);_,bert,_,tokenizer=round2.load_selected('bert');tokenizer.model_max_length=10**8
                def predict(rows):return round2.predict_rows('bert',bert,rows,tokenizer=tokenizer,batch=8)[0].tolist() if rows else []
                base,_=configurations();candidate=contextual_text.configuration(base)
                library=json.loads((ROOT/'runtime/indexes/18/manifest.json').read_text(encoding='utf-8'));library['_textIndex']=joblib.load(ROOT/'runtime/indexes/18/text-index.joblib');results=[]
                with (out/'predictions.jsonl').open('w',encoding='utf-8') as stream:
                    for method,config,detect in [('baseline',base,detect_text),('context-lexical',candidate,contextual_text.detect)]:
                        models=dict(textConfig=config,textConfigs={config['configId']:config},tokenizer=tokenizer,predictBert=predict)
                        for sample in samples:
                            guard();cid=sample['caseId']+'-'+method;req=dict(taskId=cid,attemptId=cid,scene='PRECHECK',inputSnapshotKey='diagnostic:'+cid,inputSha256=digest_json(sample['text']),libraryGenerationId='18',configId=config['configId'],text=sample['text'],excludeManuscriptId=None)
                            report=detect(req,library,models);alerts=[e for e in report['evidence'] if e.get('literalAcceptedCandidate',e['acceptedCandidate']) or e.get('semanticSummary',{}).get('suspectedReuse')]
                            result=dict(caseId=sample['caseId'],family=sample['family'],method=method,alerted=bool(alerts),report=report);results.append(result);stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush();done+=1;status('RUNNING_NORMAL_CONTROLS',method=method,caseId=sample['caseId'])
                guard();summary=dict(state='NORMAL_CONTROLS_COMPLETE',queries=24,independentAuthoredFamilies=8,requests=48,methods={name:dict(queries=24,alertedDocuments=sum(r['alerted'] for r in results if r['method']==name),alertedFamilies=len({r['family'] for r in results if r['method']==name and r['alerted']}),elapsedMs=sum(r['report']['elapsedMs'] for r in results if r['method']==name)) for name in ['baseline','context-lexical']},elapsedSeconds=time.perf_counter()-started,scope='Authored8familiesx3controls; not natural-population false-positive rate',normalPopulationFpr=None)
                atomic_json(out/'summary.json',summary);atomic_json(out/'status.json',summary);print(json.dumps(summary));return
        except BlockingIOError:status('WAITING_SHARED_COMPUTE_SLOT');time.sleep(15)


if __name__=='__main__':
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2');main()
