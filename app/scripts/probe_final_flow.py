"""M15 fresh real-model version-return-publish-index-query acceptance.

Decisions are taken in the reviewer UI between phases, never inferred from model scores.
"""
import http.cookiejar
import json
import sys
import time
import urllib.request
import uuid
from probe_auth import ROOT,BASE,exchange

def run(action):
    directory=ROOT/'runtime/probes/M15';directory.mkdir(parents=True,exist_ok=True);state_path=directory/'state.json';state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    def save():state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    accounts=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));_,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':accounts[name]},{token['headerName']:token['token']})[0]==200
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];return opener,{token['headerName']:token['token']}
    member,headers=login('member1');reviewer,_=login('reviewer');admin,_=login('admin')
    def checked(opener,path,data=None,extra=None):
        status,response=exchange(opener,path,data,{**headers,**(extra or {})});assert status==200,(path,status,response.get('code'));return response['data']
    def until(getter,predicate,seconds=240):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            result=getter()
            if predicate(result):return result
            time.sleep(1)
        raise RuntimeError('M15 condition not reached; state retained, no success fabricated')
    if action=='prepare':
        if 'fileId' not in state:
            from PIL import Image,ImageDraw
            path=directory/'M15-live-test.png';image=Image.new('RGB',(1400,700),(240,248,253));draw=ImageDraw.Draw(image)
            for index,line in enumerate(['M15 LIVE ACCEPTANCE','CAMPUS REVIEW SYSTEM','IMMUTABLE VERSION AND HUMAN REVIEW','THIS IS A LABELLED FUNCTIONAL TEST']):draw.text((60,70+index*120),line,fill=(20,65,110),font_size=38)
            image.save(path);boundary='campus-'+uuid.uuid4().hex;body=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="M15-live-test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            with member.open(urllib.request.Request(BASE+'/api/files',data=body,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=75) as response:state['fileId']=json.load(response)['data']['fileId']
            save()
        if 'manuscriptId' not in state:state['manuscriptId']=checked(member,'/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
        if 'first' not in state:
            state['originalText']='M15现场完整链路验收，以下为明确标记的功能测试文字。南京传媒学院图文审核系统保存本次新输入的不可变版本，投稿成员先提交初稿，审核员写明退回理由，修改后再次提交；新版本通过后生成发布快照与参考条目，另一组织新稿应能检索到此测试来源。模型结果仅提供证据，人工决定独立保存。'*4
            nodes=[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':state['originalText']}]},{'type':'campusImage','attrs':{'nodeId':'image','fileId':state['fileId'],'caption':'M15现场验收测试图','origin':'ORIGINAL','sourceUrl':''}}]
            state['first']=checked(member,f'/api/manuscripts/{state["manuscriptId"]}/submissions',{'title':'M15现场完整闭环第一版（测试用途）','expectedDraftRevision':0,'schemaVersion':'1','content':{'type':'doc','content':nodes},'sources':[]},{'Idempotency-Key':'ab2f941b-106c-4fd8-8c8a-7c4b1479bc01'});save()
        report=until(lambda:checked(reviewer,'/api/detection-batches/'+state['first']['batchId']+'/report'),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED'));assert report['status']=='COMPLETED'
        print(json.dumps({'stage':'M15','phase':'ready-for-reviewer-return','manuscriptId':state['manuscriptId'],'submissionId':state['first']['submissionId'],'batchId':state['first']['batchId']}))
    elif action=='resubmit':
        first=checked(member,'/api/submissions/'+state['first']['submissionId']);assert first['decision']['decision']=='RETURN'
        if 'second' not in state:
            draft=checked(member,f'/api/manuscripts/{state["manuscriptId"]}/draft');state['finalText']='M15第二版已按审核意见补充图注与来源说明。'+state['originalText'];content=draft['content'];content['content'][0]['content'][0]['text']=state['finalText'];content['content'][1]['attrs']['caption']='M15修改后测试图注，原图身份保留'
            state['second']=checked(member,f'/api/manuscripts/{state["manuscriptId"]}/submissions',{'title':'M15现场完整闭环第二版（测试用途）','expectedDraftRevision':draft['revision'],'schemaVersion':'1','content':content,'sources':[]},{'Idempotency-Key':'7184c250-cb13-455a-b799-b65c3dfd05ae'});save()
        report=until(lambda:checked(reviewer,'/api/detection-batches/'+state['second']['batchId']+'/report'),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED'));assert report['status']=='COMPLETED'
        assert checked(member,'/api/submissions/'+state['first']['submissionId'])['content']==first['content']
        print(json.dumps({'stage':'M15','phase':'ready-for-reviewer-approve','submissionId':state['second']['submissionId'],'batchId':state['second']['batchId']}))
    elif action=='verify':
        version=checked(member,'/api/submissions/'+state['second']['submissionId']);assert version['decision']['decision']=='APPROVE'
        publication=checked(member,'/api/publications/'+state['manuscriptId']);assert publication['submissionId']==state['second']['submissionId']
        reference=until(lambda:checked(admin,'/api/references?q=M15'),lambda result:any(row['title']=='M15现场完整闭环第二版（测试用途）' and row['effectiveEnabled'] for row in result['items']))
        row=next(row for row in reference['items'] if row['title']=='M15现场完整闭环第二版（测试用途）');state['referenceId']=row['referenceId'];save()
        other,other_headers=login('member2')
        if 'query' not in state:
            if 'queryManuscriptId' not in state:state['queryManuscriptId']=checked(other,'/api/manuscripts',{'organizationId':'2'},other_headers)['manuscriptId'];save()
            state['query']=checked(other,f'/api/manuscripts/{state["queryManuscriptId"]}/submissions',{'title':'M15新稿检索已发布测试来源（测试用途）','expectedDraftRevision':0,'schemaVersion':'1','content':{'type':'doc','content':[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':state['finalText']}]}]},'sources':[]},{**other_headers,'Idempotency-Key':'12677d47-113a-45b5-b464-c9187bb76f5f'});save()
        report=until(lambda:checked(reviewer,'/api/detection-batches/'+state['query']['batchId']+'/report'),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED'));assert report['status']=='COMPLETED'
        evidence=[entry for item in report['items'] for entry in item['evidence'] if entry['sourceWorkId']==row['referenceId']];assert evidence and any(entry['evidenceType']=='TEXT_SIMILARITY' and entry.get('acceptedCandidate') and entry.get('matches') for entry in evidence)
        first=checked(member,'/api/submissions/'+state['first']['submissionId']);assert first['decision']['decision']=='RETURN' and first['content']['content'][0]['content'][0]['text']==state['originalText']
        roles={}
        for name in ('member1','member2','reviewer','admin'):
            opener,_=login(name);roles[name]={'formalReport':exchange(opener,'/api/detection-batches/'+state['second']['batchId']+'/report')[0],'experiments':exchange(opener,'/api/experiments')[0]}
        assert roles['reviewer']['formalReport']==200 and all(roles[name]['formalReport']!=200 for name in ('member1','member2','admin'))
        assert roles['admin']['experiments']==200 and all(roles[name]['experiments']==403 for name in ('member1','member2','reviewer'))
        assert exchange(other,'/api/manuscripts/'+state['manuscriptId']+'/draft')[0] in (403,404)
        dashboard=checked(admin,'/api/experiments/pawsx-zh-round2/bundle');assert abs(dashboard['metrics']['sets']['official_test']['models']['bert']['macro_f1']-.7369837959240795)<1e-12
        summary={'stage':'M15','freshRealInput':True,'manuscriptId':state['manuscriptId'],'first':state['first'],'second':state['second'],'query':state['query'],'reviewerUiReturnAndApprove':True,'priorVersionUnchanged':True,'publishedVersionIsApprovedSecond':True,'referenceId':row['referenceId'],'queryLibraryGenerationId':report['libraryGenerationId'],'realQueryMatchedNewPublishedSource':True,'evidenceIds':[entry['evidenceId'] for entry in evidence],'roleChecks':roles,'crossOrganizationDraftDenied':True,'frozenDashboardBertMacroF1Verified':True,'scope':'Labelled real functional acceptance, not detection accuracy evaluation.'}
        (ROOT/'docs/midterm/evidence/M15-final-flow.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');state['verified']=True;save();print(json.dumps(summary))
    else:raise ValueError('Expected prepare/resubmit/verify')

if __name__=='__main__':run(sys.argv[1])
