"""Labelled real-model interruption probe. Each phase is resumable; no direct business DB writes."""
import http.cookiejar
import json
import sys
import time
import urllib.request
import uuid
from probe_auth import exchange,BASE,ROOT
from process_supervisor import stop,health
from runtime_manager import configuration

def run(action):
    config,runtime=configuration();directory=runtime/'probes/M13';directory.mkdir(parents=True,exist_ok=True);state_path=directory/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {}
    def save():state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    accounts=json.loads((runtime/'private-config/accounts.json').read_text());name='member1' if action=='interrupt' else 'reviewer'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));_,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':accounts[name]},{token['headerName']:token['token']})[0]==200
    _,token=exchange(opener,'/api/auth/csrf');token=token['data'];headers={token['headerName']:token['token']}
    def checked(path,data=None,extra=None):
        status,body=exchange(opener,path,data,{**headers,**(extra or {})});assert status==200,(status,body.get('code'));return body['data']
    if action=='interrupt':
        if state.get('interrupted'):raise RuntimeError('Already interrupted; rebuild/start and run verify instead')
        if 'fileIds' not in state:
            from PIL import Image,ImageDraw
            state['fileIds']=[]
            for index in range(6):
                image=Image.new('RGB',(3000,2000),(240-index*5,245,250));draw=ImageDraw.Draw(image)
                for row in range(25):draw.text((70,40+row*70),f'M13 RECOVERY TEST {index+1} LINE {row+1} - THIS IS A LABELLED FUNCTIONAL FIXTURE',fill=(20,45+index*10,95),font_size=32)
                path=directory/f'recovery-{index+1}.png';image.save(path);boundary='campus-'+uuid.uuid4().hex
                body=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="M13-recovery-{index+1}.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
                with opener.open(urllib.request.Request(BASE+'/api/files',data=body,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=75) as response:state['fileIds'].append(json.load(response)['data']['fileId'])
            save()
        if 'manuscriptId' not in state:state['manuscriptId']=checked('/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
        if 'receipt' not in state:
            text=('M13恢复验收，仅为明确标记的本机功能测试。投稿快照与成功证据在服务重启之后仍需保留；未完成检测创建新执行，旧执行迟到不能覆盖。南京传媒学院图文审核系统分别保存人工决定和模型计算结果。'*20)
            nodes=[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':text}]}]+[{'type':'campusImage','attrs':{'nodeId':f'image-{i}','fileId':file,'caption':f'M13恢复测试图{i+1}','origin':'ORIGINAL','sourceUrl':''}} for i,file in enumerate(state['fileIds'])]
            state['receipt']=checked(f'/api/manuscripts/{state["manuscriptId"]}/submissions',{'title':'M13重启恢复验收（测试用途）','expectedDraftRevision':0,'schemaVersion':'1','content':{'type':'doc','content':nodes},'sources':[]},{'Idempotency-Key':'cd852145-cb11-4293-8558-a3c180e5835b'});save()
        batch=state['receipt']['batchId'];deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            progress=checked('/api/detection-batches/'+batch+'/progress')
            if progress['completedItems']>=1 and any(row['status']=='RUNNING' for row in progress['items']):
                state['before']=progress;save();stop(config,runtime,'java',True);stop(config,runtime,'detector',True);state['interrupted']=True;save();print(json.dumps({'stage':'M13','phase':'interrupted','batchId':batch,'completedBeforeStop':progress['completedItems']}));return
            if progress['completedItems']==13:raise RuntimeError('Fixture finished before interruption; no recovery success claimed')
            time.sleep(.03)
        raise RuntimeError('No in-flight item observed; no interruption performed')
    elif action=='verify':
        assert state.get('interrupted');batch=state['receipt']['batchId'];deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            report=checked('/api/detection-batches/'+batch+'/report')
            if report['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED'):break
            time.sleep(1)
        assert report['status']=='COMPLETED',report['status']
        before={row['itemId']:row for row in state['before']['items']};kept=[];retried=[]
        for item in report['items']:
            previous=before[item['itemId']]
            if previous['status'] in ('COMPLETED','NOT_APPLICABLE'):assert previous['activeAttemptId']==item['activeAttemptId'];kept.append(item['itemId'])
            if previous['status']=='RUNNING' and previous['activeAttemptId']!=item['activeAttemptId']:retried.append(item['itemId'])
        assert kept and retried
        published=checked('/api/publications');assert published['total']>=2
        summary={'stage':'M13','realModelInterruption':True,'receipt':state['receipt'],'items':len(report['items']),'finalStatus':report['status'],'completedAttemptIdsPreserved':kept,'interruptedItemsReceivedNewAttempt':retried,'oldPublishedSnapshotsStillReadable':checked('/api/publications/2')['submissionId']=='1','modelsReady':{component:health(config,runtime,component)['ready'] for component in ('detector','ocr')},'scope':'Labelled synthetic functional fixture. Not an accuracy or throughput estimate.'}
        (ROOT/'docs/midterm/evidence/M13-recovery.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');state['verified']=True;save();print(json.dumps(summary))
    else:raise ValueError('Expected interrupt or verify')

if __name__=='__main__':run(sys.argv[1])
