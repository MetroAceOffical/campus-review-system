"""Audit cached exact-content publication relations without counting URL aliases as new articles."""
import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl

from corpus import normalized,read_jsonl,extract_article
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]


def publication_identity(url):
    parts=urlsplit(url);host=(parts.hostname or '').lower();path=parts.path.rstrip('/') or '/'
    match=re.search(r'(?:^|/)c\d+a(\d+)/page\.s?html?$',path,re.I)
    if match:return (host,'webplus-article',match[1])
    match=re.search(r'/info/\d+/(\d+)\.s?html?$',path,re.I)
    if match:return (host,'vsb-article',match[1])
    return (host,'canonical-path',path,tuple(sorted(parse_qsl(parts.query))))


def content_relation(source,alternate):
    reasons=[]
    if publication_identity(source['url'])==publication_identity(alternate['url']):reasons.append('SAME_PUBLICATION_IDENTITY')
    if source.get('pageSha256') and source.get('pageSha256')==alternate.get('pageSha256'):reasons.append('IDENTICAL_HTML_ALIAS')
    if not normalized(source['text']) or normalized(source['text'])!=normalized(alternate['text']):reasons.append('BODIES_NOT_NORMALIZED_EXACT')
    return {'accepted':not reasons,'reasons':reasons,'exactCodepointEquality':source['text']==alternate['text'],
            'relationType':'NORMALIZED_EXACT_CONTENT_DISTINCT_PUBLICATION_RECORDS',
            'scope':'Known same content, not proof of authorship, chronology, permission or independent event. No paraphrase claim.'}


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-natural-relations-v1');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):raise ValueError('Use project dataset output')
    if (output/'READY').exists():raise ValueError('Natural relation version already frozen')
    clean=ROOT/'runtime/datasets/campus-clean-20261026-v2';clean_hashes=verify_ready(clean)
    partitions=ROOT/'runtime/datasets/campus-partitions-20261026-v1';partition_hashes=verify_ready(partitions)
    partition_rows={row['documentId']:(split,row) for split in ['train','calibration','dev','final'] for row in read_jsonl(partitions/(split+'.jsonl'))}
    # Reuse recorded final URLs instead of assuming every requested URL was a new page.
    final_urls={}
    for dbpath in sorted((ROOT/'runtime/datasets/campus-final-v1').glob('*/crawl.sqlite')):
        db=sqlite3.connect(f'file:{dbpath.resolve().as_posix()}?mode=ro',uri=True)
        payloads=db.execute('SELECT payload FROM articles').fetchall();db.close()
        for payload, in payloads:
            row=json.loads(payload);final_urls[(row['url'],row['pageSha256'])]=row.get('finalUrl',row['url'])
    stats=Counter();reasons=Counter();split_counts=Counter();parents=Counter();parent_sets={split:set() for split in ['train','calibration','dev','final']}
    events={split:set() for split in parent_sets};seen=set();records=[]
    for canonical in read_jsonl(clean/'corpus.jsonl'):
        split,parent=partition_rows[canonical['documentId']]
        if normalized(parent['text'])!=normalized(canonical['text']):raise ValueError('Partition body identity differs')
        source={**canonical,'url':canonical.get('finalUrl',canonical['url'])}
        for candidate in canonical.get('alternateSources',[]):
            stats['alternateRecordsChecked']+=1
            page_sha=candidate.get('pageSha256')
            if not page_sha:reasons['MISSING_ALT_PAGE_SHA']+=1;continue
            url=final_urls.get((candidate['url'],page_sha),candidate['url'])
            identity=(canonical['documentId'],publication_identity(url))
            if identity in seen:reasons['REPEATED_ALT_PUBLICATION_RECORD']+=1;continue
            seen.add(identity)
            if publication_identity(source['url'])==publication_identity(url):reasons['SAME_PUBLICATION_IDENTITY']+=1;continue
            if source.get('pageSha256')==page_sha:reasons['IDENTICAL_HTML_ALIAS']+=1;continue
            host=urlsplit(candidate['url']).netloc
            cached=(ROOT/'runtime/datasets/campus-final-v1'/host/'pages'/(page_sha+'.html')).resolve()
            if not cached.is_relative_to((ROOT/'runtime/datasets/campus-final-v1').resolve()):raise ValueError('Cache path out of scope')
            if not cached.is_file():reasons['MISSING_ALT_CACHE']+=1;continue
            if sha(cached)!=page_sha:raise ValueError('Alternate raw page changed')
            article=extract_article(cached.read_bytes(),url)
            if not article:reasons['ALT_BODY_NOT_EXTRACTED']+=1;continue
            alternate={**article,'url':url,'pageSha256':page_sha};proof=content_relation(source,alternate)
            if not proof['accepted']:reasons.update(proof['reasons']);continue
            key=hashlib.sha256((canonical['documentId']+'\0'+url+'\0'+page_sha).encode()).hexdigest()
            record={'relationId':key,'taskType':'CONTENT_CORRESPONDENCE','target':1,'split':split,
                    'labelOrigin':'traceable_correspondence','labelConfidence':'known','humanVerified':False,
                    'sourceIds':[canonical['documentId']],'sourceClusterId':parent['sourceClusterId'],'eventClusterId':parent['eventClusterId'],
                    'query':alternate['text'],'source':canonical['text'],'sourceOffsets':{'start':0,'end':len(canonical['text'])},
                    'queryOffsets':{'start':0,'end':len(alternate['text'])},'sourceUrl':source['url'],'queryUrl':url,
                    'sourcePageSha256':source.get('pageSha256'),'queryPageSha256':page_sha,'contentProof':proof,
                    'queryNormalizedBodySha256':hashlib.sha256(normalized(alternate['text']).encode()).hexdigest(),
                    'transformationKind':'natural_normalized_exact_content','productQueryEligible':len(alternate['text'])<=10000,
                    'usedDetectorScoresForTruth':False}
            records.append(record);split_counts[split]+=1;parent_sets[split].add(canonical['documentId']);events[split].add(parent['eventClusterId'])
    output.mkdir(parents=True,exist_ok=True)
    (output/'relations.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in records),encoding='utf-8')
    manifest={'state':'CACHED_EXACT_CONTENT_RELATIONS_AUDITED_NOT_FULL_NATURAL_EVALUATION','statistics':dict(stats),'exclusions':dict(reasons),
              'relationCount':len(records),'splitRelationCounts':dict(split_counts),'splitParentCounts':{split:len(values) for split,values in parent_sets.items()},
              'splitAutomaticEventCounts':{split:len(values) for split,values in events.items()},'productEligibleQueries':sum(row['productQueryEligible'] for row in records),
              'cleanManifestSha256':clean_hashes['manifest.json'],'partitionManifestSha256':partition_hashes['split-manifest.json'],
              'rawAltPagesHashVerified':True,'usedDetectorScoresForTruth':False,'naturalParaphrasesAccepted':0,'humanGold':False,
              'scope':'Natural cached normalized-exact content only. Same URL, known article/column aliases and identical HTML do not inflate relations. Different publication records are not independent events or evidence of actual copying/permission. Final natural target200 remains a separate unmet target if below200.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'READY').write_text(json.dumps({name:sha(output/name) for name in ['relations.jsonl','manifest.json']},indent=2),encoding='utf-8');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
