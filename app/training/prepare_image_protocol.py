"""Freeze image families and controlled positives before any detector evaluation."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from collections import Counter,defaultdict
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageEnhance,ImageOps

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection.image_geometry import _decode,_phash


def image_families(rows):
    parent={row['imageId']:row['imageId'] for row in rows}
    def find(key):
        while parent[key]!=key:parent[key]=parent[parent[key]];key=parent[key]
        return key
    def union(a,b):
        a,b=sorted((find(a),find(b)));parent[b]=a
    seen={}
    for row in rows:
        for kind,key in [('event',row['eventClusterId']),('pixels',row['pixelSha256'])]:
            tag=(kind,key)
            if tag in seen:union(row['imageId'],seen[tag])
            else:seen[tag]=row['imageId']
    for index,row in enumerate(rows):
        for other in rows[:index]:
            if (int(row['phash'],16)^int(other['phash'],16)).bit_count()<=6:union(row['imageId'],other['imageId'])
    return {key:find(key) for key in parent}


def family_splits(families):
    groups=sorted(set(families.values()),key=lambda key:hashlib.sha256(('20261026:'+key).encode()).hexdigest())
    split={key:'development' if index%2==0 else 'final' for index,key in enumerate(groups)}
    return {key:split[group] for key,group in families.items()}


def controlled_variants(image):
    width,height=image.size;identity=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    new_width,new_height=max(1,round(width*.6)),max(1,round(height*.6))
    sx,sy=width/new_width,height/new_height
    yield 'resize',image.resize((new_width,new_height),Image.Resampling.LANCZOS),[[sx,0.,.5*sx-.5],[0.,sy,.5*sy-.5],[0.,0.,1.]]
    yield 'jpeg',image.copy(),identity
    left,top,right,bottom=round(width*.2),round(height*.2),round(width*.8),round(height*.8)
    yield 'crop',image.crop((left,top,right,bottom)),[[1.,0.,float(left)],[0.,1.,float(top)],[0.,0.,1.]]
    overlay=image.copy();draw=ImageDraw.Draw(overlay);draw.rectangle((0,0,width,max(25,height//12)),fill='white');draw.text((12,8),'SYNTHETIC TEST OVERLAY',fill='black')
    yield 'text_overlay',overlay,identity
    watermark=image.convert('RGBA');layer=Image.new('RGBA',image.size,(0,0,0,0));draw=ImageDraw.Draw(layer)
    for y in range(30,height,100):
        for x in range(20,width,180):draw.text((x,y),'CONTROL',fill=(255,255,255,140))
    combined=Image.alpha_composite(watermark,layer).convert('RGB');watermark.close();layer.close()
    yield 'watermark',combined,identity
    yield 'tint',ImageEnhance.Brightness(ImageEnhance.Color(image).enhance(.4)).enhance(1.12),identity


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    import cv2
    parser=argparse.ArgumentParser();parser.add_argument('--acquisition',type=Path,default=ROOT/'runtime/datasets/campus-image-acquisition-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-image-protocol-v1');parser.add_argument('--wait',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):raise ValueError('Use project dataset output')
    if (output/'READY').exists():raise RuntimeError('Image protocol already frozen')
    output.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+2*3600
    while True:
        try:state=json.loads((args.acquisition/'status.json').read_text())
        except (FileNotFoundError,json.JSONDecodeError):state={}
        if state.get('state')=='ACQUISITION_FINISHED_NOT_CLEANED_OR_EVALUATED':break
        if not args.wait or time.monotonic()>deadline:raise RuntimeError('Acquisition not complete; no final image protocol frozen')
        (output/'status.json').write_text(json.dumps({'state':'WAITING_IMAGE_ACQUISITION','evaluationStarted':False}),encoding='utf-8');time.sleep(10)
    rows=[]
    for dbpath in sorted(args.acquisition.glob('*/images.sqlite')):
        db=sqlite3.connect(f'file:{dbpath.resolve().as_posix()}?mode=ro',uri=True)
        payloads=db.execute("SELECT payload FROM attempts WHERE state='ACQUIRED' ORDER BY url").fetchall();db.close()
        for payload, in payloads:
            row=json.loads(payload);path=args.acquisition/row['path']
            if sha(path)!=row['sha256']:raise ValueError('Acquired image changed')
            pixels=_decode(path.read_bytes());pixel_sha=hashlib.sha256(str((pixels.shape[1],pixels.shape[0])).encode()+pixels.tobytes()).hexdigest()
            if pixel_sha!=row['pixelSha256']:raise ValueError('Decoded pixel identity changed')
            row.update(imageId='image:'+hashlib.sha256(row['imageUrl'].encode()).hexdigest(),phash=f'{_phash(pixels,cv2):016x}')
            rows.append(row)
    snapshot=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest();families=image_families(rows)
    canonical={}
    for row in rows:canonical.setdefault(row['pixelSha256'],row)
    by_family=defaultdict(list)
    for row in canonical.values():by_family[families[row['imageId']]].append(row)
    ordered=[]
    for level in range(max([len(items) for items in by_family.values()] or [0])):
        for family,items in sorted(by_family.items(),key=lambda item:hashlib.sha256(item[0].encode()).hexdigest()):
            if level<len(items):ordered.append(items[level])
    selected=ordered[:300];selected_groups={families[row['imageId']] for row in selected}
    if len(selected)<300 or len(selected_groups)<100:
        result={'state':'INSUFFICIENT_SOURCE_COUNT_OR_AUTOMATIC_FAMILIES','uniquePixelOriginals':len(canonical),'automaticImageFamilies':len(by_family),'neededOriginals':300,'neededFamilies':100,'evaluationStarted':False}
        (output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result));return
    selected_families={row['imageId']:families[row['imageId']] for row in selected};partitions=family_splits(selected_families)
    config={'seed':20261026,'acquisitionSnapshotSha256':snapshot,'originalCount':300,'automaticImageFamilies':len(selected_groups),
            'nearImageFamilyHamming':6,'variantsPerOriginal':7,'evaluationStarted':False,'realHardNegativeTruthCount':0,
            'scope':'Controlled positives and automatic article/image families only. Natural same-scene relationships are unknown, not gold negatives. No detector output created labels.'}
    config_path=output/'protocol.json'
    if config_path.exists() and json.loads(config_path.read_text())!=config:raise ValueError('Protocol input changed; use a new version')
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8');(output/'sources').mkdir(exist_ok=True);(output/'queries').mkdir(exist_ok=True)
    references=[];queries=[];image_hashes={};event_splits=defaultdict(set)
    for index,row in enumerate(selected):
        image_id=row['imageId'];split=partitions[image_id];family=selected_families[image_id]
        path=output/'sources'/f'{index:04d}.img';shutil.copyfile(args.acquisition/row['path'],path);image_hashes[path.relative_to(output).as_posix()]=sha(path)
        references.append({**row,'path':path.relative_to(output).as_posix(),'imageFamilyId':family,'split':split})
        event_splits[family].add(split)
        with Image.open(path) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
            identity=output/'queries'/f'{index:04d}-original.img';shutil.copyfile(path,identity)
            variants=[('original',identity,[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])]
            for kind,variant,mapping in controlled_variants(image):
                query_path=output/'queries'/f'{index:04d}-{kind}.jpg'
                try:variant.save(query_path,format='JPEG',quality=55 if kind=='jpeg' else 88)
                finally:variant.close()
                variants.append((kind,query_path,mapping))
            image.close()
        for kind,query_path,mapping in variants:
            digest=sha(query_path);image_hashes[query_path.relative_to(output).as_posix()]=digest
            queries.append({'queryId':f'image-control:{index:04d}:{kind}','sourceImageId':image_id,'sourceIds':[image_id],
                            'path':query_path.relative_to(output).as_posix(),'sha256':digest,'imageFamilyId':family,'split':split,
                            'transformation':kind,'queryToSourceHomography':mapping,'labelOrigin':'controlled_construction','humanVerified':False,
                            'target':1,'groundTruthScope':'LOCAL_REGION' if kind=='crop' else 'WHOLE_IMAGE','independentOriginals':1})
        (output/'status.json').write_text(json.dumps({'state':'WRITING_CONTROLLED_IMAGE_QUERIES','originalsWritten':index+1,'queriesWritten':len(queries),'evaluationStarted':False}),encoding='utf-8')
    if any(len(splits)>1 for splits in event_splits.values()):raise ValueError('Image family leaked across partitions')
    for name,items in [('references.jsonl',references),('queries.jsonl',queries)]:
        (output/name).write_text(''.join(json.dumps(item,ensure_ascii=False)+'\n' for item in items),encoding='utf-8')
    result={'state':'CONTROLLED_IMAGE_PROTOCOL_READY_NATURAL_NEGATIVES_PENDING','originals':len(references),'controlledQueries':len(queries),
            'automaticImageFamilies':len(selected_groups),'sourcePixelDuplicatesExcluded':len(rows)-len(canonical),'availableUniquePixelOriginals':len(canonical),
            'originalSplitCounts':dict(Counter(row['split'] for row in references)),'querySplitCounts':dict(Counter(row['split'] for row in queries)),
            'familySplitDisjoint':True,'realHardNegativeTruthCount':0,'evaluationStarted':False,'qualityAccepted':False,'productActivated':False,
            'scope':'300 different decoded original images; 2100 correlated transforms are not 2100 originals/events. Automatic families are not human-confirmed independent events.'}
    (output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    image_hashes.update({name:sha(output/name) for name in ['protocol.json','references.jsonl','queries.jsonl','manifest.json']})
    (output/'READY').write_text(json.dumps(image_hashes,indent=2),encoding='utf-8');(output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
