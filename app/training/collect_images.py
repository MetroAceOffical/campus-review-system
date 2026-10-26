"""Bounded acquisition of public school image candidates. No gold labels are inferred."""
import argparse
import concurrent.futures
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser

import requests

from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection.image_geometry import _decode

AGENT='campus-review-research/1.0'


def public_image_url(url):
    try:
        parts=urlsplit(url)
        return parts.scheme in {'http','https'} and bool(parts.hostname) and parts.hostname.endswith('.edu.cn') and parts.port in {None,80,443} and not parts.username and not parts.password
    except ValueError:return False


def choose_candidates(originals,per_event=3):
    seen=set();counts=Counter();candidates=[]
    # Prioritize the local institution but bound each event, not each URL's spelling.
    for row in sorted(originals,key=lambda item:(item['institutionName']!='南京传媒学院',item['documentId'])):
        for url in row.get('images',[]):
            if url in seen or not public_image_url(url) or counts[row['eventClusterId']]>=per_event:continue
            seen.add(url);counts[row['eventClusterId']]+=1
            candidates.append({'sourceId':row['documentId'],'eventClusterId':row['eventClusterId'],'sourceClusterId':row['sourceClusterId'],
                               'institutionName':row['institutionName'],'articleUrl':row['url'],'imageUrl':url})
    return candidates


