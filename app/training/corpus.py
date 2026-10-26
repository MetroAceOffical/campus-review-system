"""Offline corpus contracts. This module never loads a detector or changes business data."""
import hashlib
import re
import unicodedata
from urllib.parse import urljoin


def normalized(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


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
            'publishedAt':published.get('content') if published else None,
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
    return row.get('taskType') == 'CONTENT_CORRESPONDENCE' and row.get('labelConfidence') == 'known' and row.get('labelOrigin') in {'human_verified','controlled_construction','traceable_correspondence'}
