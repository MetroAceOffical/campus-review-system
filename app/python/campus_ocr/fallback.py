"""Optional OCR recovery primitives; the existing ocr-v1 service remains unchanged."""
import hashlib
import math
from pathlib import Path
import time

import numpy as np
from campus_ocr.recognizer import normalize_result
from campus_shared.contracts import digest_json

POLICY={'baselineLongEdge':960,'fallbackLongEdge':1600,'smallProcessedLineHeight':14.,
        'lowConfidenceThreshold':.8,'lowConfidenceFraction':.25,'tileLongEdgeTrigger':2000,
        'tileSize':1024,'tileOverlap':128,'maxTiles':9,'lineIouThreshold':.6}
ALGORITHM_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def fallback_configuration(baseline,policy=None):
    import cv2
    import PIL
    policy={**POLICY,**(policy or {})}
    config={'schemaVersion':'ocr-v2','baselineConfigId':baseline['configId'],'modelFiles':baseline['modelFiles'],
            'device':'cpu','policy':policy,'algorithmSha256':ALGORITHM_SHA256,'software':{'opencv':cv2.__version__,'Pillow':PIL.__version__,'numpy':np.__version__},
            'inputDecoder':'Content-based OpenCV IMREAD_COLOR; Pillow EXIF/RGB fallback if codec unavailable; first frame only.',
            'coordinatePolicy':'Decoded original image pixels, including decoder EXIF orientation; tile polygons translated into that same frame.'}
    config['featureSpaceId']='ocr-'+digest_json(config)
    config['configId']='ocr-'+digest_json(config);return config


def decoder_input(path):
    import cv2
    from PIL import Image,ImageOps
    payload=Path(path).read_bytes()
    if not payload or len(payload)>10*1024*1024:raise ValueError('OCR image byte budget exceeded or empty')
    with Image.open(path) as original:
        if original.width*original.height>20_000_000:raise ValueError('OCR image pixel budget exceeded')
        decoded=cv2.imdecode(np.frombuffer(payload,dtype=np.uint8),cv2.IMREAD_COLOR)
        if decoded is None:
            oriented=ImageOps.exif_transpose(original).convert('RGB')
            try:decoded=cv2.cvtColor(np.asarray(oriented),cv2.COLOR_RGB2BGR)
            finally:oriented.close()
    return decoded


def fallback_reasons(result,width,height,processed_limit=960,policy=None):
    policy={**POLICY,**(policy or {})};lines=result['recognitionLines'];reasons=[]
    if not result.get('combinedText','').strip():reasons.append('EMPTY_OCR')
    if lines:
        heights=[max(point[1] for point in line['polygon'])-min(point[1] for point in line['polygon']) for line in lines]
        scale=min(1.,processed_limit/max(width,height))
        if float(np.median(heights))*scale<policy['smallProcessedLineHeight']:reasons.append('SMALL_TEXT')
        if sum(line['confidence']<policy['lowConfidenceThreshold'] for line in lines)/len(lines)>=policy['lowConfidenceFraction']:reasons.append('LOW_CONFIDENCE')
    return reasons


def plan_tiles(width,height,tile_size=1024,overlap=128,max_tiles=9):
    if min(width,height,tile_size,max_tiles)<1 or not 0<=overlap<tile_size:raise ValueError('Invalid tile dimensions or budget')
    def starts(length):
        values=list(range(0,max(1,length-tile_size+1),tile_size-overlap));last=max(0,length-tile_size)
        if values[-1]!=last:values.append(last)
        return values
    tiles=[[x,y,min(width,x+tile_size),min(height,y+tile_size)] for y in starts(height) for x in starts(width)]
    total=len(tiles)
    if total>max_tiles:tiles=[tiles[int(index)] for index in np.linspace(0,total-1,max_tiles,dtype=int)]
    return {'tiles':tiles,'totalTiles':total,'coverageStatus':'PARTIAL' if total>len(tiles) else 'COMPLETE'}


def map_tile_result(raw,width,height,x,y):
    return normalize_result(raw,width,height,{'scaleX':1.,'scaleY':1.,'offsetX':-float(x),'offsetY':-float(y)})


def _polygon_overlap(left,right):
    import cv2
    a=cv2.convexHull(np.asarray(left,dtype=np.float32));b=cv2.convexHull(np.asarray(right,dtype=np.float32))
    aa,bb=float(cv2.contourArea(a)),float(cv2.contourArea(b))
    intersection=float(cv2.intersectConvexConvex(a,b)[0]) if aa>0 and bb>0 else 0.
    return intersection/max(1e-9,aa+bb-intersection),intersection/max(1e-9,min(aa,bb))


