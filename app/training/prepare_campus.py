"""Freeze a cleaned acquisition snapshot; do not pretend source clusters are verified events."""
import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from corpus import normalized, near_source_edges, cluster_splits, extract_article

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):
        raise ValueError('Campus output must remain in project runtime/datasets')
    output.mkdir(parents=True,exist_ok=True)
    if (output/'READY').exists():
        raise RuntimeError('Immutable snapshot already exists; choose a new version')
    articles = []
    stats = Counter()
    inputs = []
    for path in sorted((ROOT/'runtime/datasets/campus-final-v1').glob('*/crawl.sqlite')):
        db = sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
        # Release read transactions before parsing to avoid stalling the live crawler.
        payloads = db.execute('SELECT payload FROM articles ORDER BY url').fetchall();db.close()
        for payload, in payloads:
            row = json.loads(payload)
            if not row.get('publishedAt'):
                cached = path.parent/'pages'/(row['pageSha256']+'.html')
                if cached.is_file():
                    recovered = extract_article(cached.read_bytes(),row['finalUrl'])
                    if recovered and recovered.get('publishedAt'):
                        row['publishedAt'] = recovered['publishedAt']
                        row['publishedAtOrigin'] = 'cached_article_publication_metadata'
            inputs.append({'url':row['url'],'pageSha256':row['pageSha256'],'bodySha256':row['bodySha256']})
            articles.append(row)
    # Reuse the existing verified campus sources without changing validation originals.
    for path in [ROOT/'validation/remaining/text/data/reference_sources.jsonl',ROOT/'validation/text/campus/sources.jsonl']:
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            body = (path.parent/row['body_path']).resolve()
            if not body.is_relative_to(path.parent.resolve()):
                raise ValueError('Historical body outside source directory')
            if hashlib.sha256(body.read_bytes()).hexdigest() != row['body_sha256']:
                raise ValueError('Historical source changed')
            articles.append({'url':row['url'],'finalUrl':row['url'],'title':row['title'],'text':row['text'],
                             'school':'南京传媒学院','publishedAt':row.get('published_at'),'fetchedAt':row.get('fetched_at'),
                             'historicalSourceManifest':path.relative_to(ROOT).as_posix(),'historicalBodySha256':row['body_sha256'],
                             'labelOrigin':'unknown','labelConfidence':'unknown'})
    canonical = {}
    for row in articles:
        text = row['text'].strip()
        if not row.get('title') or not 200 <= len(normalized(text)) <= 50000 or '\ufffd' in text:
            stats['excluded_body_or_title'] += 1
            continue
        if len(re.findall(r'[\u3400-\u9fff]',text))/max(1,len(text)) < .15:
            stats['excluded_non_chinese_body'] += 1
            continue
        digest = hashlib.sha256(normalized(text).encode()).hexdigest()
        if digest in canonical:
            canonical[digest]['alternateSources'].append({k:row.get(k) for k in ('url','school','pageSha256','historicalBodySha256')})
            stats['exact_duplicate_bodies'] += 1
            continue
        row['text'] = text
        row.update(documentId='campus:'+digest,normalizedBodySha256=digest,alternateSources=[],
                   institutionName='南京传媒学院' if row['school'].startswith('南京传媒学院') else row['school'],
                   sizeBucket='within_product_body_limit' if len(text)<=10000 else 'training_long_document')
        canonical[digest] = row
    documents = {row['documentId']:row['text'] for row in canonical.values()}
    edges = near_source_edges(documents)
    provisional = cluster_splits(documents,edges)
    # No split is emitted here: T2 train-body decontamination and event construction are pending.
    clusters = {key:{'sourceClusterId':value['sourceClusterId'],'eventClusterId':None,'eventStatus':'NOT_VERIFIED'} for key,value in provisional.items()}
    with (output/'corpus.jsonl').open('w',encoding='utf-8') as stream:
        for row in sorted(canonical.values(),key=lambda value:value['documentId']):
            row.update(clusters[row['documentId']]);stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest = {'schemaVersion':'1','state':'CLEAN_SOURCE_SNAPSHOT_NOT_FINAL_SPLIT','rawCandidateRows':len(articles),
                'uniqueCleanBodies':len(canonical),'sourceClusterCount':len({row['sourceClusterId'] for row in clusters.values()}),
                'nearDuplicateEdges':len(edges),'exclusions':dict(stats),'schools':dict(Counter(row['school'] for row in canonical.values())),
                'institutions':dict(Counter(row['institutionName'] for row in canonical.values())),
                'missingPublishedDate':sum(not row.get('publishedAt') for row in canonical.values()),
                'seed':20261026,'campusFinalProtocolFrozen':False,'independentEventCount':None,
                'pending':['T2 selected-training-body decontamination','conservative event clustering','train/calibration/dev/final split','controlled correspondence generation'],
                'nearSourceRule':{'shingleCharacters':8,'commonShingleDfThreshold':max(5,len(documents)//100),'minimumSharedRareShingles':32,'jaccard':.65,'containment':.85},
                'scope':'Automatic source deduplication only; no human-gold labels, no training/final predictions.'}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'input-pages.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=True),flush=True)


if __name__ == '__main__':
    main()
