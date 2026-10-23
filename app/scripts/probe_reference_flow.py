"""M11 real administrator reference -> formal query -> disable/new-query check."""
import hashlib
import http.cookiejar
import json
import sys
import time
import urllib.request
import uuid
from probe_auth import exchange,ROOT,BASE

def run(stage):
    folder=ROOT/'runtime/probes/M11';folder.mkdir(parents=True,exist_ok=True);state_file=folder/'state.json'
    state=json.loads(state_file.read_text()) if state_file.exists() else {}
    def save():state_file.write_text(json.dumps(state,indent=2),encoding='utf-8')
    credentials=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':credentials[name]},{token['headerName']:token['token']})[0]==200
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];return opener,{token['headerName']:token['token']}
    admin,admin_headers=login('admin');member,member_headers=login('member2');reviewer,_=login('reviewer')
    def get(opener,path,payload=None,headers=None):
        status,result=exchange(opener,path,payload,headers);assert status==200,(path,status,result.get('code'));return result['data']
    def until(getter,predicate):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            value=getter()
            if predicate(value):return value
            time.sleep(1)
        raise RuntimeError('Reference flow did not finish; local resumable state retained')
    query='/api/references?q=M11%E7%AE%A1%E7%90%86%E5%91%98%E5%AF%BC%E5%85%A5%E9%AA%8C%E6%94%B6'
    listing=until(lambda:get(admin,query),lambda value:value['total']==1 and value['items'][0]['effectiveEnabled']==(stage=='before'));assert listing['total']==1
    row=listing['items'][0];reference=get(admin,'/api/references/'+row['referenceId']);state['referenceId']=row['referenceId']
    assert get(admin,'/api/publications?q=M11%E7%AE%A1%E7%90%86%E5%91%98%E5%AF%BC%E5%85%A5%E9%AA%8C%E6%94%B6')['total']==0
    if stage=='before':assert row['effectiveEnabled'] and row['originType']=='MANUAL'
    elif stage=='after':assert not row['requestedEnabled'] and not row['effectiveEnabled']
    else:raise ValueError('Expected before or after')
    if stage not in state:
        title=f'M11参考查询{stage}（测试用途）';created=get(member,'/api/manuscripts',{'organizationId':'2','title':title},member_headers)
        payload={key:reference[key] for key in ('schemaVersion','content','sources')};payload.update(title=title,expectedDraftRevision=0)
        state[stage]=get(member,f'/api/manuscripts/{created["manuscriptId"]}/submissions',payload,{**member_headers,'Idempotency-Key':str(uuid.uuid5(uuid.NAMESPACE_URL,'M11-reference-flow:'+stage))});save()
    receipt=state[stage];batch=receipt['batchId']
    until(lambda:get(member,'/api/detection-batches/'+batch+'/progress'),lambda result:result['status'] in ('COMPLETED','PARTIAL_FAILED'))
    report=get(reviewer,'/api/detection-batches/'+batch+'/report');assert report['status']=='COMPLETED'
    matches=[evidence for item in report['items'] for evidence in item['evidence'] if evidence['sourceWorkId']==row['referenceId']]
    if stage=='before':assert any(evidence['acceptedCandidate'] for evidence in matches)
    else:assert not matches
    (folder/(stage+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    state[stage+'Generation']=report['libraryGenerationId'];save()
    if stage=='after':
        prior=json.loads((folder/'before-report.json').read_text(encoding='utf-8'));again=get(reviewer,'/api/detection-batches/'+prior['batchId']+'/report')
        assert [[e['evidenceId'] for e in item['evidence']] for item in prior['items']]==[[e['evidenceId'] for e in item['evidence']] for item in again['items']]
        old_manifest=ROOT/'runtime/indexes'/prior['libraryGenerationId']/'manifest.json';assert hashlib.sha256(old_manifest.read_bytes()).hexdigest()==prior['pipelineManifest']['libraryManifestSha256']
        published=get(admin,'/api/publications?q=M10%E5%AE%A1%E6%A0%B8%E6%95%85%E9%9A%9C')['items'][0]
        for name in ('member1','member2','reviewer','admin'):
            actor,_=login(name);public=get(actor,'/api/publications/'+published['manuscriptId']);assert 'decision' not in public and 'report' not in public
            file_id=public['content']['content'][1]['attrs']['fileId']
            with actor.open(BASE+'/api/files/'+file_id,timeout=15) as image:assert image.status==200 and image.read()
        summary={'stage':'M11','manualReferenceId':row['referenceId'],'manualImportNotPublished':True,'newQueryMatchedManualReference':True,'browserDisableSwitched':True,
                 'afterDisableQueryExcludesReference':True,'oldReportAndGenerationRetained':True,'beforeGeneration':state['beforeGeneration'],'afterGeneration':state['afterGeneration'],
                 'allFourAccountsReadPublishedSnapshotAndImage':True,'publicationExcludesInternalDecisionAndReport':True,
                 'scope':'explicit browser-admin and HTTP acceptance fixtures; no retrieval accuracy claim'}
        (ROOT/'docs/midterm/evidence/M11-reference-flow.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
    else:print(json.dumps({'stage':'M11','referenceId':row['referenceId'],'generation':report['libraryGenerationId'],'actualQueryMatched':True,'manualImportNotPublished':True}))

if __name__=='__main__':run(sys.argv[1])
