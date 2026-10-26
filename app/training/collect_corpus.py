"""Resumable public HTML acquisition. One worker and one-second spacing per host."""
import argparse
import concurrent.futures
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from corpus import extract_article, normalized

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runtime/datasets/campus-final-v1'
AGENT = 'campus-review-research/1.0'


def crawl_link(base, href):
    parts = urlsplit(urljoin(base,href))
    if parts.scheme not in {'https','http'} or parts.netloc != urlsplit(base).netloc:
        return None
    params = parse_qsl(parts.query,keep_blank_values=True)
    if any(key.lower() not in {'page','p','pageno'} or not value.isdigit() or not 1 <= int(value) <= 1000 for key,value in params):
        return None
    if not re.search(r'(\.s?html?$|/list\d*/?$|/XinWen/|/$)',parts.path,re.I):
        return None
    if re.search(r'(login|search|download|enroll|authentication)',parts.path,re.I):
        return None
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(sorted(params)),''))


def open_crawl_db(path):
    db = sqlite3.connect(path,timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, status TEXT, priority INT, error TEXT); CREATE TABLE IF NOT EXISTS articles(url TEXT PRIMARY KEY, body_sha TEXT, payload TEXT);')
    return db


def collect(source, max_pages):
    host = urlsplit(source['url']).netloc
    folder = OUT / host
    folder.mkdir(parents=True, exist_ok=True)
    db = open_crawl_db(folder / 'crawl.sqlite')
    session = requests.Session()
    session.headers['User-Agent'] = AGENT
    last = 0
    def get(url):
        nonlocal last
        for attempt in range(3):
            time.sleep(max(0, 1.5-(time.monotonic()-last)))
            last = time.monotonic()
            try:
                response = session.get(url, timeout=(10,25), allow_redirects=True)
                if response.status_code in {429,500,502,503,504}:
                    response.raise_for_status()
                return response
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt+1))
    robots_url = urlunsplit(('https',host,'/robots.txt','',''))
    try:
        robots_response = get(robots_url)
        (folder / 'robots.txt').write_bytes(robots_response.content)
        (folder / 'robots-fetch.json').write_text(json.dumps({'url':robots_url,'status':robots_response.status_code,'fetchedAt':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
        robots = RobotFileParser(robots_url)
        if robots_response.status_code == 404:
            robots.parse([])
        elif robots_response.status_code == 200:
            robots.parse(robots_response.text.splitlines())
        else:
            raise RuntimeError(f'robots inaccessible: {robots_response.status_code}')
        db.execute('INSERT OR IGNORE INTO pages VALUES(?,?,?,NULL)',(source['url'],'PENDING',0))
        db.execute("UPDATE pages SET status='PENDING',error=NULL WHERE url=?",(source['url'],))
        db.commit()
        for _ in range(max_pages):
            if db.execute('SELECT count(*) FROM articles').fetchone()[0] >= source.get('target',250):
                break
            row = db.execute("SELECT url FROM pages WHERE status='PENDING' ORDER BY priority DESC,rowid LIMIT 1").fetchone()
            if not row:
                break
            url = row[0]
            try:
                if not robots.can_fetch(AGENT,url):
                    raise RuntimeError('ROBOTS_DENIED')
                response = get(url)
                response.raise_for_status()
                if urlsplit(response.url).netloc != host or not robots.can_fetch(AGENT,response.url):
                    raise RuntimeError('REDIRECT_OUT_OF_SCOPE')
                if 'text/html' not in response.headers.get('Content-Type','').lower():
                    raise RuntimeError('NOT_HTML')
                if len(response.content) > 5*1024*1024:
                    raise RuntimeError('PAGE_TOO_LARGE')
                html = response.content.decode(response.apparent_encoding or 'utf-8', errors='replace')
                soup = BeautifulSoup(html,'html.parser')
                for anchor in soup.select('a[href]'):
                    link = crawl_link(response.url,anchor['href'])
                    if not link:
                        continue
                    priority = int(bool(re.search(r'(/info/|/20\d\d/|/a/\d|/XinWen/.+/)',urlsplit(link).path)))
                    db.execute('INSERT OR IGNORE INTO pages VALUES(?,?,?,NULL)',(link,'PENDING',priority))
                article = extract_article(html,response.url)
                if article and 200 <= len(normalized(article['text'])) <= 50000 and '\ufffd' not in article['text']:
                    page_sha = hashlib.sha256(response.content).hexdigest()
                    body_sha = hashlib.sha256(normalized(article['text']).encode()).hexdigest()
                    (folder / 'pages').mkdir(exist_ok=True)
                    (folder / 'pages' / (page_sha+'.html')).write_bytes(response.content)
                    article.update(url=url,finalUrl=response.url,school=source['school'],channel=source.get('channel','public_news'),
                                   fetchedAt=datetime.now(timezone.utc).isoformat(),pageSha256=page_sha,bodySha256=body_sha,
                                   labelOrigin='unknown',labelConfidence='unknown')
                    db.execute('INSERT OR REPLACE INTO articles VALUES(?,?,?)',(url,body_sha,json.dumps(article,ensure_ascii=False)))
                db.execute("UPDATE pages SET status='DONE' WHERE url=?",(url,))
            except Exception as error:
                db.execute("UPDATE pages SET status='FAILED',error=? WHERE url=?",(type(error).__name__+': '+str(error)[:200],url))
            db.commit()
        summary = {'host':host,'school':source['school'],'articles':db.execute('SELECT count(*) FROM articles').fetchone()[0],
                   'pages':dict(db.execute('SELECT status,count(*) FROM pages GROUP BY status'))}
    except Exception as error:
        summary = {'host':host,'school':source['school'],'error':str(error)}
    finally:
        db.close()
    (folder / 'status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--pages-per-host',type=int,default=600)
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text(encoding='utf-8'))
    if len({urlsplit(s['url']).netloc for s in sources}) != len(sources):
        raise ValueError('Only one worker per host permitted')
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(collect,source,args.pages_per_host) for source in sources]
        for future in concurrent.futures.as_completed(futures):
            print(json.dumps(future.result(),ensure_ascii=True),flush=True)


if __name__ == '__main__':
    main()
