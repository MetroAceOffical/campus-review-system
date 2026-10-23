"""M14 real HTTP boundaries and sequential model capacity, with resumable labelled fixtures.

No training, benchmark-score selection, DB writes, source-image resizing, or limit relaxation.
"""
from datetime import datetime,timezone
import hashlib
import http.cookiejar
import io
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error
import uuid
import psutil
from probe_auth import ROOT,BASE,exchange
from runtime_manager import configuration
from inspect_image import inspect

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def fixture_manifest(directory,limits):
    path=directory/'fixtures.json'
    if path.exists():
        manifest=json.loads(path.read_text(encoding='utf-8'))
        if manifest['limits']!=limits or sha(directory/'body.txt')!=manifest['bodySha256']:raise RuntimeError('Capacity configuration or body changed; existing evidence is not reusable')
        for row in manifest['representative']+manifest['nearLimit']+manifest['ocrCorners']:
            if sha(row['path'])!=row['sha256']:raise RuntimeError('Capacity fixture changed; no silent regeneration')
        return manifest
    from PIL import Image,ImageDraw,ImageFilter
    import numpy as np
    initial=json.loads((ROOT/'runtime/import/initial-sources.json').read_text(encoding='utf-8'));representative=[]
    for work in initial['works']:
        for image in work['images']:
            source=Path(image['path'])
            try:metadata=inspect(source,limits['imageBytes'],limits['imagePixels'],limits['imageSide'])
            except ValueError:continue
            representative.append({'path':str(source),'sha256':sha(source),'bytes':source.stat().st_size,**metadata,'sourceUrl':work['url'],'kind':'existing_official_original'})
            break
        if len(representative)==6:break
    if len(representative)!=6:raise RuntimeError('Six admitted representative original images unavailable')
    near=[]
    for index,(width,height) in enumerate([(4000,5000),(5000,4000),(8000,2500),(4000,5000),(5000,4000),(8000,2500)]):
        # Deterministic encoded noise is a stress fixture, not a campus/OCR accuracy sample.
        array=np.random.default_rng(20261023+index).integers(0,256,(height,width,3),dtype=np.uint8);image=Image.fromarray(array)
        low,high=1,95;best=None;quality=None
        while low<=high:
            middle=(low+high)//2;stream=io.BytesIO();image.save(stream,format='JPEG',quality=middle)
            data=stream.getvalue()
            if len(data)<=limits['imageBytes']:best=data;quality=middle;low=middle+1
            else:high=middle-1
        if best is None or len(best)<limits['imageBytes']*.95:raise RuntimeError('Natural stress JPEG not sufficiently close to byte boundary')
        target=directory/f'near-limit-{index+1}.jpg';target.write_bytes(best);image.close();del array,image,best,data
        metadata=inspect(target,limits['imageBytes'],limits['imagePixels'],limits['imageSide']);near.append({'path':str(target),'sha256':sha(target),'bytes':target.stat().st_size,**metadata,'quality':quality,'kind':'synthetic_natural_encoded_noise','sourceUrl':''})
    blank=directory/'empty-ocr.png';Image.new('RGB',(1600,1200),'white').save(blank)
    blurred=directory/'blurred-ocr.png'
    with Image.open(representative[0]['path']) as source:source.convert('RGB').filter(ImageFilter.GaussianBlur(24)).save(blurred)
    corners=[{'path':str(target),'sha256':sha(target),'bytes':target.stat().st_size,**inspect(target),'kind':kind,'sourceUrl':''} for target,kind in [(blank,'synthetic_blank'),(blurred,'blurred_copy_for_quality_check')]]
    intro='M14容量验收测试稿，仅用于本机输入上限与资源检查，不用于准确率评价。'
    original='\n'.join(work['text'] for work in initial['works'] if work['text'])
    if len(intro+original)<limits['bodyCodePoints']:raise RuntimeError('Existing official long-form text unavailable')
    body=(intro+original)[:limits['bodyCodePoints']];(directory/'body.txt').write_text(body,encoding='utf-8')
    manifest={'representative':representative,'nearLimit':near,'ocrCorners':corners,'bodyCodePoints':len(body),'bodySha256':sha(directory/'body.txt'),'limits':limits,'notes':['Near-limit JPEGs are deterministic synthetic stress data, not evidence of OCR accuracy.','The long-form fixture explicitly selects exactly 10000 code points from existing official source text after a test label; original sources are untouched.']}
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');return manifest

