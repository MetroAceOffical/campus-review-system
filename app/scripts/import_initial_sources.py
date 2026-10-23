"""Import the verified local manifest through the administrator HTTP API.

Progress and credentials remain local. Stable idempotency keys survive interruption.
Imported references stay QUEUED until the M07 worker prepares them.
"""
import hashlib
import http.cookiejar
import json
import mimetypes
from pathlib import Path
import urllib.request
import uuid
from initial_sources import ROOT,prepare_sources
from probe_auth import exchange,BASE

def run():
    manifest=prepare_sources()
    folder=ROOT/'runtime/import';folder.mkdir(parents=True,exist_ok=True)
    state_file=folder/'initial-import-state.json'
    state=json.loads(state_file.read_text()) if state_file.exists() else {'files':{},'works':{}}
    state.setdefault('rejectedImages',{})
    config_path=ROOT/'app/config/local.json'
    config=json.loads((config_path if config_path.exists() else ROOT/'app/config/local.example.json').read_text())
    limits=config['limits']
    def save():
        temporary=state_file.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2),encoding='utf-8');temporary.replace(state_file)
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    credentials=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    status,token=exchange(opener,'/api/auth/csrf');assert status==200
    token=token['data']
    status,_=exchange(opener,'/api/auth/login',{'username':'admin','password':credentials['admin']},{token['headerName']:token['token']});assert status==200
    _,token=exchange(opener,'/api/auth/csrf');token=token['data'];headers={token['headerName']:token['token']}
    for work in manifest['works']:
        key=work['externalKey']
        if key in state['works']:continue
        nodes=[];image_sources=[]
        for index,paragraph in enumerate(work['text'].split('\n')):
            if paragraph:nodes.append({'type':'paragraph','attrs':{'nodeId':f'body-{index}'},'content':[{'type':'text','text':paragraph}]})
        for image in work['images']:
            source=image['sourceMetadata'];image_key=source['image_id'];path=Path(image['path'])
            if source['width']*source['height']>limits['imagePixels'] or max(source['width'],source['height'])>limits['imageSide'] or path.stat().st_size>limits['imageBytes']:
                state['rejectedImages'][image_key]={'errorCode':'INITIAL_IMAGE_EXCEEDS_UPLOAD_LIMIT','sha256':image['sha256'],
                                                   'width':source['width'],'height':source['height'],'sourceUrl':source['image_url']}
                image_sources.append(dict(source,importStatus='REJECTED',errorCode='INITIAL_IMAGE_EXCEEDS_UPLOAD_LIMIT'));save();continue
            if image_key not in state['files']:
                data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==image['sha256']
                boundary='campus-'+uuid.uuid4().hex
                body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: {mimetypes.guess_type(path.name)[0]}\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
                request=urllib.request.Request(BASE+'/api/files',data=body,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary})
                with opener.open(request,timeout=75) as response:state['files'][image_key]=json.loads(response.read())['data']['fileId']
                save()
            nodes.append({'type':'campusImage','attrs':{'nodeId':image_key,'fileId':state['files'][image_key],
                         'caption':'','origin':'CITED','sourceUrl':source['image_url']}})
            image_sources.append(dict(source,fileId=state['files'][image_key],nodeId=image_key))
        metadata=dict(work['sourceMetadata'],initialImportKey=key,imageSources=image_sources)
        payload={'title':work['title'],'schemaVersion':'1','content':{'type':'doc','content':nodes},
                 'sources':[{'sourceId':'official-body','url':work['url']}] if work['text'] else [],'sourceMetadata':metadata}
        status,result=exchange(opener,'/api/references',payload,{**headers,'Idempotency-Key':str(uuid.uuid5(uuid.NAMESPACE_URL,'campus-initial-v1:'+work['url']))})
        if status!=200:raise RuntimeError(f'Initial import failed for {key}: HTTP {status}, code {result.get("code")}')
        state['works'][key]=result['data'];save()
    summary={'stage':'M06','importedWorks':len(state['works']),'officialTexts':manifest['textCount'],'officialImages':len(state['files']),
             'collectedImages':manifest['imageCount'],'rejectedImages':state['rejectedImages'],
             'processingStatus':'QUEUED','publishedByImport':False,'syntheticQueriesImported':False,'credentialsRecorded':False}
    (ROOT/'docs/midterm/evidence/M06-import.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))

if __name__=='__main__':run()
