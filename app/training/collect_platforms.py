"""Follow public platform articles linked by collected school pages; never bypass access gates."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests
from article_extraction import extract_article

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'runtime/datasets/campus-final-v1/public-platforms'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    discovery = ROOT/'runtime/datasets/campus-final-v1/platform-discovery.jsonl'
    rows = [json.loads(line) for line in discovery.read_text(encoding='utf-8').splitlines()]
    session = requests.Session();session.headers['User-Agent']='campus-review-research/1.0'
    rules,last = {},{}
    def get(url):
        host = urlsplit(url).netloc
        time.sleep(max(0,1.5-(time.monotonic()-last.get(host,0))))
        last[host] = time.monotonic()
        return session.get(url,timeout=(15,30))
    counts = {'discoveredLinks':len(rows),'acquiredArticles':0,'unavailable':0,'alreadyRecorded':0}
    for row in rows:
        url = row['url'];parts = urlsplit(url)
        if parts.netloc not in {'mp.weixin.qq.com','weibo.com','www.weibo.com'} or parts.scheme not in {'https','http'}:
            continue
        key = hashlib.sha256(url.encode()).hexdigest()
        path = OUT/(key+'.json')
        if path.exists():
            counts['alreadyRecorded'] += 1
            continue
        result = {'source':row,'state':'UNAVAILABLE','publisherVerified':False}
        try:
            if parts.netloc not in rules:
                response = get(f'https://{parts.netloc}/robots.txt')
                robot = RobotFileParser()
                if response.status_code == 200:
                    robot.parse(response.text.splitlines())
                elif response.status_code == 404:
                    robot.parse([])
                else:
                    robot = None
                rules[parts.netloc] = robot
                (OUT/(parts.netloc+'-robots.txt')).write_bytes(response.content)
            rule = rules[parts.netloc]
            if rule is None or not rule.can_fetch(session.headers['User-Agent'],url):
                raise RuntimeError('ROBOTS_INACCESSIBLE_OR_DENIED')
            if parts.netloc == 'mp.weixin.qq.com' and not parts.path.startswith('/s'):
                raise RuntimeError('NOT_A_PUBLIC_ARTICLE_LINK')
            response = get(url);response.raise_for_status()
            if urlsplit(response.url).netloc != parts.netloc or not rule.can_fetch(session.headers['User-Agent'],response.url):
                raise RuntimeError('LOGIN_OR_OUT_OF_SCOPE_REDIRECT')
            article = extract_article(response.content,response.url)
            if not article or len(article['text']) < 200:
                raise RuntimeError('NO_PUBLIC_ARTICLE_BODY')
            digest = hashlib.sha256(response.content).hexdigest()
            (OUT/(digest+'.html')).write_bytes(response.content)
            result.update(state='ACQUIRED_UNVERIFIED_PUBLISHER',article=article,finalUrl=response.url,pageSha256=digest,
                          labelOrigin='unknown',labelConfidence='unknown',fetchedAt=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
            counts['acquiredArticles'] += 1
        except Exception as error:
            result['error'] = type(error).__name__+': '+str(error)[:250]
            counts['unavailable'] += 1
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'status.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    print(json.dumps(counts),flush=True)


if __name__ == '__main__':
    main()
