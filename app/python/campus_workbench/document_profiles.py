"""Pin deployed document-check algorithms/models to an evaluated profile."""
import inspect
import importlib.metadata
import json
import re
from pathlib import Path
from . import inspection
from campus_shared.contracts import digest_json,file_sha256


def engine_algorithm(name,module=inspection):
    functions=('grammar','_grammar_pipeline','_corrected_edits','protected','check_files') if name=='grammar' else ('image_text','fields','compare_fields','check_files')
    return digest_json({key:inspect.getsource(getattr(module,key)) for key in functions})


def configuration(evaluations):
    if not isinstance(evaluations,dict) or set(evaluations)!={'grammar','imageText'} or any(not re.fullmatch('[0-9a-f]{64}',str(v)) for v in evaluations.values()):
        raise ValueError('文稿模型缺少完整评价身份')
    value=dict(schemaVersion='document-models-v1',algorithmSha256=file_sha256(inspection.__file__),
        software={name:importlib.metadata.version(name) for name in ('torch','transformers','tokenizers','numpy','Pillow')},
        adapterSha256=file_sha256(Path(__file__)),coordinatorSha256=file_sha256(inspection.ROOT/'app/python/campus_shared/document_compute.py'),engineAlgorithms={name:engine_algorithm(name) for name in ('grammar','imageText')},
        devicePreference='cuda',gpuMinimumGiB={'GRAMMAR_MODEL':6.5,'IMAGE_TEXT':2.},
        ocrConfiguration=json.loads((inspection.ROOT/'app/config/frozen-ocr-v2.json').read_text(encoding='utf-8')),
        models={name:dict(name='Qwen2.5-3B-Instruct' if name=='grammar' else 'Chinese-CLIP ViT-B/16',revision=path.name,acquisitionSha256=file_sha256(path/'acquisition.json'))
                for name,path in [('grammar',inspection.QWEN),('imageText',inspection.CLIP)]},
        evaluations=evaluations,finalQualityAccepted=False)
    return value|{'profileId':'document-'+digest_json(value)}


def validate(value):
    if not isinstance(value,dict) or value.get('schemaVersion')!='document-models-v1':raise ValueError('文稿模型配置无效')
    unsigned={k:v for k,v in value.items() if k!='profileId'}
    if value.get('profileId')!='document-'+digest_json(unsigned):raise ValueError('文稿模型配置身份不一致')
    if configuration(value.get('evaluations'))!=value:raise ValueError('文稿模型配置已更新，请重新检查')
    return value


def device(kind,profile):
    import torch
    validate(profile)
    required=profile['gpuMinimumGiB'][kind]*1024**3
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<required:
        raise BlockingIOError('等待文稿模型显存资源')
    return 'cuda'
