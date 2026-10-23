"""Read-only HTTP verification of the M09 browser-created two-version fixture."""
import http.cookiejar
import json
import sys
import urllib.request
from probe_auth import exchange,ROOT
from probe_draft import walk

def run(manuscript):
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    accounts=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    _,token=exchange(opener,'/api/auth/csrf');token=token['data']
    assert exchange(opener,'/api/auth/login',{'username':'member1','password':accounts['member1']},{token['headerName']:token['token']})[0]==200
    def get(path):
        status,body=exchange(opener,path);assert status==200,(status,body.get('code'));return body['data']
    history=get(f'/api/manuscripts/{manuscript}/submissions');assert history['status']=='PENDING'
    assert [row['versionNo'] for row in history['items']]==[2,1]
    versions=[get('/api/submissions/'+row['submissionId']) for row in reversed(history['items'])]
    first,second=versions
    first_images=[node['attrs'] for node in walk(first['content']) if node['type']=='campusImage']
    second_images=[node['attrs'] for node in walk(second['content']) if node['type']=='campusImage']
    assert len(first_images)==len(second_images)==6
    assert [image['caption'] for image in first_images]==['验收图1','验收图2','验收图3','验收图4','验收图6','验收图5']
    assert second_images[1]['caption']=='第二版引用图注' and first_images[1]['origin']=='CITED'
    assert [image['nodeId'] for image in first_images]==[image['nodeId'] for image in second_images]
    assert first['sources'][0]['url']=='https://example.org/m09-body-v1' and second['sources'][0]['url']=='https://example.org/m09-body-v2'
    assert first['decision']['decision']=='RETURN' and second['decision'] is None
    assert 'A😀中' in ''.join(node.get('text','') for node in walk(first['content']))
    assert ''.join(node.get('text','') for node in walk(second['content'])).startswith('第二版已修改：')
    for row in history['items']:
        progress=get('/api/detection-batches/'+row['batchId']+'/progress');assert progress['totalItems']==13 and progress['completedItems']==13
        assert exchange(opener,'/api/detection-batches/'+row['batchId']+'/report')[0]==403
    summary={'stage':'M09','manuscriptId':manuscript,'versions':[row['submissionId'] for row in versions],
             'sixImagesEachVersion':True,'stableNodeOrder':True,'priorCaptionAndSourcesPreserved':True,'currentUnsavedEditsSubmitted':True,
             'bothBatches13ItemsCompleted':True,'memberFormalReportDenied':True,
             'browserObserved':['upload disables submission','service interruption retains six unsaved images','401 re-login preserves editor','return-modify-resubmit','history version switch'],
             'scope':'explicitly labelled acceptance fixture; return action used backend API before M10 reviewer page'}
    (ROOT/'docs/midterm/evidence/M09-browser-flow.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))

if __name__=='__main__':run(sys.argv[1])
