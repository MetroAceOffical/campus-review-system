import functools
import json
import math
import os
from pathlib import Path
import time
from campus_shared.contracts import ContractError,controlled_file,digest_json,file_sha256

ROOT=Path(__file__).resolve().parents[3]

def prepare_environment():
    cache=ROOT/'runtime/ocr-cache'
    for name in ('home','tmp','paddlex','hf','modelscope','paddle','xdg'):(cache/name).mkdir(parents=True,exist_ok=True)
    for key,name in {'USERPROFILE':'home','TEMP':'tmp','TMP':'tmp','PADDLE_PDX_CACHE_HOME':'paddlex','HF_HOME':'hf','MODELSCOPE_CACHE':'modelscope','PADDLE_HOME':'paddle','XDG_CACHE_HOME':'xdg'}.items():os.environ[key]=str(cache/name)
    os.environ.update({'PYTHONUTF8':'1','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','CUDA_VISIBLE_DEVICES':'-1',
                       'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK':'True','DISABLE_MODEL_SOURCE_CHECK':'True','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'})

def configuration():
    model_root=ROOT/'validation/remaining/vision/models'
    manifest=json.loads((model_root/'manifest.json').read_text(encoding='utf-8'))
    hashes={}
    for item in manifest['extracted_files']:
        original=Path(item['path']);path=model_root/original.parent.name/original.name
        actual=file_sha256(path)
        if actual!=item['sha256']:raise ContractError('MODEL_HASH_MISMATCH','OCR weight or model configuration changed')
        hashes[path.relative_to(model_root).as_posix()]=actual
    config={'schemaVersion':'ocr-v1','model':'PP-OCRv5-mobile','device':'cpu','cpuThreads':2,'mkldnn':False,
            'orientationClassification':False,'unwarping':False,'textlineOrientation':False,'detectionLimitSide':960,
            'detectionLimitType':'max','recognitionBatchSize':1,'recognitionScoreThreshold':0.0,'lowConfidenceThreshold':0.8,'modelFiles':hashes}
    config['featureSpaceId']='ocr-'+digest_json(config);config['configId']='ocr-'+digest_json(config)
    return config

@functools.lru_cache(maxsize=1)
def load_pipeline():
    prepare_environment();config=configuration()
    from paddleocr import PaddleOCR
    model_root=ROOT/'validation/remaining/vision/models'
    pipeline=PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det',text_recognition_model_name='PP-OCRv5_mobile_rec',
        text_detection_model_dir=str(model_root/'PP-OCRv5_mobile_det_infer'),text_recognition_model_dir=str(model_root/'PP-OCRv5_mobile_rec_infer'),
        use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,device='cpu',enable_hpi=False,enable_mkldnn=False,
        cpu_threads=2,text_recognition_batch_size=1,text_det_limit_side_len=960,text_det_limit_type='max',text_rec_score_thresh=0.0)
    return pipeline,config

def normalize_result(raw,width,height,transform=None,low_threshold=.8):
    if width<=0 or height<=0:raise ContractError('OCR_DIMENSIONS_INVALID','Invalid original image dimensions')
    transform=transform or {'scaleX':1.,'scaleY':1.,'offsetX':0.,'offsetY':0.}
    if any(not math.isfinite(float(transform[key])) for key in ('scaleX','scaleY','offsetX','offsetY')) or transform['scaleX']<=0 or transform['scaleY']<=0:
        raise ContractError('OCR_TRANSFORM_INVALID','Invalid processing transform')
    texts=raw.get('rec_texts',[]);scores=raw.get('rec_scores',[]);polygons=raw.get('rec_polys',[])
    if not len(texts)==len(scores)==len(polygons):raise ContractError('OCR_LINE_MISMATCH','OCR text, confidence and polygon counts differ')
    lines=[];low=[]
    for i,(text,score,polygon) in enumerate(zip(texts,scores,polygons),1):
        score=float(score)
        if not isinstance(text,str) or not math.isfinite(score) or not 0<=score<=1 or len(polygon)!=4:raise ContractError('OCR_OUTPUT_INVALID','Invalid OCR recognition line')
        points=[]
        for point in polygon:
            if len(point)!=2:raise ContractError('OCR_COORDINATES_INVALID','Invalid OCR polygon')
            x=(float(point[0])-transform['offsetX'])/transform['scaleX'];y=(float(point[1])-transform['offsetY'])/transform['scaleY']
            if not math.isfinite(x) or not math.isfinite(y) or not 0<=x<=width or not 0<=y<=height:raise ContractError('OCR_COORDINATES_INVALID','OCR polygon lies outside original image')
            points.append([x,y])
        line_id='line-'+str(i);lines.append({'lineId':line_id,'text':text,'confidence':score,'polygon':points})
        if score<low_threshold:low.append(line_id)
    combined='\n'.join(line['text'] for line in lines)
    flags=['COVERAGE_UNVERIFIED']
    if not combined.strip():flags.append('EMPTY_OCR')
    if low:flags.append('LOW_CONFIDENCE')
    return {'status':'COMPLETED','ocrStatus':'COMPLETED' if combined.strip() else 'EMPTY','recognitionLines':lines,'lowConfidenceLineIds':low,
            'combinedText':combined,'originalWidth':width,'originalHeight':height,'processingTransform':transform,
            'coordinateSpace':'ORIGINAL_PIXELS','textSearchStatus':'NOT_RUN','noReuseClaim':False,'qualityFlags':flags}

def recognize(image,config=None):
    start=time.perf_counter();pipeline,actual=load_pipeline()
    if config is not None and config.get('configId')!=actual['configId']:raise ContractError('CONFIG_UNAVAILABLE','Requested OCR configuration is unavailable')
    if image.get('configId',actual['configId'])!=actual['configId']:raise ContractError('CONFIG_UNAVAILABLE','Requested OCR configuration is unavailable')
    for key in ('taskId','attemptId','fileId'):
        if not isinstance(image.get(key),str) or not image[key]:raise ContractError('INVALID_IDENTITY','Missing '+key)
    path=controlled_file(image.get('path',''),image.get('fileSha256'),[ROOT/'runtime',ROOT/'validation'])
    from PIL import Image
    with Image.open(path) as original:width,height=original.size
    outputs=list(pipeline.predict(str(path)))
    if len(outputs)!=1:raise ContractError('OCR_OUTPUT_INVALID','OCR must return exactly one result for one image')
    raw=outputs[0].json['res']
    result=normalize_result(raw,width,height,low_threshold=actual['lowConfidenceThreshold'])
    result.update({key:image[key] for key in ('taskId','attemptId','fileId')})
    result.update(fileSha256=image['fileSha256'],actualConfig=actual,elapsedMs=(time.perf_counter()-start)*1000)
    return result
