"""Export a verified completed M3 adapter as a plain Transformers CPU-FP32 model.

No production configuration is changed. The production environment needs no
PEFT installation; CUDA precision and product quality remain separate checks.
"""
import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from construct_correspondence import verify_ready
from corpus import read_jsonl

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def completed_run(run):
    run=Path(run)
    config=json.loads((run/'run.json').read_text(encoding='utf-8'))
    status=json.loads((run/'status.json').read_text(encoding='utf-8'))
    if config.get('taskType')!='CONTENT_CORRESPONDENCE' or config.get('pairCount',0)<20000 or config.get('epochs')!=2:raise ValueError('Require formal correspondence training identity')
    if status.get('state')!='CORRESPONDENCE_TRAINING_COMPLETE' or status.get('reloadVerified') is not True or status.get('epochs')!=2:raise ValueError('Training and final adapter reload are not verified complete')
    name=status.get('checkpoint','')
    if not re.fullmatch(r'checkpoint-\d{6}',name):raise ValueError('Invalid final checkpoint identity')
    checkpoint=run/name;hashes=verify_ready(checkpoint)
    if not hashes or 'state.pt' not in hashes:raise ValueError('Checkpoint lacks full resumable state')
    return {'config':config,'status':status,'checkpoint':checkpoint,'checkpointHashes':hashes}


def load_export_base(folder,training_precision):
    import torch
    from transformers import AutoModelForSequenceClassification
    if training_precision!='BF16':raise ValueError('Unsupported frozen training backbone precision')
    # Preserve the rounded frozen weights actually used during training, then
    # upcast for CPU merging; raw FP32 parent weights are a different backbone.
    return AutoModelForSequenceClassification.from_pretrained(folder,torch_dtype=torch.bfloat16,
               local_files_only=True,trust_remote_code=False).to(device='cpu',dtype=torch.float32)


def merge_for_inference(model,tokenizer,inputs,output):
    import torch
    from transformers import AutoModelForSequenceClassification
    output=Path(output)
    if output.exists():raise ValueError('Use a new merge output directory')
    if model.config.num_labels!=1 or not hasattr(model,'merge_and_unload'):raise ValueError('Require the task-specific single-output adapter model')
    model=model.to(device='cpu',dtype=torch.float32).eval()
    inputs={key:value.to('cpu') for key,value in inputs.items()}
    with torch.inference_mode():expected=model(**inputs).logits.float()
    if not torch.isfinite(expected).all():raise ValueError('Nonfinite adapter probe')
    merged=model.merge_and_unload(safe_merge=True).eval()
    if any('lora_' in name or 'modules_to_save' in name for name,_ in merged.named_parameters()):raise ValueError('Adapter modules remain in plain export')
    with torch.inference_mode():actual=merged(**inputs).logits.float()
    if not torch.isfinite(actual).all() or not torch.allclose(expected,actual,atol=1e-5,rtol=1e-5):raise ValueError('FP32 merge changed task logits')
    merged.save_pretrained(output,safe_serialization=True);tokenizer.save_pretrained(output)
    restored=AutoModelForSequenceClassification.from_pretrained(output,local_files_only=True,trust_remote_code=False).to('cpu').eval()
    with torch.inference_mode():reloaded=restored(**inputs).logits.float()
    if not torch.isfinite(reloaded).all() or not torch.allclose(actual,reloaded,atol=1e-6,rtol=1e-6):raise ValueError('Plain serialized model reload changed logits')
    return {'mergeVerified':True,'reloadVerified':True,'precision':'FP32_CPU','probeCount':int(expected.shape[0]),
            'maximumMergeLogitDifference':float((expected-actual).abs().max()),
            'maximumReloadLogitDifference':float((actual-reloaded).abs().max()),
            'probeLogits':reloaded.tolist(),'scope':'CPU FP32 adapter-to-merged and serialized reload equivalence; not CUDA BF16 or quality acceptance.'}


