"""Resumable real M08 business loop; labelled fixtures, no credentials in evidence."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid
from probe_auth import exchange,BASE,ROOT

def run():
    folder=ROOT/'runtime/probes/M08';folder.mkdir(parents=True,exist_ok=True)
    state_file=folder/'state.json';state=json.loads(state_file.read_text()) if state_file.exists() else {}
    def save():
        temp=state_file.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(state_file)
    credentials=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _,token=exchange(opener,'/api/auth/csrf');token=token['data']
        status,_=exchange(opener,'/api/auth/login',{'username':name,'password':credentials[name]},{token['headerName']:token['token']});assert status==200
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];return opener,{token['headerName']:token['token']}
    member,member_headers=login('member1');second,second_headers=login('member2');reviewer,reviewer_headers=login('reviewer');admin,admin_headers=login('admin')
    def checked(opener,path,data=None,headers=None):
        status,result=exchange(opener,path,data,headers)
        if status!=200:raise RuntimeError(f'{path}: HTTP {status}, {result.get("code")}')
        return result['data']
    def until(getter,predicate,label):
        end=time.monotonic()+1200
        while time.monotonic()<end:
            value=getter()
            if predicate(value):return value
            time.sleep(2)
        raise RuntimeError(label+' timed out; resumable state retained')
    if 'fileId' not in state:
        path=ROOT/'validation/remaining/vision/inputs/mixed-known.png';boundary='campus-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="M08-test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
        request=urllib.request.Request(BASE+'/api/files',data=body,headers={**member_headers,'Content-Type':'multipart/form-data; boundary='+boundary})
        with member.open(request,timeout=75) as response:state['fileId']=json.loads(response.read())['data']['fileId']
        save()
    text='M08真实业务闭环验收，仅用于本机功能测试。南京传媒学院图文审核保存不可变送审快照，人工审核与模型报告分别记录，参考库新版本启用后可以查到明确测试来源。'*5
    def create_submission(label,opener,headers,organization,include_image):
        if label in state:return state[label]
        manuscript_key=label+'Manuscript'
        if manuscript_key not in state:state[manuscript_key]=checked(opener,'/api/manuscripts',{'organizationId':organization,'title':f'M08闭环验收稿{label}（测试用途）'},headers)['manuscriptId'];save()
        content=[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':text}]}]
        if include_image:content.append({'type':'campusImage','attrs':{'nodeId':'image','fileId':state['fileId'],'caption':'M08闭环测试图','origin':'CITED','sourceUrl':'https://example.org/m08-test'}})
        payload={'expectedDraftRevision':0,'title':f'M08闭环验收稿{label}（测试用途）','schemaVersion':'1','content':{'type':'doc','content':content},'sources':[]}
        key=str(uuid.uuid5(uuid.NAMESPACE_URL,'M08-closed-loop-v1:'+label))
        state[label]=checked(opener,f'/api/manuscripts/{state[manuscript_key]}/submissions',payload,{**headers,'Idempotency-Key':key});save();return state[label]
    first=create_submission('first',member,member_headers,'1',True)
    def progress(receipt,opener):return checked(opener,f'/api/detection-batches/{receipt["batchId"]}/progress')
    first_progress=until(lambda:progress(first,member),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED'),'first batch')
    assert first_progress['status']=='COMPLETED'
    if 'decision' not in state:
        state['decision']=checked(reviewer,f'/api/submissions/{first["submissionId"]}/decision',{'decision':'APPROVE','reason':'M08明确测试夹具，验证发布事务'},{**reviewer_headers,'Idempotency-Key':str(uuid.uuid5(uuid.NAMESPACE_URL,'M08-closed-loop-decision-v1'))});save()
    publication=checked(member,f'/api/publications/{state["firstManuscript"]}')
    assert publication['submissionId']==first['submissionId'] and publication['content']['content'][0]['content'][0]['text']==text
    def reference():
        page=1
        while True:
            listing=checked(admin,f'/api/references?page={page}&pageSize=100')
            for row in listing['items']:
                if row['sourceMetadata'].get('submissionId')==first['submissionId']:return row
            if page*100>=listing['total']:return {}
            page+=1
    ref=until(reference,lambda row:row.get('effectiveEnabled',False) and row.get('processingStatus') in ('READY','PARTIAL'),'published reference')
    later=create_submission('second',second,second_headers,'2',False)
    later_progress=until(lambda:progress(later,second),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED'),'later batch');assert later_progress['status']=='COMPLETED'
    status,_=exchange(second,f'/api/detection-batches/{later["batchId"]}/report');assert status==403
    report=checked(reviewer,f'/api/detection-batches/{later["batchId"]}/report')
    evidence=report['items'][0]['evidence'];assert any(row['sourceWorkId']==ref['referenceId'] and row['acceptedCandidate'] for row in evidence)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'stage':'M08','transport':'real authenticated HTTP -> Java -> main Python + OCR -> MySQL',
             'fixtureScope':'explicitly labelled local business acceptance records; no accuracy claim',
             'firstSubmissionId':first['submissionId'],'firstBatchStatus':first_progress['status'],'publishedSnapshotVerified':True,
             'publishedReferenceEnabled':True,'laterSubmissionId':later['submissionId'],'newQueryMatchesPublishedWork':True,
             'memberReportDenied':True,'reportSha256':hashlib.sha256((folder/'report.json').read_bytes()).hexdigest()}
    (ROOT/'docs/midterm/evidence/M08-business-loop.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))

if __name__=='__main__':run()
