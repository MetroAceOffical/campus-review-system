"""Verify the browser-created M03 fixture over real HTTP; never record credentials."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
from probe_auth import exchange

ROOT=Path(__file__).resolve().parents[2]

def walk(node):
    yield node
    for child in node.get('content',[]): yield from walk(child)

def run(manuscript_id):
    accounts=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    _,body=exchange(opener,'/api/auth/csrf');token=body['data']
    status,_=exchange(opener,'/api/auth/login',{'username':'member1','password':accounts['member1']},{token['headerName']:token['token']})
    assert status==200
    status,body=exchange(opener,f'/api/manuscripts/{manuscript_id}/draft')
    assert status==200
    draft=body['data'];images=[node['attrs'] for node in walk(draft['content']) if node['type']=='campusImage']
    assert draft['title']=='M03浏览器验收稿（测试用途）'
    assert len(images)==2 and len({image['nodeId'] for image in images})==2
    assert [image['caption'] for image in images]==['第二图图注','第一图图注']
    assert images[0]['origin']=='ORIGINAL'
    assert images[1]['origin']=='CITED' and images[1]['sourceUrl']=='https://example.org/m03-image-one'
    assert draft['sources'][0]['url']=='https://example.org/m03-body'
    assert 'A😀中' in ''.join(node.get('text','') for node in walk(draft['content']))
    _,body=exchange(opener,'/api/auth/csrf');token=body['data']
    payload={key:draft[key] for key in ('title','schemaVersion','content','sources')}
    payload['expectedRevision']=str(int(draft['revision'])-1)
    request=urllib.request.Request(f'http://127.0.0.1:8080/api/manuscripts/{manuscript_id}/draft',data=json.dumps(payload).encode(),method='PUT',headers={'Content-Type':'application/json',token['headerName']:token['token']})
    try: response=opener.open(request,timeout=15)
    except urllib.error.HTTPError as error: response=error
    with response:
        assert response.status==409 and json.loads(response.read())['code']=='DRAFT_REVISION_CONFLICT'
    evidence={'stage':'M03','transport':'real browser plus HTTP','manuscriptId':manuscript_id,'revision':draft['revision'],
              'images':images,'bodySources':draft['sources'],'unicodePreserved':True,'staleRevisionRejected':True,
              'contentSha256':hashlib.sha256(json.dumps(draft['content'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
              'fixtureScope':'clearly labelled synthetic editor check; not a published/reference work'}
    (ROOT/'docs/midterm/evidence/M03-http.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print('M03 real browser draft and stale-revision HTTP checks PASS; no credentials recorded')

if __name__=='__main__':run(sys.argv[1])
