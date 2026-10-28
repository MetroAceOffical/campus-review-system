"""Finite public API collection with cached-page reuse and conservative robots checks."""
import argparse,hashlib,json,math,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests

ROOT=Path(__file__).resolve().parents[2]
BASE='https://wap.cucn.edu.cn/cucneduapi/'
CATEGORIES=('6474c012f43e605f71f43cef','6475aa4728064a7587a51e36','6474d9be28064a758762df22','6475aa84f43e605f713fda49')
AGENT='campus-review-research/1.0'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(path)


def collect(output,max_wait_hours):
    sysroot=ROOT/'runtime/datasets'
    if not output.resolve().is_relative_to(sysroot):raise ValueError('Use project dataset output')
    if (output/'READY').exists():raise ValueError('Acquisition version already frozen')
    output.mkdir(parents=True,exist_ok=True);raw=output/'raw';raw.mkdir(exist_ok=True);logs=output/'requests.jsonl'
    config={'base':BASE,'categories':CATEGORIES,'pageSize':30,'maximumPagesPerCategory':40,'delaySeconds':1.5,
        'maximumWaitingHours':max_wait_hours,'retryTemporaryUnavailableSeconds':1800,'algorithmSha256':sha(Path(__file__))}
    if (output/'run.json').exists():
        previous=json.loads((output/'run.json').read_text(encoding='utf-8'));previous['categories']=tuple(previous['categories'])
        if previous!=config:raise ValueError('Collection identity changed; preserve and use a new version')
    else:write(output/'run.json',config)
    session=requests.Session();session.headers['User-Agent']=AGENT;last=0;downloaded=0;reused=0;deadline=time.monotonic()+max_wait_hours*3600
    def status(state,**values):write(output/'status.json',{'state':state,'newDownloadedPages':downloaded,'reusedHistoricalPages':reused,'newCorpusSourcesAudited':0,'trainingInputsChanged':False,**values})
    def get(url):
        nonlocal last
        time.sleep(max(0,1.5-(time.monotonic()-last)));last=time.monotonic()
        response=session.get(url,timeout=(10,25),allow_redirects=False)
        record={'url':url,'status':response.status_code,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(response.content).hexdigest(),'bytes':len(response.content)}
        with logs.open('a',encoding='utf-8') as stream:stream.write(json.dumps(record)+'\n')
        if len(response.content)>5*1024*1024:raise ValueError('Public page too large')
        return response,record
    # Reuse raw responses, including those not selected by the old small corpus.
    for meta_path in (ROOT/'validation/remaining/text/data/raw').glob('*-*.meta.json'):
        metadata=json.loads(meta_path.read_text(encoding='utf-8'))
        if not metadata.get('url','').startswith(BASE+'getArticleList.php?'):continue
        cached=meta_path.with_name(meta_path.name.replace('.meta.json','.json'))
        if sha(cached)!=metadata['sha256']:raise ValueError('Historical API cache hash changed')
        target=raw/cached.name
        if not target.exists():target.write_bytes(cached.read_bytes());write(raw/meta_path.name,{**metadata,'cacheRecoveredFrom':cached.relative_to(ROOT).as_posix()})
        reused+=1
    downloaded=sum('cacheRecoveredFrom' not in json.loads(path.read_text(encoding='utf-8')) for path in raw.glob('*.meta.json'))
    robots_url='https://wap.cucn.edu.cn/robots.txt'
    while True:
        try:
            response,record=get(robots_url);(output/'robots-response.bin').write_bytes(response.content);write(output/'robots-meta.json',record)
            text=response.content.decode('utf-8',errors='replace')
            if response.status_code==404:robots=RobotFileParser(robots_url);robots.parse([]);break
            if response.status_code==200 and '<html' not in text.lower() and ('user-agent:' in text.lower() or not text.strip()):
                robots=RobotFileParser(robots_url);robots.parse(text.splitlines())
                if not robots.can_fetch(AGENT,BASE+'getArticleList.php') or not robots.can_fetch('GPTBot',BASE+'getArticleList.php'):
                    status('ROBOTS_DENIED');return
                break
            if response.status_code in (401,403) or 300<=response.status_code<400:status('ACCESS_REQUIRES_REVIEW',httpStatus=response.status_code);return
            status('SOURCE_TEMPORARILY_UNAVAILABLE',retryAfterSeconds=1800)
        except requests.RequestException as error:status('SOURCE_NETWORK_UNAVAILABLE',errorType=type(error).__name__,retryAfterSeconds=1800)
        if time.monotonic()>=deadline:status('SOURCE_UNAVAILABLE_WAIT_FINISHED');return
        time.sleep(min(1800,max(0,deadline-time.monotonic())))
    for category in CATEGORIES:
        page=1;pages=40
        while page<=pages:
            target=raw/f'{category}-{page}.json';metadata=target.with_suffix('.meta.json')
            if target.exists() and metadata.exists():
                info=json.loads(metadata.read_text(encoding='utf-8'))
                if sha(target)!=info['sha256']:raise ValueError('Collection cache changed')
                payload=json.loads(target.read_text(encoding='utf-8'))
            else:
                url=BASE+f'getArticleList.php?categoryid={category}&size=30&page={page}'
                if not robots.can_fetch(AGENT,url) or not robots.can_fetch('GPTBot',url):status('ROBOTS_DENIED',url=url);return
                response,info=get(url)
                if response.status_code!=200:status('API_UNAVAILABLE',httpStatus=response.status_code);return
                try:payload=response.json()
                except ValueError:status('API_RETURNED_NON_JSON',url=url);return
                if payload.get('code')!=0 or not isinstance(payload.get('data',{}).get('list'),list):status('API_RETURNED_INVALID_PAYLOAD',url=url);return
                target.write_bytes(response.content);write(metadata,{**info,'final_url':url,'http_status':response.status_code});downloaded+=1
            pages=min(40,max(1,math.ceil(int(payload['data'].get('count',0))/30)))
            status('COLLECTING_PUBLIC_API',category=category,page=page,totalPages=pages);page+=1
    ready={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file() and p.name not in ('status.json','READY')}
    write(output/'READY',ready);status('PUBLIC_API_ACQUISITION_FROZEN_NOT_AUDITED')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--max-wait-hours',type=int,default=12);a=p.parse_args()
    if not 0<=a.max_wait_hours<=12:raise ValueError('Use a finite0..12hour wait')
    collect(a.output,a.max_wait_hours)
