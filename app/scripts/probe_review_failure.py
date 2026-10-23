"""Controlled M10 OCR outage fixture and read-only verification after browser retry."""
import http.cookiejar
import json
import sys
import time
import urllib.request
import uuid
from probe_auth import exchange,ROOT,BASE

def run(action):
    directory=ROOT/'runtime/probes/M10';directory.mkdir(parents=True,exist_ok=True);state_file=directory/'state.json'
    state=json.loads(state_file.read_text()) if state_file.exists() else {}
    def save():state_file.write_text(json.dumps(state,indent=2),encoding='utf-8')
    credentials=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    name='member1' if action=='prepare' else 'reviewer'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    _,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':credentials[name]},{token['headerName']:token['token']})[0]==200
    _,token=exchange(opener,'/api/auth/csrf');token=token['data'];headers={token['headerName']:token['token']}
    def checked(path,payload=None,extra=None):
        status,result=exchange(opener,path,payload,{**headers,**(extra or {})});assert status==200,(status,result.get('code'));return result['data']
    if action=='prepare':
        if 'fileId' not in state:
            path=ROOT/'runtime/test-images/m03-2.png';boundary='campus-'+uuid.uuid4().hex
            payload=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="M10-failure-test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            with opener.open(urllib.request.Request(BASE+'/api/files',data=payload,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=75) as response:state['fileId']=json.loads(response.read())['data']['fileId']
            save()
        if 'manuscriptId' not in state:state['manuscriptId']=checked('/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
        if 'submission' not in state:
            content={'type':'doc','content':[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':'M10现场审核与OCR故障恢复验收，明确测试稿件。图像识别故障不得掩盖其他检测结果。'*3}]},{'type':'campusImage','attrs':{'nodeId':'image','fileId':state['fileId'],'caption':'M10故障恢复测试图','origin':'ORIGINAL','sourceUrl':''}}]}
            state['submission']=checked(f'/api/manuscripts/{state["manuscriptId"]}/submissions',{'expectedDraftRevision':0,'title':'M10审核故障与恢复验收（测试用途）','schemaVersion':'1','content':content,'sources':[]},{'Idempotency-Key':'ef864569-284b-4aa5-9a1c-e5500123d710'});save()
        batch=state['submission']['batchId'];deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            progress=checked('/api/detection-batches/'+batch+'/progress')
            if progress['completedItems']==3:break
            time.sleep(1)
        assert progress['status']=='PARTIAL_FAILED',progress
        assert [item['status'] for item in progress['items']]==['COMPLETED','COMPLETED','FAILED']
        state['before']=progress;save();print(json.dumps({'stage':'M10','submissionId':state['submission']['submissionId'],'batchId':batch,'expectedFailure':'OCR_SERVICE_UNAVAILABLE','otherItemsRetained':True}))
    elif action=='verify':
        report=checked('/api/detection-batches/'+state['submission']['batchId']+'/report');assert report['status']=='COMPLETED'
        before=state['before']['items'];after=report['items'];assert [row['activeAttemptId'] for row in before[:2]]==[row['activeAttemptId'] for row in after[:2]]
        assert before[2]['activeAttemptId']!=after[2]['activeAttemptId'] and after[2]['activeAttempt']['attemptNo']==2
        again=checked('/api/detection-batches/'+state['submission']['batchId']+'/report')
        assert [[entry['evidenceId'] for entry in item['evidence']] for item in again['items']]==[[entry['evidenceId'] for entry in item['evidence']] for item in report['items']]
        result=after[2]['activeAttempt']['result']
        version=checked('/api/submissions/'+state['submission']['submissionId']);assert version['decision']['decision']=='APPROVE'
        published=checked('/api/publications/'+state['manuscriptId']);assert published['submissionId']==state['submission']['submissionId']
        summary={'stage':'M10','submissionId':state['submission']['submissionId'],'batchId':report['batchId'],'controlledActualOcrOutage':True,
                 'browserRetryCompleted':True,'onlyFailedItemReceivedNewAttempt':True,'evidenceIdsStableOnRefresh':True,'browserDecisionPersisted':True,'publishedApprovedSnapshot':True,'ocrStatus':result.get('ocrStatus'),'recognitionLines':len(result.get('recognitionLines',[])),
                 'scope':'labelled business acceptance fixture, no OCR accuracy claim'}
        (ROOT/'docs/midterm/evidence/M10-review-flow.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
    else:raise ValueError('Expected prepare or verify')

if __name__=='__main__':run(sys.argv[1])
