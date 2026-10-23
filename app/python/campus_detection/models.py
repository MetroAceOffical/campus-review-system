import functools
import importlib.util
import json
import os
from pathlib import Path
import sys
from campus_shared.contracts import digest_json,file_sha256,ContractError

ROOT=Path(__file__).resolve().parents[3]

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

@functools.lru_cache(maxsize=1)
def frozen_text_helpers():
    spec=importlib.util.spec_from_file_location('campus_frozen_text_helpers',ROOT/'validation/remaining/text/text_core.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def configurations():
    selection=read(ROOT/'validation/remaining/text/selection.json')
    lock=read(ROOT/'validation/text/round2/selection-lock.json')
    if selection['chunk']!={'tokens':48,'overlap':12} or selection['alpha']!=0:
        raise ContractError('CONFIG_UNAVAILABLE','Frozen text selection differs from reviewed method')
    text={'schemaVersion':'text-v1','method':'V1-A-20261022','chunk':selection['chunk'],'params':selection['params'],
          'semanticAlpha':0,'candidateK':10,'literalSearchMinimum':20,'semanticWindowsPerSource':2,
          'weightSha256':lock['artifact_sha256']['bert'],'selectionSha256':file_sha256(ROOT/'validation/remaining/text/selection.json'),
          'tokenizerSha256':file_sha256(ROOT/'validation/text/models/bert-base-chinese/tokenizer.json'),
          'templateGram':16,'templateRatio':0.8,'templateDocumentRatio':0.1,'bertPairMaxTokens':128,'bertPrecision':'bfloat16-autocast'}
    text['featureSpaceId']='text-'+digest_json(text)
    text['configId']='text-'+digest_json(text)
    image={'schemaVersion':'image-v1','model':'facebook/dinov2-small','revision':'ed25f3a31f01632728cabb09d1542f84ab7b0056',
           'weightSha256':'ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1',
           'processorSha256':file_sha256(ROOT/'validation/remaining/image/models/dinov2-small/preprocessor_config.json'),
           'precision':'FP32','processor':'slow-PIL','feature':'L2-normalized-CLS','dimensions':384,
           'threshold':read(ROOT/'validation/remaining/image/evaluation/selection.json')['thresholds']['dino']}
    image['featureSpaceId']='dino-'+digest_json({key:value for key,value in image.items() if key!='threshold'})
    image['configId']='image-'+digest_json(image)
    return text,image

@functools.lru_cache(maxsize=1)
def load_models():
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
    import torch
    from transformers import AutoImageProcessor,AutoModel
    torch.set_num_threads(4)
    text,image=configurations()
    # Only the read-only frozen loader/predictor are imported. No experiment runner is executed.
    sys.path.insert(0,str(ROOT/'validation/text'))
    import round2
    choice,bert,_,tokenizer=round2.load_selected('bert')
    tokenizer.model_max_length=10**8
    image_path=ROOT/'validation/remaining/image/models/dinov2-small'
    if file_sha256(image_path/'model.safetensors')!=image['weightSha256']:raise ContractError('MODEL_HASH_MISMATCH','DINO weight hash changed')
    processor=AutoImageProcessor.from_pretrained(image_path,local_files_only=True,use_fast=False)
    dino=AutoModel.from_pretrained(image_path,local_files_only=True).eval().cuda()
    def predict(pairs):
        if not pairs:return []
        scores,_=round2.predict_rows('bert',bert,pairs,tokenizer=tokenizer,batch=8)
        return scores.tolist()
    return {'textConfig':text,'imageConfig':image,'tokenizer':tokenizer,'bert':bert,'predictBert':predict,
            'dino':dino,'processor':processor,'allowedRoots':[ROOT/'runtime',ROOT/'validation'],
            'loadedWeights':{'bert':text['weightSha256'],'dino':image['weightSha256']}}