def freeze_export(folder,provenance,comparison):
    folder=Path(folder)
    if (folder/'READY').exists() or (folder/'export-manifest.json').exists():raise ValueError('Export version already sealed')
    files={path.relative_to(folder).as_posix():sha(path) for path in sorted((folder/'model').rglob('*')) if path.is_file()}
    if not files or comparison.get('mergeVerified') is not True or comparison.get('reloadVerified') is not True:raise ValueError('Model export comparison not verified')
    manifest={**provenance,'schemaVersion':'merged-correspondence-v1','taskType':'CONTENT_CORRESPONDENCE',
              'scoreType':'CONTENT_CORRESPONDENCE_SCORE','inferenceRuntime':'TRANSFORMERS_NO_PEFT',
              'exportAlgorithmSha256':sha(Path(__file__)),
              'software':{name:importlib.metadata.version(name) for name in ['torch','transformers','peft','safetensors']},
              'comparison':comparison,'files':dict(files),'mergePrecision':'FP32',
              'cudaPrecisionVerified':False,'productActivated':False,'qualityAccepted':False}
    manifest['exportId']='m3-merged-'+hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (folder/'export-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    files['export-manifest.json']=sha(folder/'export-manifest.json')
    (folder/'READY').write_text(json.dumps(files,indent=2),encoding='utf-8')
    verify_ready(folder)
    return manifest


def main():
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True);parser.add_argument('--base-manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/models/final').resolve()):raise ValueError('Use a new project model export version')
    temporary=output.with_name(output.name+'.partial')
    if output.exists() or temporary.exists():raise ValueError('Do not overwrite an exported or partial model version')
    verified=completed_run(args.run);config=verified['config']
    data_hashes=verify_ready(args.data)
    if data_hashes.get('pairs.jsonl')!=config['pairsSha256'] or sha(args.base_manifest)!=config['baseManifestSha256']:raise ValueError('Training data/base identity differs from completed run')
    base_manifest=json.loads(args.base_manifest.read_text(encoding='utf-8'))
    for item in base_manifest['files']:
        if sha(args.model/item['file'])!=item['sha256']:raise ValueError('Base model changed')
    probes={};count=0
    for row in read_jsonl(args.data/'pairs.jsonl'):
        count+=1
        if row['target'] not in probes:probes[row['target']]=row
    if count!=config['pairCount'] or set(probes)!={0,1}:raise ValueError('Completed run pair/class identity differs')
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    selected=[probes[key] for key in sorted(probes)]
    tokens=tokenizer([row['query'] for row in selected],[row['source'] for row in selected],padding=True,truncation=False,return_tensors='pt')
    if tokens['input_ids'].shape[1]>512:raise ValueError('Export probe exceeds task budget')
    base=load_export_base(args.model,config['frozenBackbonePrecision'])
    model=PeftModel.from_pretrained(base,verified['checkpoint']/'adapter').eval()
    temporary.mkdir(parents=True,exist_ok=False)
    comparison=merge_for_inference(model,tokenizer,tokens,temporary/'model')
    provenance={'baseRevision':base_manifest['revision'],'baseManifestSha256':config['baseManifestSha256'],
              'trainingRunSha256':sha(args.run/'run.json'),'trainingStatusSha256':sha(args.run/'status.json'),
              'pairsSha256':config['pairsSha256'],'checkpoint':verified['checkpoint'].name,
              'checkpointHashes':verified['checkpointHashes'],'probePairIds':[row['pairId'] for row in selected],
              'frozenBackbonePrecision':config['frozenBackbonePrecision']}
    manifest=freeze_export(temporary,provenance,comparison)
    temporary.replace(output)
    print(json.dumps({'state':'MERGED_EXPORT_VERIFIED','exportId':manifest['exportId'],
                      'productActivated':False,'qualityAccepted':False}),flush=True)


if __name__=='__main__':main()
