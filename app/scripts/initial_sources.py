"""Prepare reviewed local official sources; never include synthetic evaluation queries."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]

def prepare_sources():
    works={}
    source_files=[ROOT/'validation/remaining/text/data/reference_sources.jsonl',ROOT/'validation/text/campus/sources.jsonl']
    text_rows=[(path,source) for path in source_files for source in rows(path)]
    for source_file,source in text_rows:
        text=source['text']
        body=(source_file.parent/source['body_path']).resolve()
        if not body.is_relative_to(source_file.parent.resolve()) or hashlib.sha256(body.read_bytes()).hexdigest()!=source['body_sha256']:raise ValueError('Source text checksum changed')
        if body.read_text(encoding='utf-8').rstrip('\n')!=text:raise ValueError('Source text does not match verified body')
        url=source['url']
        if url in works:raise ValueError('Duplicate official source URL')
        works[url]={'externalKey':source['source_id'],'url':url,'title':source['title'],'text':text,'images':[],
                    'sourceMetadata':dict(source,sourceType='URL')}
        works[url]['sourceMetadata'].pop('text',None)
    image_rows=rows(ROOT/'validation/remaining/image/evaluation/data/images.jsonl')
    for source in image_rows:
        if source.get('source_kind')!='official_public_article_image':raise ValueError('Nonofficial image must not enter initial library')
        path=(ROOT/'validation/remaining/image/evaluation/data'/source['relative_path']).resolve()
        if not path.is_relative_to(ROOT/'validation/remaining/image/evaluation/data/originals'):raise ValueError('Image outside original source directory')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Source image checksum changed')
        url=source['source_url']
        if url not in works:
            works[url]={'externalKey':source['source_id'],'url':url,'title':source['title'],'text':'','images':[],
                        'sourceMetadata':{'sourceType':'URL','url':url,'published_at':source.get('published_at'),
                                          'permission_status':source['permission_status'],'public_redistribution_permission':source['public_redistribution_permission']}}
        works[url]['images'].append({'path':str(path),'sha256':source['sha256'],'sourceMetadata':source})
    return {'textCount':len(text_rows),'imageCount':len(image_rows),'works':list(works.values())}

if __name__=='__main__':
    manifest=prepare_sources();destination=ROOT/'runtime/import/initial-sources.json';destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'works':len(manifest['works']),'texts':manifest['textCount'],'images':manifest['imageCount'],'manifest':str(destination)}))
