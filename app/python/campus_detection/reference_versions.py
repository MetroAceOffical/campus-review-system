"""Group well-supported publication versions for compute budgeting, never merge records."""
import hashlib,re,unicodedata
from urllib.parse import urlsplit,urlunsplit


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).lower() if c.isalnum())


def canonical_url(value):
    if not isinstance(value,str):return None
    try:
        parts=urlsplit(value.strip())
        if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password:return None
        host=parts.hostname.lower();port=parts.port
        if port and port!=({'http':80,'https':443}[parts.scheme]):host+=':'+str(port)
        return urlunsplit((parts.scheme,host,parts.path or '/',parts.query,''))
    except ValueError:return None


def publication(document):
    if document.get('sourceKind','BODY')!='BODY':return None
    metadata=document.get('sourceMetadata',{});text=document['text']
    url=canonical_url(document.get('url') or metadata.get('url'))
    if not url and metadata.get('sourceType')=='PUBLISHED':
        # A writer's citation alone does not establish that their own article is
        # the cited publication. Require the explicit archived-original footer.
        footer=re.search(r'\n原文发布日期[：:]',text)
        if not footer:return None
        link=re.search(r'原文链接[：:]\s*(https?://[^\s。]+)',text[footer.start():])
        supplied={canonical_url(s.get('url')) for s in metadata.get('bodySources',[]) if canonical_url(s.get('url'))}
        url=canonical_url(link[1]) if link else None
        if not url or supplied!={url}:return None
        text=text[:footer.start()]
    if not url:return None
    body=normalized(text);title=normalized(document.get('title',''))
    if len(body)<128 or len(title)<4:return None
    grams={body[i:i+16] for i in range(len(body)-15)}
    if len(grams)<32:return None
    return dict(url=url,title=title,grams=grams,numbers=set(re.findall(r'\d+',text)))


def reference_groups(documents):
    buckets={};groups={}
    for document in sorted(documents,key=lambda d:str(d.get('sourceKey',d['sourceRevisionId']))):
        key=str(document.get('sourceKey',document['sourceRevisionId']));description=publication(document)
        group=None
        if description:
            candidates=buckets.setdefault((description['url'],description['title']),[])
            for candidate in candidates:
                supported=True
                for previous in candidate['versions']:
                    common=len(description['grams']&previous['grams'])
                    coverage=[common/len(description['grams']),common/len(previous['grams'])]
                    if description['numbers']!=previous['numbers'] or min(coverage)<.90 or max(coverage)<.995:
                        supported=False;break
                if supported:group=candidate;break
            if group is None:
                group=dict(id='reference-'+hashlib.sha256((description['url']+'\0'+description['title']+'\0'+key).encode()).hexdigest()[:24],versions=[])
                candidates.append(group)
            group['versions'].append(description)
        groups[key]=group['id'] if group else 'record-'+hashlib.sha256(key.encode()).hexdigest()[:24]
    return groups