def image_metadata(payload):
    pixels=_decode(payload);height,width=pixels.shape[:2]
    if min(width,height)<180 or max(width,height)<400 or max(width,height)/min(width,height)>3:raise ValueError('DECORATION_OR_SMALL_IMAGE')
    return {'width':width,'height':height,'pixelSha256':hashlib.sha256(str((width,height)).encode()+pixels.tobytes()).hexdigest(),
            'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload),'coordinateFrame':'EXIF_ORIENTED_ORIGINAL_PIXELS'}


def collect_host(host,candidates,output,per_host,max_requests):
    folder=output/host;folder.mkdir(parents=True,exist_ok=True);(folder/'images').mkdir(exist_ok=True)
    db=sqlite3.connect(folder/'images.sqlite',timeout=30);db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS attempts(url TEXT PRIMARY KEY,state TEXT,payload TEXT,error TEXT)');db.commit()
    session=requests.Session();session.headers['User-Agent']=AGENT;last=0
    def get(url,limit):
        nonlocal last
        for attempt in range(3):
            time.sleep(max(0,1.5-(time.monotonic()-last)));last=time.monotonic()
            try:
                with session.get(url,timeout=(10,25),stream=True,allow_redirects=False) as response:
                    if response.status_code in {429,500,502,503,504}:response.raise_for_status()
                    if response.is_redirect:
                        # Record redirects without contacting another endpoint implicitly.
                        raise ValueError('REDIRECT_NOT_FETCHED:'+urljoin(url,response.headers.get('Location','')))
                    if response.status_code==404:return response.status_code,b'',response.headers
                    response.raise_for_status();body=bytearray()
                    if int(response.headers.get('Content-Length','0'))>limit:raise ValueError('RESPONSE_TOO_LARGE')
                    for chunk in response.iter_content(65536):
                        body.extend(chunk)
                        if len(body)>limit:raise ValueError('RESPONSE_TOO_LARGE')
                    return response.status_code,bytes(body),response.headers
            except requests.RequestException:
                if attempt==2:raise
                time.sleep(2**(attempt+1))
    try:
        robots_url=urlsplit(candidates[0]['imageUrl']).scheme+'://'+host+'/robots.txt'
        status,body,_=get(robots_url,1024*1024)
        (folder/'robots.txt').write_bytes(body)
        (folder/'robots-fetch.json').write_text(json.dumps({'url':robots_url,'httpStatus':status,'time':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
        robots=RobotFileParser(robots_url);robots.parse([] if status==404 else body.decode('utf-8',errors='replace').splitlines())
        rows=db.execute("SELECT payload FROM attempts WHERE state='ACQUIRED'").fetchall()
        unique={json.loads(row[0])['pixelSha256'] for row in rows};events=Counter(json.loads(row[0])['eventClusterId'] for row in rows)
        processed=0
        for candidate in candidates:
            if len(unique)>=per_host or processed>=max_requests:break
            url=candidate['imageUrl']
            if db.execute('SELECT 1 FROM attempts WHERE url=?',(url,)).fetchone() or events[candidate['eventClusterId']]>=2:continue
            processed+=1
            try:
                if not robots.can_fetch(AGENT,url):raise ValueError('ROBOTS_DENIED')
                _,payload,headers=get(url,10*1024*1024)
                if not headers.get('Content-Type','').lower().startswith('image/'):raise ValueError('NOT_IMAGE_RESPONSE')
                metadata=image_metadata(payload)
                if metadata['pixelSha256'] in unique:raise ValueError('DUPLICATE_PIXELS')
                path=folder/'images'/(metadata['sha256']+'.img');path.write_bytes(payload)
                record={**candidate,**metadata,'path':path.relative_to(output).as_posix(),'acquiredAt':datetime.now(timezone.utc).isoformat(),
                        'state':'IMAGE_SOURCE_CANDIDATE_UNVERIFIED','humanVerified':False,'eventBasis':'automatic_article_event_cluster',
                        'publicRedistributionPermission':'not_established','ocrTranscription':None,'relationshipToOtherPhotos':'unknown'}
                db.execute('INSERT INTO attempts VALUES(?,?,?,NULL)',(url,'ACQUIRED',json.dumps(record,ensure_ascii=False)))
                unique.add(metadata['pixelSha256']);events[candidate['eventClusterId']]+=1
            except Exception as error:
                db.execute('INSERT INTO attempts VALUES(?,?,NULL,?)',(url,'FAILED',type(error).__name__+': '+str(error)))
            db.commit()
            (folder/'status.json').write_text(json.dumps({'uniquePixelCandidates':len(unique),'requestsThisRun':processed,'neuralModelsRun':False}),encoding='utf-8')
        return {'host':host,'uniquePixelCandidates':len(unique),'requestsThisRun':processed,'error':None}
    except Exception as error:
        return {'host':host,'error':type(error).__name__+': '+str(error),'uniquePixelCandidates':0}
    finally:db.close();session.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-image-acquisition-v1')
    parser.add_argument('--per-host',type=int,default=24);parser.add_argument('--max-requests',type=int,default=100);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):raise ValueError('Use project dataset output')
    partitions=ROOT/'runtime/datasets/campus-partitions-20261026-v1';hashes=verify_ready(partitions)
    originals=[row for split in ['train','calibration','dev','final'] for row in read_jsonl(partitions/(split+'.jsonl'))]
    candidates=choose_candidates(originals);by_host=defaultdict(list)
    for row in candidates:by_host[urlsplit(row['imageUrl']).hostname].append(row)
    output.mkdir(parents=True,exist_ok=True)
    config={'partitionHashes':hashes,'perHostPixelTarget':args.per_host,'maxRequestsPerHostPerRun':args.max_requests,'spacingSeconds':1.5,'workers':args.workers,'perEventCandidateLimit':3,'state':'ACQUISITION_NOT_EVALUATION_OR_FINAL_SPLIT'}
    path=output/'config.json'
    if path.exists() and json.loads(path.read_text())!=config:raise ValueError('Acquisition configuration changed; use a new version')
    path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(collect_host,host,items,output,args.per_host,args.max_requests) for host,items in sorted(by_host.items())]
        completed=[]
        for future in concurrent.futures.as_completed(futures):
            result=future.result();completed.append(result);print(json.dumps(result),flush=True)
            (output/'status.json').write_text(json.dumps({'state':'ACQUIRING_PUBLIC_IMAGES','completedHosts':completed,'totalHosts':len(by_host),'neuralModelsRun':False},indent=2),encoding='utf-8')
    (output/'status.json').write_text(json.dumps({'state':'ACQUISITION_FINISHED_NOT_CLEANED_OR_EVALUATED','hosts':completed,'neuralModelsRun':False,'independentVerifiedEvents':None},indent=2),encoding='utf-8')


if __name__=='__main__':main()
