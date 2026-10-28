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

def configurations(*, legacy=False):
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
    if not legacy:
        text = {**text, 'schemaVersion':'text-v2', 'method':'sentence-aligned-20261024',
                'baseConfigId':text['configId'],
                'semanticDecision':'separate-evidence-hint; literal acceptance and ranking unchanged',
                'semanticAlgorithmSha256':file_sha256(ROOT/'app/python/campus_detection/semantic.py'),
                'semanticPolicy':{'scoreThreshold':.5,'lexicalFloor':.25,'minimumPairs':2,
                                  'minimumCharacters':64,'maxSources':3,'maxQueryUnits':48,
                                  'maxPairs':288,'alignmentMinimum':.08,'candidatesPerUnit':2,'unitTokens':60}}
        # Existing TF-IDF vectors are unchanged; only the inference policy gets a new ID.
        text.pop('configId')
        text['configId']='text-'+digest_json(text)
    image={'schemaVersion':'image-v1','model':'facebook/dinov2-small','revision':'ed25f3a31f01632728cabb09d1542f84ab7b0056',
           'weightSha256':'ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1',
           'processorSha256':file_sha256(ROOT/'validation/remaining/image/models/dinov2-small/preprocessor_config.json'),
           'precision':'FP32','processor':'slow-PIL','feature':'L2-normalized-CLS','dimensions':384,
           'threshold':read(ROOT/'validation/remaining/image/evaluation/selection.json')['thresholds']['dino']}
    image['featureSpaceId']='dino-'+digest_json({key:value for key,value in image.items() if key!='threshold'})
    image['configId']='image-'+digest_json(image)
    return text,image

def load_image_models(device='cuda',enhanced=False):
    from transformers import AutoImageProcessor,AutoModel
    _,image=configurations();source=ROOT/'validation/remaining/image/models/dinov2-small'
    if file_sha256(source/'model.safetensors')!=image['weightSha256']:raise ContractError('MODEL_HASH_MISMATCH','DINO weight hash changed')
    processor=AutoImageProcessor.from_pretrained(source,local_files_only=True,use_fast=False)
    dino=AutoModel.from_pretrained(source,local_files_only=True).eval().to(device)
    configs={image['configId']:image}
    if enhanced:
        from .image_enhanced import configuration
        image=configuration(image);configs[image['configId']]=image
    return {'imageConfig':image,'imageConfigs':configs,'dino':dino,'processor':processor,'allowedRoots':[ROOT/'runtime',ROOT/'validation']}

@functools.lru_cache(maxsize=1)
def load_models(enhanced_images=False):
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
    import torch
    from transformers import AutoImageProcessor,AutoModel
    torch.set_num_threads(4)
    text,image=configurations()
    old_text,_=configurations(legacy=True)
    # Only the read-only frozen loader/predictor are imported. No experiment runner is executed.
    sys.path.insert(0,str(ROOT/'validation/text'))
    import round2
    choice,bert,_,tokenizer=round2.load_selected('bert')
    tokenizer.model_max_length=10**8
    image_models=load_image_models(enhanced=enhanced_images)
    def predict(pairs):
        if not pairs:return []
        scores,_=round2.predict_rows('bert',bert,pairs,tokenizer=tokenizer,batch=8)
        return scores.tolist()
    return {'textConfig':text,'legacyTextConfig':old_text,'textConfigs':{text['configId']:text,old_text['configId']:old_text},
            **image_models,'tokenizer':tokenizer,'bert':bert,'predictBert':predict,
            'loadedWeights':{'bert':text['weightSha256'],'dino':image['weightSha256']}}