def merge_lines(lines,policy=None):
    policy={**POLICY,**(policy or {})};merged=[];conflicts=[]
    for line in sorted(lines,key=lambda value:(-value['confidence'],value.get('stage',''),value['text'])):
        candidate={**line,'observedInStages':[line.get('stage','unknown')]};text=''.join(line['text'].split());duplicate=False
        for previous in merged:
            old=''.join(previous['text'].split());iou,contained=_polygon_overlap(line['polygon'],previous['polygon'])
            contains_text=bool(text and old and (text in old or old in text))
            if iou<policy['lineIouThreshold'] and not (contained>=.8 and contains_text):continue
            previous['observedInStages']=sorted(set(previous['observedInStages']+candidate['observedInStages']));duplicate=True
            if old!=text:
                conflicts.append({'retained':previous['text'],'alternative':line['text'],'polygon':line['polygon'],'stage':line.get('stage')})
                # A tile can contain a shorter fragment of a full line; prefer the full text
                # only when it is geometrically contained and not materially less confident.
                if old in text and len(text)>len(old) and line['confidence']>=previous['confidence']-.1:
                    stages=previous['observedInStages'];previous.update(candidate);previous['observedInStages']=stages
            break
        if not duplicate:merged.append(candidate)
    # Group near-horizontal rows, then order by x. This is a stated heuristic,
    # not a claim to recover every multi-column or vertical reading order.
    pending=sorted(merged,key=lambda value:(min(point[1] for point in value['polygon']),min(point[0] for point in value['polygon'])))
    rows=[]
    for line in pending:
        ymin=min(point[1] for point in line['polygon']);ymax=max(point[1] for point in line['polygon']);center=(ymin+ymax)/2
        if rows and abs(center-rows[-1]['center'])<=.4*min(ymax-ymin,rows[-1]['height']):rows[-1]['lines'].append(line)
        else:rows.append({'center':center,'height':ymax-ymin,'lines':[line]})
    ordered=[line for row in rows for line in sorted(row['lines'],key=lambda value:min(point[0] for point in value['polygon']))]
    for number,line in enumerate(ordered,1):line['lineId']='line-'+str(number)
    return {'lines':ordered,'conflicts':conflicts,'readingOrderPolicy':'cluster-near-horizontal-rows-then-left-to-right'}


def recognize_adaptive(pipeline,path,baseline_config,policy=None):
    from PIL import Image
    import cv2
    policy={**POLICY,**(policy or {})};started=time.perf_counter();steps=[]
    source_input=decoder_input(path);height,width=source_input.shape[:2]
    with Image.open(path) as original:multiframe=getattr(original,'n_frames',1)>1
    def predict(value,limit,stage,tile=None):
        tick=time.perf_counter();outputs=list(pipeline.predict(value,text_det_limit_side_len=limit,text_det_limit_type='max'))
        if len(outputs)!=1:raise ValueError('OCR must return one result per processing step')
        raw=outputs[0].json['res']
        result=map_tile_result(raw,width,height,tile[0],tile[1]) if tile else normalize_result(raw,width,height,low_threshold=policy['lowConfidenceThreshold'])
        for line in result['recognitionLines']:line['stage']=stage
        steps.append({'stage':stage,'detectionLongEdge':limit,'tile':tile,'elapsedMs':(time.perf_counter()-tick)*1000,
                      'result':result,'rawRecognition':{'rec_texts':list(raw.get('rec_texts',[])),
                      'rec_scores':[float(value) for value in raw.get('rec_scores',[])],
                      'rec_polys':[[[float(x),float(y)] for x,y in polygon] for polygon in raw.get('rec_polys',[])]}})
        return result
    baseline=predict(source_input,policy['baselineLongEdge'],'mobile960');baseline_elapsed=(time.perf_counter()-started)*1000
    reasons=fallback_reasons(baseline,width,height,policy['baselineLongEdge'],policy);all_lines=list(baseline['recognitionLines']);flags=['FIRST_FRAME_ONLY'] if multiframe else [];coverage='COMPLETE'
    if reasons:
        try:
            high=predict(source_input,policy['fallbackLongEdge'],'mobile1600');all_lines.extend(high['recognitionLines'])
            still_low=fallback_reasons(high,width,height,policy['fallbackLongEdge'],policy)
            if still_low and max(width,height)>policy['tileLongEdgeTrigger']:
                plan=plan_tiles(width,height,policy['tileSize'],policy['tileOverlap'],policy['maxTiles']);coverage=plan['coverageStatus']
                for number,tile in enumerate(plan['tiles'],1):
                    left,top,right,bottom=tile;tile_input=source_input[top:bottom,left:right].copy()
                    result=predict(tile_input,policy['tileSize'],'tile-'+str(number),tile);all_lines.extend(result['recognitionLines'])
                if coverage=='PARTIAL':flags.append('TILE_BUDGET_EXCEEDED')
        except Exception as error:
            coverage='PARTIAL';flags.append('FALLBACK_FAILED');steps.append({'stage':'fallback-failure','error':type(error).__name__+': '+str(error)})
    if reasons:
        merged=merge_lines(all_lines,policy);lines=merged['lines'];conflicts=merged['conflicts']
    else:lines=baseline['recognitionLines'];conflicts=[]
    combined='\n'.join(line['text'] for line in lines);low=[line['lineId'] for line in lines if line['confidence']<policy['lowConfidenceThreshold']]
    if not combined.strip():flags.append('EMPTY_OCR')
    if low:flags.append('LOW_CONFIDENCE')
    if conflicts:flags.append('OCR_REGION_DISAGREEMENT')
    result={'status':'COMPLETED','ocrStatus':'COMPLETED' if combined.strip() else 'EMPTY','recognitionLines':lines,'combinedText':combined,
            'lowConfidenceLineIds':low,'qualityFlags':sorted(set(['COVERAGE_UNVERIFIED']+flags)),'originalWidth':width,'originalHeight':height,
            'coordinateSpace':'ORIGINAL_PIXELS','pixelFrame':'DECODED_ORIGINAL_PIXELS_EXIF_APPLIED','textSearchStatus':'NOT_RUN','noReuseClaim':False,'fallbackUsed':bool(reasons),'fallbackReasons':reasons,
            'processingCoverageStatus':coverage,'processingStrategy':[step['stage'] for step in steps],
            'conflictingOcrAlternatives':conflicts,'actualConfig':fallback_configuration(baseline_config,policy),'elapsedMs':(time.perf_counter()-started)*1000}
    return {'baseline':baseline,'baselineElapsedMs':baseline_elapsed,'adaptive':result,'steps':steps}
