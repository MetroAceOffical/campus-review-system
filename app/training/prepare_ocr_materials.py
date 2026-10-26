"""Freeze known-text synthetic OCR controls and separate untranscribed real runtime inputs."""
import argparse
import functools
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import PIL
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]


@functools.lru_cache(maxsize=16)
def _font(path,size):return ImageFont.truetype(str(path),size)


def render_notice(index,font_path):
    image=Image.new('RGB',(1200,1600),[(249,251,255),(255,251,245),(248,255,250)][index%3])
    draw=ImageDraw.Draw(image);draw.rectangle((0,0,20,image.height),fill=[(25,72,120),(112,48,35),(30,94,64)][index%3])
    lines=[];body_size=[12,16,20,28,36][index%5];mixed=index>=25
    title=f'合成OCR测试海报 第{index+1:03d}号'
    body=[f'日期：2026年11月{index%28+1:02d}日',f'时间：{8+index%10:02d}:30—{10+index%10:02d}:00',
          f'地点：综合实验楼 A{200+index}室',f'主题：数字媒介应用讨论 第{index+1}场',
          '参与对象：合成测试班级，不对应真实人员。','请准备纸笔，按议程顺序交流。',
          f'测试编号：SYNTH-{index+1:04d}','本材料仅用于文字识别研究。']
    if mixed:
        body[0]=f'Date / 日期: 2026-11-{index%28+1:02d}'
        body[2]=f'Location / 地点: Media Lab A{200+index}'
        body[3]=f'Topic / 主题: Digital Media Session {index+1}'
    body += [f'议程{number:02d}：第{index+1}组测试任务，记录观察与讨论结果。' for number in range(1,9)]
    specs=[(title,64,56,44),('合成测试材料，不是真实校园通知。',64,140,24)]
    specs += [(text,64,220+number*(body_size+24),body_size) for number,text in enumerate(body)]
    for number,(text,x,y,size) in enumerate(specs):
        font=_font(str(font_path),size);bbox=draw.textbbox((x,y),text,font=font)
        while bbox[2]>image.width-50 and size>10:
            size-=1;font=_font(str(font_path),size);bbox=draw.textbbox((x,y),text,font=font)
        if not 0<=bbox[0]<bbox[2]<=image.width or not 0<=bbox[1]<bbox[3]<=image.height:raise ValueError('Known OCR line would be clipped')
        draw.text((x,y),text,font=font,fill=(22,32,42))
        left,top,right,bottom=bbox
        lines.append({'lineId':f'line-{number+1}','text':text,'polygon':[[left,top],[right,top],[right,bottom],[left,bottom]],'fontSize':size})
    return image,lines


