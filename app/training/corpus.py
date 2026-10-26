"""Offline corpus contracts. This module never loads a detector or changes business data."""
import hashlib
import json
import re
import unicodedata
from collections import Counter,defaultdict
from datetime import date
from urllib.parse import urljoin


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def normalized(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


def visible_publication_date(soup):
    values = set()
    for node in soup.select('.entry-meta,.arti_metas,.ardate,.article-info,.cont-tit,.detail_box .time,.Article_PublishDate,.pubtime,.publish-time,time[datetime]'):
        text = node.get('datetime') or node.get_text(' ',strip=True)
        match = re.search(r'((?:19|20)\d{2})[-年./](\d{1,2})[-月./](\d{1,2})',text)
        if match:
            try:
                values.add(date(*map(int,match.groups())).isoformat())
            except ValueError:
                pass
    return next(iter(values)) if len(values)==1 else None


def extract_article(html, url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.select('script,style,nav,footer,header,noscript'):
        node.decompose()
    candidates = soup.select('.wp_articlecontent, .v_news_content, #vsb_content, #vsb_content_2, .Article_Content, .article-content, .article_content, .content-article, #js_content, article')
    if not candidates:
        return None
    body = max(candidates, key=lambda node: len(node.get_text(strip=True)))
    paragraphs = [re.sub(r'[\t \u3000]+', ' ', p.get_text(' ', strip=True)).strip() for p in body.find_all(['p'])]
    text = '\n'.join(p for p in paragraphs if p)
    if not text:
        text = '\n'.join(line.strip() for line in body.get_text('\n').splitlines() if line.strip())
    title = soup.find('h1') or soup.find('title')
    published = soup.find('meta', attrs={'name':re.compile('publishdate|pubdate|date', re.I)})
    publisher = soup.select_one('#js_name')
    return {'title':title.get_text(' ', strip=True) if title else '', 'text':text,
            'images':list(dict.fromkeys(urljoin(url, img.get('src','')) for img in body.find_all('img') if img.get('src'))),
            'publishedAt':published.get('content') if published else visible_publication_date(soup),
            'publisher':publisher.get_text(' ',strip=True) if publisher else None}


def cluster_splits(documents, positive_edges, seed=20261026):
    parent = {key:key for key in documents}
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def union(left, right):
        if left not in parent or right not in parent:
            return
        a,b = sorted((find(left),find(right)))
        parent[b] = a
    seen = {}
    for key,text in sorted(documents.items()):
        digest = hashlib.sha256(normalized(text).encode()).hexdigest()
        if digest in seen:
            union(key, seen[digest])
        else:
            seen[digest] = key
    for left,right in positive_edges:
        union(left,right)
    # The same cluster always takes the same partition, independent of iteration order.
    result = {}
    for key in sorted(documents):
        root = find(key)
        bucket = int(hashlib.sha256(f'{seed}:{root}'.encode()).hexdigest()[:8],16) % 100
        result[key] = {'sourceClusterId':root, 'eventClusterId':root,
                       'split':'aux_train' if bucket < 90 else 'aux_validation'}
    return result


def eligible_correspondence(row):
    if row.get('taskType') != 'CONTENT_CORRESPONDENCE':return False
    if row.get('target')==0 and row.get('labelOrigin')=='rule_inferred_noncorrespondence':
        basis=row.get('negativeBasis') or {}
        return row.get('labelConfidence')=='supported_rule' and basis.get('supported') is True and len(basis.get('factSpans',[]))>=2 and bool(basis.get('checks')) and all(basis['checks'].values())
    return row.get('labelConfidence') == 'known' and row.get('labelOrigin') in {'human_verified','controlled_construction','traceable_correspondence'}


def near_source_edges(documents):
    """Conservative shingle clustering, not a human-labelled event oracle."""
    shingles = {}
    frequency = Counter()
    for key,text in documents.items():
        text = normalized(text)
        values = {int.from_bytes(hashlib.blake2b(text[i:i+8].encode(),digest_size=8).digest(),'big') for i in range(max(0,len(text)-7))}
        shingles[key] = values
        frequency.update(values)
    threshold = max(5,len(documents)//100)
    rare = {key:{value for value in values if frequency[value] < threshold} for key,values in shingles.items()}
    buckets = defaultdict(list)
    candidates = set()
    for key in sorted(rare):
        for value in sorted(rare[key])[:32]:
            for other in buckets[value]:
                candidates.add((other,key))
            buckets[value].append(key)
    edges = []
    for left,right in sorted(candidates):
        a,b = rare[left],rare[right]
        overlap = len(a&b)
        if overlap < 32:
            continue
        containment = overlap/min(len(a),len(b))
        jaccard = overlap/len(a|b)
        if jaccard >= .65 or containment >= .85:
            edges.append((left,right))
    return edges
