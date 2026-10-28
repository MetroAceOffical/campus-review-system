"""Read-only loading of an explicitly selected merged correspondence export.

This module has no default-profile registration and does not import PEFT.
"""
import contextlib
import hashlib
import json
import math
import re
from pathlib import Path


def _sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_export(folder,expected_export_id=None):
    folder=Path(folder).resolve()
    if not (folder/'READY').is_file() or not (folder/'export-manifest.json').is_file():raise ValueError('Merged model export is not READY')
    ready=json.loads((folder/'READY').read_text(encoding='utf-8'))
    if not isinstance(ready,dict) or ready.get('export-manifest.json')!=_sha(folder/'export-manifest.json'):raise ValueError('Export manifest changed')
    manifest=json.loads((folder/'export-manifest.json').read_text(encoding='utf-8'))
    export_id=manifest.get('exportId')
    identity={key:value for key,value in manifest.items() if key!='exportId'}
    expected='m3-merged-'+hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if export_id!=expected or expected_export_id is not None and export_id!=expected_export_id:raise ValueError('Merged export identity differs from selected model')
    if manifest.get('schemaVersion')!='merged-correspondence-v1' or manifest.get('taskType')!='CONTENT_CORRESPONDENCE' or manifest.get('inferenceRuntime')!='TRANSFORMERS_NO_PEFT' or manifest.get('scoreType')!='CONTENT_CORRESPONDENCE_SCORE':raise ValueError('Require plain task-correspondence weights')
    comparison=manifest.get('comparison',{})
    if comparison.get('mergeVerified') is not True or comparison.get('reloadVerified') is not True or comparison.get('precision')!='FP32_CPU':raise ValueError('Merge and reload equivalence are not verified')
    files=manifest.get('files',{})
    if not isinstance(files,dict) or not files or ready!={**files,'export-manifest.json':_sha(folder/'export-manifest.json')}:raise ValueError('Export components differ from READY')
    for name,checksum in files.items():
        path=folder/name
        if not name.startswith('model/') or not path.resolve().is_relative_to(folder/'model') or not re.fullmatch('[0-9a-f]{64}',checksum):raise ValueError('Invalid export component path/hash')
        if not path.is_file() or _sha(path)!=checksum:raise ValueError('Merged export component changed: '+name)
    if 'model/config.json' not in files or 'model/tokenizer.json' not in files or not any(name.endswith('.safetensors') for name in files):raise ValueError('Export lacks model/tokenizer components')
    return manifest


def configuration_for(folder,manifest,*,device='cuda',precision='BF16'):
    """Describe an already verified export without allocating neural weights."""
    configuration={'schemaVersion':'task-model-v1','exportId':manifest['exportId'],
                   'exportManifestSha256':_sha(Path(folder)/'export-manifest.json'),'device':device,'precision':precision,
                   'parameterPrecision':'FP32','maxJointTokens':512,'scoreType':'CONTENT_CORRESPONDENCE_SCORE',
                   'algorithmSha256':_sha(Path(__file__))}
    configuration['configId']='task-'+hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return configuration


def load_correspondence_model(folder,*,expected_export_id,device='cuda',precision='BF16'):
    import torch
    from transformers import AutoModelForSequenceClassification,AutoTokenizer
    if not isinstance(expected_export_id,str) or not expected_export_id:raise ValueError('Select a fixed export identity')
    if device not in {'cuda','cpu'} or precision not in {'FP32','BF16'} or device=='cpu' and precision!='FP32':raise ValueError('Unsupported task-model execution policy')
    if device=='cuda' and (not torch.cuda.is_available() or precision=='BF16' and not torch.cuda.is_bf16_supported()):raise RuntimeError('Requested CUDA policy is unavailable; do not silently change environments')
    folder=Path(folder);manifest=verify_export(folder,expected_export_id)
    tokenizer=AutoTokenizer.from_pretrained(folder/'model',local_files_only=True,trust_remote_code=False,use_fast=True)
    model=AutoModelForSequenceClassification.from_pretrained(folder/'model',local_files_only=True,trust_remote_code=False).float().to(device).eval()
    if model.config.num_labels!=1:raise ValueError('Correspondence model must have one task logit')
    configuration=configuration_for(folder,manifest,device=device,precision=precision)
    def score_pair(pair):
        query,source=pair['queryText'],pair['sourceText']
        if not isinstance(query,str) or not isinstance(source,str) or not query.strip() or not source.strip():raise ValueError('Require nonempty original query/source slices')
        tokens=tokenizer(query,source,truncation=False,return_tensors='pt')
        if tokens['input_ids'].shape[1]>configuration['maxJointTokens']:raise ValueError('Task pair exceeds joint512; split with original offsets')
        tokens={key:value.to(device) for key,value in tokens.items()}
        with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16) if precision=='BF16' else contextlib.nullcontext():
            logits=model(**tokens).logits.float()
        if logits.numel()!=1 or not torch.isfinite(logits).all():raise ValueError('Task model returned invalid logits')
        score=float(torch.sigmoid(logits).item())
        if not math.isfinite(score):raise ValueError('Task model returned nonfinite score')
        return score
    return {'model':model,'tokenizer':tokenizer,'configuration':configuration,'scorePair':score_pair}