def transform_notice(image,lines,kind):
    sx=sy=1.
    if kind=='original':query=image.copy()
    elif kind=='downscale_jpeg':
        width,height=round(image.width*.75),round(image.height*.75);query=image.resize((width,height),Image.Resampling.LANCZOS);sx=width/image.width;sy=height/image.height
    elif kind=='blur':query=image.filter(ImageFilter.GaussianBlur(.45))
    elif kind=='low_contrast':
        white=Image.new('RGB',image.size,'white')
        try:query=Image.blend(image,white,.35)
        finally:white.close()
    else:raise ValueError('Unknown controlled OCR transform')
    return query,[{**row,'polygon':[[x*sx,y*sy] for x,y in row['polygon']]} for row in lines]


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-ocr-controls-v1')
    parser.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/msyh.ttc'))
    parser.add_argument('--images',type=Path,default=ROOT/'runtime/datasets/campus-image-protocol-v1');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):raise ValueError('Use project dataset output')
    if (output/'READY').exists():raise ValueError('OCR materials already frozen')
    image_hashes=verify_ready(args.images)
    references=[row for row in read_jsonl(args.images/'references.jsonl') if row['split']=='development']
    real=[];families=set()
    for row in sorted(references,key=lambda item:hashlib.sha256(item['imageId'].encode()).hexdigest()):
        if row['imageFamilyId'] in families:continue
        families.add(row['imageFamilyId']);real.append(row)
        if len(real)==50:break
    if len(real)<50:raise ValueError('Need 50 separate real development image families for runtime coverage')
    order=sorted(range(50),key=lambda index:hashlib.sha256(f'ocr-20261026:{index}'.encode()).hexdigest());development=set(order[:25])
    protocol={'schemaVersion':'ocr-controls-v1','seed':20261026,'knownTextSyntheticQueries':200,'syntheticOriginalFamilies':50,
              'syntheticLayoutFontSizes':[12,16,20,28,36],'syntheticLayouts':5,'ChineseOriginals':25,'mixedOriginals':25,
              'transforms':['original','downscale_jpeg','blur','low_contrast'],'syntheticSplitCounts':{'development':100,'final':100},
              'realRuntimeImages':50,'realTranscriptionsAvailable':0,'realParentSplit':'image-development-only',
              'imageReferencesManifestSha256':image_hashes['references.jsonl'],'fontSha256':sha(args.font),'Pillow':PIL.__version__,
              'normalization':'Remove Unicode whitespace only; preserve case, punctuation and digits. GT is rendered top-to-bottom line order.',
              'coordinateSpace':'VARIANT_IMAGE_PIXELS','modelInferenceStarted':False,
              'scope':'200 correlated transforms of 50 synthetic notices, not 200 real posters. Real campus images have no known transcription and cannot enter CER denominators.'}
    output.mkdir(parents=True,exist_ok=True);config=output/'protocol.json'
    if config.exists() and json.loads(config.read_text(encoding='utf-8'))!=protocol:raise ValueError('OCR material identity changed; use a new version')
    config.write_text(json.dumps(protocol,indent=2),encoding='utf-8');(output/'synthetic').mkdir(exist_ok=True);(output/'real').mkdir(exist_ok=True)
    samples=[];hashes={}
    for index in range(50):
        image,lines=render_notice(index,args.font)
        try:
            for kind in protocol['transforms']:
                query,truth=transform_notice(image,lines,kind);path=output/'synthetic'/f'{index:03d}-{kind}.jpg'
                try:query.save(path,format='JPEG',quality=60 if kind=='downscale_jpeg' else 95);width,height=query.size
                finally:query.close()
                digest=sha(path);hashes[path.relative_to(output).as_posix()]=digest
                samples.append({'sampleId':f'ocr-synthetic:{index:03d}:{kind}','sourceFamilyId':f'ocr-synthetic:{index:03d}',
                                'split':'development' if index in development else 'final','path':path.relative_to(output).as_posix(),
                                'sha256':digest,'width':width,'height':height,'transformation':kind,'realOrSynthetic':'synthetic_known_text',
                                'language':'zh_en' if index>=25 else 'zh','groundTruthLines':truth,'groundTruthText':'\n'.join(row['text'] for row in truth),
                                'truthOrigin':'known_rendered_strings_not_human_transcription','cerEligible':True,'humanVerified':False})
        finally:image.close()
    for index,row in enumerate(real):
        path=output/'real'/f'{index:03d}.img';shutil.copyfile(args.images/row['path'],path);digest=sha(path)
        if digest!=row['sha256']:raise ValueError('Real image changed')
        hashes[path.relative_to(output).as_posix()]=digest
        samples.append({'sampleId':f'ocr-real:{index:03d}','sourceFamilyId':row['imageFamilyId'],'sourceImageId':row['imageId'],
                        'split':'runtime_only','parentImageSplit':'development','path':path.relative_to(output).as_posix(),'sha256':digest,
                        'width':row['width'],'height':row['height'],'realOrSynthetic':'real_public_campus_image','groundTruthLines':None,
                        'groundTruthText':None,'truthOrigin':'no_independent_transcription','cerEligible':False,'humanVerified':False,
                        'institutionName':row['institutionName'],'articleUrl':row['articleUrl'],'visualTextDensity':'not_human_verified'})
    (output/'samples.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in samples),encoding='utf-8')
    result={'state':'OCR_MATERIALS_FROZEN_NOT_EVALUATED','samples':len(samples),'knownTextSyntheticQueries':200,'syntheticOriginalFamilies':50,
            'realRuntimeImages':50,'realTranscriptionsAvailable':0,'splitCounts':dict(Counter(row['split'] for row in samples)),
            'modelInferenceStarted':False,'qualityAccepted':False,'productActivated':False,'scope':protocol['scope']}
    (output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8');hashes.update({name:sha(output/name) for name in ['protocol.json','samples.jsonl','manifest.json']})
    (output/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8');(output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
