"""Read each DOM text node once, including malformed nested campus-news paragraphs."""
import re
from urllib.parse import urljoin
from corpus import visible_publication_date

BODY_SELECTORS='.wp_articlecontent,.v_news_content,#vsb_content,#vsb_content_2,.Article_Content,.article-content,.article_content,.content-article,#js_content,article'
BLOCKS={'p','div','section','article','li','blockquote','h1','h2','h3','h4','h5','h6','tr','table','figure','figcaption','ul','ol','pre'}

def extract_article(html,url):
    from bs4 import BeautifulSoup,NavigableString,Comment,Tag
    soup=BeautifulSoup(html,'html.parser')
    for node in soup.select('script,style,nav,footer,header,noscript'):node.decompose()
    bodies=soup.select(BODY_SELECTORS)
    if not bodies:return None
    body=max(bodies,key=lambda node:len(node.get_text(strip=True)))
    pieces=[]
    def visit(node):
        if isinstance(node,Comment):return
        if isinstance(node,NavigableString):
            # Source formatting indentation alone is not article text.
            if not str(node).strip():
                if '\n' not in str(node):pieces.append(' ')
            else:pieces.append(re.sub(r'[\t\r\n \u3000\xa0]+',' ',str(node)))
        elif isinstance(node,Tag):
            boundary=node.name in BLOCKS or node.name=='br'
            if boundary:pieces.append('\n')
            for child in node.children:visit(child)
            if boundary:pieces.append('\n')
    visit(body)
    text='\n'.join(line.strip() for line in ''.join(pieces).splitlines() if line.strip())
    title=soup.find('h1') or soup.find('title')
    published=soup.find('meta',attrs={'name':re.compile('publishdate|pubdate|date',re.I)})
    publisher=soup.select_one('#js_name')
    return {'title':title.get_text(' ',strip=True) if title else '', 'text':text,
            'images':list(dict.fromkeys(urljoin(url,image['src']) for image in body.find_all('img') if image.get('src'))),
            'publishedAt':published.get('content') if published else visible_publication_date(soup),
            'publisher':publisher.get_text(' ',strip=True) if publisher else None,
            'extractionVersion':'dom-text-once-v2','nestedParagraphs':sum(bool(p.find_parent('p')) for p in body.find_all('p'))}