class Monitor:
    def __init__(self,runtime):
        self.runtime=runtime;self.samples=0;self.min_available=None;self.max_rss=0;self.max_cpu=0;self.max_gpu=None;self.seen={};self.started=time.monotonic();self.last_gpu=0
    def sample(self):
        available=psutil.virtual_memory().available;self.min_available=available if self.min_available is None else min(self.min_available,available);rss=0;cpu=0;processes={}
        for component in ('java','detector','ocr'):
            record=self.runtime/'processes'/f'{component}.json'
            if not record.exists():continue
            from process_supervisor import verify_process
            for saved in json.loads(record.read_text())['members']:
                process=verify_process(saved)
                if process:
                    for child in [process,*process.children(recursive=True)]:processes[child.pid]=child
        for pid,process in processes.items():
            try:
                key=(pid,process.create_time());tracked=self.seen.setdefault(key,process);rss+=tracked.memory_info().rss;cpu+=tracked.cpu_percent(None)
            except psutil.NoSuchProcess:continue
        self.max_rss=max(self.max_rss,rss);self.max_cpu=max(self.max_cpu,cpu);self.samples+=1
        if time.monotonic()-self.last_gpu>=2:
            self.last_gpu=time.monotonic()
            try:
                result=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                if result.returncode==0:
                    value=sum(int(line.strip()) for line in result.stdout.splitlines() if line.strip());self.max_gpu=value if self.max_gpu is None else max(self.max_gpu,value)
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
    def result(self):return {'samples':self.samples,'observationSeconds':time.monotonic()-self.started,'minimumSystemAvailableBytes':self.min_available,'peakProjectRssSumBytes':self.max_rss,'peakProjectCpuPercentOneCoreBasis':self.max_cpu,'peakTotalGpuUsedMiB':self.max_gpu,'notes':['RSS sum may double-count shared pages; system available memory is separately observed.','GPU value is total device memory, not solely this application. CPU percentages can exceed 100 on multiple cores.','Sampled observations, not a guaranteed minimum RAM requirement or production throughput estimate.']}

def check_capacity(config,fixtureManifest):
    runtime=ROOT/config['runtimeRoot'];directory=runtime/'probes/M14';directory.mkdir(parents=True,exist_ok=True);state_path=directory/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {'uploads':{},'batches':{},'boundaryCases':[]}
    def save():state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    evidence=ROOT/'docs/midterm/evidence/M14-capacity.json'
    if evidence.is_file() and state.get('boundariesComplete'):
        previous=json.loads(evidence.read_text(encoding='utf-8'))
        if previous['bodySha256']==fixtureManifest['bodySha256'] and set(previous['batches'])==set(state['batches']) and all(previous['batches'][label]['receipt']==receipt and previous['batches'][label]['status']=='PASS' for label,receipt in state['batches'].items()):
            print('M14 completed evidence reused; original measured resource observations preserved');return previous
    accounts=json.loads((runtime/'private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));_,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':accounts[name]},{token['headerName']:token['token']})[0]==200
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];return opener,{token['headerName']:token['token']}
    member,headers=login('member1');reviewer,_=login('reviewer');limits=fixtureManifest['limits'];monitor=Monitor(runtime)
    def checked(opener,path,data=None,extra=None):
        status,body=exchange(opener,path,data,{**headers,**(extra or {})});assert status==200,(path,status,body.get('code'));return body['data']
    def upload(path,key=None,expected=200,filename=None):
        if key and key in state['uploads']:return state['uploads'][key]
        path=Path(path);boundary='campus-'+uuid.uuid4().hex
        body=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename or path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        started=time.monotonic()
        try:response=member.open(urllib.request.Request(BASE+'/api/files',data=body,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=75)
        except urllib.error.HTTPError as failure:response=failure
        with response:status=response.status;result=json.load(response)
        monitor.sample();assert status==expected,(path.name,status,result.get('code'))
        if expected==200:
            receipt=result['data']
            if key:state['uploads'][key]=receipt;save()
            return receipt
        return {'httpStatus':status,'code':result.get('code'),'elapsedSeconds':time.monotonic()-started}
    if not state.get('boundariesComplete'):
        from PIL import Image
        cases=[]
        small=directory/'valid.png';Image.new('RGB',(32,32),'white').save(small);first=upload(small,'boundary-small')
        base=small.read_bytes()
        for name,length,expected in [('bytes-below',limits['imageBytes']-1,200),('bytes-exact',limits['imageBytes'],200),('bytes-over',limits['imageBytes']+1,413)]:
            target=directory/(name+'.png');target.write_bytes(base+b'\0'*(length-len(base)));result=upload(target,expected=expected);cases.append({'case':name,'bytes':length,'httpStatus':expected,'status':'PASS','fixture':'valid small PNG with explicit trailing padding for byte-boundary transport test'})
        for name,size,expected in [('pixels-exact',(4000,5000),200),('pixels-over',(4000,5001),413),('side-exact',(8000,1),200),('side-over',(8001,1),413)]:
            target=directory/(name+'.png');Image.new('RGB',size,'white').save(target);upload(target,expected=expected);cases.append({'case':name,'width':size[0],'height':size[1],'httpStatus':expected,'status':'PASS'})
        fake=directory/'fake.png';fake.write_text('This is not an image',encoding='utf-8');upload(fake,expected=415);cases.append({'case':'disguised-invalid-image','httpStatus':415,'status':'PASS'})
        gif=directory/'unsupported.gif';Image.new('RGB',(8,8),'white').save(gif);upload(gif,expected=415);cases.append({'case':'unsupported-gif','httpStatus':415,'status':'PASS'})
        actual=upload(small,filename='disguised.txt');assert actual['mimeType']=='image/png';cases.append({'case':'actual-decoded-format-used','httpStatus':200,'mimeType':actual['mimeType'],'status':'PASS'})
        webp=directory/'valid.webp';Image.new('RGB',(16,16),'blue').save(webp);assert upload(webp)['mimeType']=='image/webp';cases.append({'case':'static-webp','httpStatus':200,'status':'PASS'})
        if 'boundaryDraft' not in state:state['boundaryDraft']=checked(member,'/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
        id=state['boundaryDraft'];draft=checked(member,f'/api/manuscripts/{id}/draft');revision=draft['revision'];text=(directory/'body.txt').read_text(encoding='utf-8')
        payload={'expectedRevision':revision,'title':'😀'*200,'schemaVersion':'1','content':{'type':'doc','content':[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':text}]}]},'sources':[]}
        def put(value):
            req=urllib.request.Request(BASE+f'/api/manuscripts/{id}/draft',method='PUT',data=json.dumps(value).encode(),headers={**headers,'Content-Type':'application/json'})
            try:response=member.open(req,timeout=15)
            except urllib.error.HTTPError as failure:response=failure
            with response:return response.status,json.load(response)
        status,result=put(payload);assert status==200;payload['expectedRevision']=result['data']['revision'];cases.append({'case':'title-200-and-body-10000-codepoints','httpStatus':status,'status':'PASS'})
        oversized=json.loads(json.dumps(payload));oversized['title']+='😀';assert put(oversized)[0]==413;cases.append({'case':'title-201-codepoints','httpStatus':413,'status':'PASS'})
        oversized=json.loads(json.dumps(payload));oversized['content']['content'][0]['content'][0]['text']+='中';assert put(oversized)[0]==413;cases.append({'case':'body-10001-codepoints','httpStatus':413,'status':'PASS'})
        images=[{'type':'campusImage','attrs':{'nodeId':f'boundary-{index}','fileId':first['fileId'],'origin':'ORIGINAL','sourceUrl':'','caption':'M14数量边界测试'}} for index in range(7)]
        payload['content']['content']+=images[:6];status,result=put(payload);assert status==200;payload['expectedRevision']=result['data']['revision'];cases.append({'case':'six-images','httpStatus':200,'status':'PASS'})
        payload['content']['content'].append(images[6]);assert put(payload)[0]==413;preserved=checked(member,f'/api/manuscripts/{id}/draft');assert len(preserved['content']['content'])==7 and preserved['title']=='😀'*200;cases.append({'case':'seventh-image-rejected-and-prior-draft-preserved','httpStatus':413,'status':'PASS'})
        state['boundaryCases']=cases;state['boundariesComplete']=True;save()
    text=(directory/'body.txt').read_text(encoding='utf-8')
    for label,rows,body in [('representative',fixtureManifest['representative'],text),('nearLimit',fixtureManifest['nearLimit'],text),('ocrCorners',fixtureManifest['ocrCorners'],'M14模糊与空识别质量解释验收，仅为本机功能测试。'*20)]:
        if label in state['batches']:continue
        files=[upload(row['path'],label+'-'+str(index))['fileId'] for index,row in enumerate(rows)]
        key=label+'Manuscript'
        if key not in state:state[key]=checked(member,'/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
        nodes=[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':body}]}]+[{'type':'campusImage','attrs':{'nodeId':'image-'+str(index),'fileId':file,'origin':'CITED' if row['sourceUrl'] else 'ORIGINAL','sourceUrl':row['sourceUrl'],'caption':'M14 '+row['kind']}} for index,(row,file) in enumerate(zip(rows,files))]
        payload={'expectedDraftRevision':0,'title':'M14容量 '+label+'（测试用途）','schemaVersion':'1','content':{'type':'doc','content':nodes},'sources':[]}
        state['batches'][label]=checked(member,f'/api/manuscripts/{state[key]}/submissions',payload,{'Idempotency-Key':str(uuid.uuid5(uuid.NAMESPACE_URL,'M14-capacity-v1:'+label))});save();monitor.sample()
    deadline=time.monotonic()+1800;reports={};last_print=0
    while time.monotonic()<deadline:
        monitor.sample()
        for label,receipt in state['batches'].items():
            progress=checked(reviewer,'/api/detection-batches/'+receipt['batchId']+'/report')
            if progress['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED','CANCELLED'):reports[label]=progress
        if len(reports)==3:break
        if time.monotonic()-last_print>20:print(json.dumps({'stage':'M14','finishedBatches':list(reports),'waitingFor':list(set(state['batches'])-set(reports))}),flush=True);last_print=time.monotonic()
        time.sleep(1)
    def seconds(start,end):return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds() if start and end else None
    results={}
    for label,receipt in state['batches'].items():
        report=reports.get(label) or checked(reviewer,'/api/detection-batches/'+receipt['batchId']+'/report');(directory/(label+'-report.json')).write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        results[label]={'receipt':receipt,'status':'PASS' if report['status']=='COMPLETED' else 'FAIL','batchStatus':report['status'],'totalItems':report['totalItems'],'completedItems':report['completedItems'],'createdAt':report.get('createdAt'),'startedAt':report.get('startedAt'),'finishedAt':report.get('finishedAt'),'queueWaitSeconds':seconds(report.get('createdAt'),report.get('startedAt')),'computeWallSeconds':seconds(report.get('startedAt'),report.get('finishedAt')),'libraryGenerationId':report['libraryGenerationId'],'pipelineManifest':report['pipelineManifest'],
            'items':[{'itemId':item['itemId'],'type':item['type'],'status':item['status'],'attemptId':item['activeAttemptId'],'elapsedSeconds':seconds(item['activeAttempt'].get('startedAt'),item['activeAttempt'].get('finishedAt')) if item.get('activeAttempt') else None,'errorCode':item['activeAttempt']['errorCode'] if item.get('activeAttempt') else None,'ocrStatus':item.get('activeAttempt',{}).get('result',{}).get('ocrStatus') if item.get('activeAttempt') else None,'qualityFlags':item.get('qualityFlags',[]),'recognitionCacheHit':item.get('activeAttempt',{}).get('result',{}).get('recognitionCacheHit') if item.get('activeAttempt') else None} for item in report['items']]}
    order=list(results);serial=all(results[order[i]]['finishedAt'] and results[order[i+1]]['startedAt'] and results[order[i]]['finishedAt']<=results[order[i+1]]['startedAt'] for i in range(len(order)-1))
    summary={'stage':'M14','createdAt':datetime.now(timezone.utc).isoformat(),'transport':'real authenticated HTTP and real model services','limits':limits,'inputManifest':{key:[{field:row[field] for field in ('sha256','bytes','width','height','kind')} for row in fixtureManifest[key]] for key in ('representative','nearLimit','ocrCorners')},'bodySha256':fixtureManifest['bodySha256'],'bodyCodePoints':fixtureManifest['bodyCodePoints'],'boundaryCases':state['boundaryCases'],'batches':results,'multipleQueuedBatchesExecutedSerially':serial,'resources':monitor.result(),'limitations':fixtureManifest['notes']+['Single local acceptance observation, not a production throughput or accuracy estimate.','All fixtures are explicitly labelled and remain unpublished. Failure tests and byte padding are separately identified.']}
    (ROOT/'docs/midterm/evidence/M14-capacity.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'stage':'M14','batches':{key:value['status'] for key,value in results.items()},'boundaryCases':len(state['boundaryCases']),'serial':serial}));return summary

def cold_representative(config,manifest):
    from PIL import Image,PngImagePlugin
    runtime=ROOT/config['runtimeRoot'];directory=runtime/'probes/M14';state_path=directory/'cold-state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {'files':[],'inputs':[]}
    def save():state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    evidence=ROOT/'docs/midterm/evidence/M14-cold-capacity.json'
    if state.get('verified'):
        print('M14 cold OCR completed evidence retained');return json.loads(evidence.read_text(encoding='utf-8'))
    accounts=json.loads((runtime/'private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));_,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':name,'password':accounts[name]},{token['headerName']:token['token']})[0]==200
        _,token=exchange(opener,'/api/auth/csrf');token=token['data'];return opener,{token['headerName']:token['token']}
    member,headers=login('member1');reviewer,_=login('reviewer');monitor=Monitor(runtime)
    def checked(opener,path,data=None,extra=None):
        status,body=exchange(opener,path,data,{**headers,**(extra or {})});assert status==200,(status,body.get('code'));return body['data']
    for index,row in enumerate(manifest['representative']):
        if index<len(state['files']):continue
        target=directory/f'cold-original-{index+1}.png'
        with Image.open(row['path']) as source:
            rgba=source.convert('RGBA');pixels=hashlib.sha256(rgba.tobytes()).hexdigest();metadata=PngImagePlugin.PngInfo();metadata.add_text('capacity-fixture',f'M14 cold OCR lossless copy {index+1}')
            rgba.save(target,pnginfo=metadata);rgba.close()
        with Image.open(target) as decoded:assert hashlib.sha256(decoded.convert('RGBA').tobytes()).hexdigest()==pixels
        info=inspect(target);assert target.stat().st_size<=config['limits']['imageBytes'] and sha(target)!=row['sha256']
        boundary='campus-'+uuid.uuid4().hex;body=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="M14-cold-{index+1}.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+target.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        with member.open(urllib.request.Request(BASE+'/api/files',data=body,headers={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=75) as response:state['files'].append(json.load(response)['data']['fileId'])
        state['inputs'].append({'originalSha256':row['sha256'],'inputSha256':sha(target),'decodedRgbaSha256':pixels,'decodedPixelsUnchanged':True,'bytes':target.stat().st_size,'width':info['width'],'height':info['height']});save();monitor.sample()
    if 'manuscriptId' not in state:state['manuscriptId']=checked(member,'/api/manuscripts',{'organizationId':'1'})['manuscriptId'];save()
    if 'receipt' not in state:
        nodes=[{'type':'paragraph','attrs':{'nodeId':'body'},'content':[{'type':'text','text':(directory/'body.txt').read_text(encoding='utf-8')}]}]+[{'type':'campusImage','attrs':{'nodeId':'cold-'+str(index),'fileId':file,'caption':'M14同像素冷OCR测试图','origin':'CITED','sourceUrl':manifest['representative'][index]['sourceUrl']}} for index,file in enumerate(state['files'])]
        state['receipt']=checked(member,f'/api/manuscripts/{state["manuscriptId"]}/submissions',{'title':'M14六图冷OCR容量验收（测试用途）','expectedDraftRevision':0,'schemaVersion':'1','content':{'type':'doc','content':nodes},'sources':[]},{'Idempotency-Key':'caa4f6e1-6679-4592-a090-2e7839d8ea55'});save()
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        monitor.sample();report=checked(reviewer,'/api/detection-batches/'+state['receipt']['batchId']+'/report')
        if report['status'] in ('COMPLETED','PARTIAL_FAILED','FAILED'):break
        time.sleep(1)
    (directory/'cold-report.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    ocr=[item for item in report['items'] if item['type']=='OCR_AND_TEXT'];assert len(ocr)==6 and all(not item.get('activeAttempt',{}).get('result',{}).get('recognitionCacheHit') for item in ocr)
    def duration(start,end):return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds() if start and end else None
    summary={'stage':'M14','mode':'cold OCR, six representative images with identical decoded pixels','receipt':state['receipt'],'status':'PASS' if report['status']=='COMPLETED' else 'FAIL','bodyCodePoints':manifest['bodyCodePoints'],'bodySha256':manifest['bodySha256'],'inputs':state['inputs'],'totalItems':report['totalItems'],'completedItems':report['completedItems'],'queueWaitSeconds':duration(report.get('createdAt'),report.get('startedAt')),'computeWallSeconds':duration(report.get('startedAt'),report.get('finishedAt')),'pipelineManifest':report['pipelineManifest'],
        'ocrItems':[{'itemId':item['itemId'],'attemptId':item['activeAttemptId'],'status':item['status'],'ocrStatus':item['activeAttempt']['result'].get('ocrStatus'),'recognitionCacheHit':bool(item['activeAttempt']['result'].get('recognitionCacheHit')),'qualityFlags':item.get('qualityFlags',[]),'elapsedSeconds':duration(item['activeAttempt'].get('startedAt'),item['activeAttempt'].get('finishedAt'))} for item in ocr],'resources':monitor.result(),'limitations':['Lossless RGBA re-encoding changes file hash to avoid previous OCR cache; decoded pixels verified identical, originals unchanged.','Single local observation, no model training, no OCR accuracy or production throughput estimate.']}
    evidence.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');state['verified']=summary['status']=='PASS';save();print(json.dumps({'stage':'M14','coldOcrStatus':summary['status'],'coldOcrItems':6,'cacheHits':0}));return summary

def verify_url_limits(config):
    runtime=ROOT/config['runtimeRoot'];state_path=runtime/'probes/M14/state.json';state=json.loads(state_path.read_text());evidence=ROOT/'docs/midterm/evidence/M14-capacity.json';summary=json.loads(evidence.read_text(encoding='utf-8'))
    if any(row['case']=='source-url-exact-limit' for row in summary['boundaryCases']):return
    accounts=json.loads((runtime/'private-config/accounts.json').read_text());opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));_,token=exchange(opener,'/api/auth/csrf');token=token['data'];assert exchange(opener,'/api/auth/login',{'username':'member1','password':accounts['member1']},{token['headerName']:token['token']})[0]==200
    _,token=exchange(opener,'/api/auth/csrf');token=token['data'];headers={token['headerName']:token['token'],'Content-Type':'application/json'};path='/api/manuscripts/'+state['boundaryDraft']+'/draft';status,response=exchange(opener,path);assert status==200;draft=response['data']
    prefix='https://example.org/';url=prefix+'a'*(config['limits']['urlCharacters']-len(prefix));payload={key:draft[key] for key in ('title','schemaVersion','content')};payload.update(expectedRevision=draft['revision'],sources=[{'sourceId':'M14-url-boundary','url':url}])
    def put(value):
        try:response=opener.open(urllib.request.Request(BASE+path,method='PUT',headers=headers,data=json.dumps(value).encode()),timeout=15)
        except urllib.error.HTTPError as failure:response=failure
        with response:return response.status,json.load(response)
    status,response=put(payload);assert status==200;payload['expectedRevision']=response['data']['revision'];payload['sources'][0]['url']+='a';status,_=put(payload);assert status==400
    status,response=exchange(opener,path);assert status==200 and response['data']['sources'][0]['url']==url
    cases=[{'case':'source-url-exact-limit','characters':len(url),'httpStatus':200,'status':'PASS'},{'case':'source-url-over-limit-prior-draft-preserved','characters':len(url)+1,'httpStatus':400,'status':'PASS'}]
    summary['boundaryCases']+=cases;state['boundaryCases']+=cases;evidence.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');print('M14 URL boundaries: 2 PASS; original capacity resource samples preserved')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--cold',action='store_true');args=parser.parse_args()
    config,runtime=configuration();directory=runtime/'probes/M14';directory.mkdir(parents=True,exist_ok=True)
    manifest=fixture_manifest(directory,config['limits'])
    if args.cold:
        if cold_representative(config,manifest)['status']!='PASS':raise SystemExit(1)
    else:
        result=check_capacity(config,manifest)
        verify_url_limits(config)
        if any(row['status']!='PASS' for row in result['batches'].values()):raise SystemExit(1)
