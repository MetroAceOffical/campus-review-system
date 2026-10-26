"""M3 content-correspondence LoRA training. Auxiliary relevance labels are rejected."""
import argparse
import gc
import hashlib
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from peft import LoraConfig,TaskType,get_peft_model,PeftModel
from transformers import AutoModelForSequenceClassification,AutoTokenizer,get_linear_schedule_with_warmup

from corpus import eligible_correspondence,read_jsonl,normalized
from negative_basis import assess_difference

ROOT=Path(__file__).resolve().parents[2]


def adapter_precision(model):
    for name,parameter in model.named_parameters():
        if parameter.requires_grad or 'lora_' in name or 'classifier.modules_to_save' in name:parameter.data=parameter.data.float()
    return model


def attach_adapter(base):
    matched=[name for name,module in base.named_modules() if isinstance(module,torch.nn.Linear) and name.rsplit('.',1)[-1] in {'query','value'}]
    if not matched:raise ValueError('No XLM-R query/value modules matched')
    model=get_peft_model(base,LoraConfig(task_type=TaskType.SEQ_CLS,r=16,lora_alpha=32,lora_dropout=.05,target_modules=['query','value'],modules_to_save=['classifier']))
    if not any(p.requires_grad for name,p in model.named_parameters() if 'lora_' in name):raise ValueError('LoRA parameters not trainable')
    if not any(p.requires_grad for name,p in model.named_parameters() if 'classifier' in name):raise ValueError('Classification head not trainable')
    return adapter_precision(model)


def correspondence_loss(logits,targets):
    targets=targets.float().reshape(-1)
    if not torch.all((targets==0)|(targets==1)):raise ValueError('Correspondence requires binary targets, not similarity/event scores')
    return F.binary_cross_entropy_with_logits(logits.float().reshape(-1),targets)


def validate_rows(rows,minimum=20000):
    if len(rows)<minimum:raise ValueError('Formal campus correspondence training requires a prepared shard of at least '+str(minimum)+' pairs; do not substitute a tiny pilot run')
    seen=set()
    for row in rows:
        if not eligible_correspondence(row) or row.get('split')!='train':raise ValueError('Unknown, auxiliary or non-training labels cannot enter correspondence BCE')
        if row.get('target') not in (0,1) or not row.get('sourceIds') or not row.get('sourceOffsets'):raise ValueError('Incomplete correspondence provenance')
        span=row['sourceOffsets']
        if span['start']<0 or span['end']-span['start']!=len(row['source']):raise ValueError('Source range does not match source window')
        key=tuple(sorted((normalized(row['query']),normalized(row['source']))))
        if key in seen:raise ValueError('Repeated or reversed text pair must not inflate training scale')
        seen.add(key)
        if row.get('labelOrigin')=='rule_inferred_noncorrespondence' and not assess_difference(row['positiveSource'],row['candidateSource'])['supported']:raise ValueError('Negative content-difference basis does not reproduce')
    counts=Counter(row['target'] for row in rows)
    if not rows or min(counts[0],counts[1])<len(rows)*.2:raise ValueError('Both supported classes must be represented')
    return counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--base-manifest',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT/'runtime/experiments').resolve()):raise ValueError('Use a new project experiment folder')
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'run.json').exists() and not args.resume:raise RuntimeError('Existing run requires explicit resume')
    input_hashes=json.loads((args.data/'READY').read_text(encoding='utf-8'))
    for name,expected in input_hashes.items():
        with (args.data/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('Training shard changed')
    base_manifest=json.loads(args.base_manifest.read_text(encoding='utf-8'))
    for item in base_manifest['files']:
        with (args.model/item['file']).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise ValueError('Parent model changed')
    rows=list(read_jsonl(args.data/'pairs.jsonl'))
    counts=validate_rows(rows)
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():raise RuntimeError('Configured BF16 CUDA unavailable')
    seed=20261026;random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed);torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    # Reject oversized windows instead of truncating the only corresponding fact.
    for row in rows:
        if len(tokenizer(row['query'],row['source'],truncation=False)['input_ids'])>512:raise ValueError('Prepared pair exceeds joint512; rebuild aligned windows')
    config={'taskType':'CONTENT_CORRESPONDENCE','seed':seed,'epochs':2,'microbatch':1,'effectivePairs':32,'maxJointTokens':512,
            'lora':{'r':16,'alpha':32,'dropout':.05,'targets':['query','value']},'adapterLearningRate':1e-4,'headLearningRate':5e-5,
            'frozenBackbonePrecision':'BF16','trainablePrecision':'FP32',
            'weightDecay':.01,'warmupRatio':.06,'classCounts':dict(counts),'pairCount':len(rows),'baseRevision':base_manifest['revision'],
            'baseManifestSha256':hashlib.sha256(args.base_manifest.read_bytes()).hexdigest(),'pairsSha256':input_hashes['pairs.jsonl']}
    config_sha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    (args.output/'run.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    base=AutoModelForSequenceClassification.from_pretrained(args.model,torch_dtype=torch.bfloat16,local_files_only=True,trust_remote_code=False)
    matched=[name for name,module in base.named_modules() if isinstance(module,torch.nn.Linear) and name.rsplit('.',1)[-1] in {'query','value'}]
    model=PeftModel.from_pretrained(base,args.resume/'adapter',is_trainable=True) if args.resume else attach_adapter(base)
    adapter_precision(model)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads();model.to('cuda').train()
    report={'matchedModules':matched,'trainableParameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
            'totalParameters':sum(p.numel() for p in model.parameters()),'trainableNames':[name for name,p in model.named_parameters() if p.requires_grad],
            'trainableParameterDtypes':dict(Counter(str(p.dtype) for p in model.parameters() if p.requires_grad))}
    (args.output/'adapter-injection.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({key:value for key,value in report.items() if key!='trainableNames'}),flush=True)
    adapter=[p for name,p in model.named_parameters() if p.requires_grad and 'classifier' not in name]
    head=[p for name,p in model.named_parameters() if p.requires_grad and 'classifier' in name]
    optimizer=torch.optim.AdamW([{'params':adapter,'lr':1e-4},{'params':head,'lr':5e-5}],weight_decay=.01)
    per_epoch=math.ceil(len(rows)/32);scheduler=get_linear_schedule_with_warmup(optimizer,math.ceil(per_epoch*2*.06),per_epoch*2)
    step,first_epoch,first_cursor=0,0,0
    if args.resume:
        state=torch.load(args.resume/'state.pt',map_location='cpu',weights_only=False)
        if state['configSha256']!=config_sha:raise ValueError('Resume identity changed')
        optimizer.load_state_dict(state['optimizer']);scheduler.load_state_dict(state['scheduler'])
        random.setstate(state['pythonRandom']);np.random.set_state(state['numpyRandom']);torch.set_rng_state(state['torchRandom']);torch.cuda.set_rng_state_all(state['cudaRandom'])
        step,first_epoch,first_cursor=state['step'],state['nextEpoch'],state['nextCursor']
        if first_epoch>=2:print(json.dumps({'state':'ALREADY_COMPLETED','step':step}));return
    witness=next(p for name,p in model.named_parameters() if 'lora_B' in name and p.requires_grad)
    head_witness=next(p for name,p in model.named_parameters() if 'classifier' in name and name.endswith('out_proj.weight') and p.requires_grad)
    def save(epoch,cursor):
        temporary=args.output/f'.checkpoint-{step:06d}.partial';temporary.mkdir(exist_ok=False)
        model.save_pretrained(temporary/'adapter');tokenizer.save_pretrained(temporary/'tokenizer')
        torch.save({'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),'step':step,'nextEpoch':epoch,'nextCursor':cursor,
                    'pythonRandom':random.getstate(),'numpyRandom':np.random.get_state(),'torchRandom':torch.get_rng_state(),'cudaRandom':torch.cuda.get_rng_state_all(),'configSha256':config_sha},temporary/'state.pt')
        hashes={}
        for path in temporary.rglob('*'):
            if path.is_file():
                with path.open('rb') as stream:hashes[path.relative_to(temporary).as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
        (temporary/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
        final=args.output/f'checkpoint-{step:06d}';temporary.replace(final);return final
    started=time.monotonic()
    with (args.output/'history.jsonl').open('a',encoding='utf-8') as log:
        for epoch in range(first_epoch,2):
            order=list(range(len(rows)));random.Random(seed+epoch).shuffle(order)
            for offset in range(first_cursor if epoch==first_epoch else 0,len(order),32):
                batch=[rows[index] for index in order[offset:offset+32]];optimizer.zero_grad(set_to_none=True)
                before=witness.detach().clone();before_head=head_witness.detach().clone();loss_sum=0
                for row in batch:
                    tokens=tokenizer(row['query'],row['source'],truncation=False,return_tensors='pt').to('cuda')
                    with torch.autocast('cuda',dtype=torch.bfloat16):loss=correspondence_loss(model(**tokens).logits,torch.tensor([row['target']],device='cuda'))
                    if not torch.isfinite(loss):raise RuntimeError('Nonfinite correspondence loss')
                    (loss/len(batch)).backward();loss_sum+=loss.item()/len(batch)
                gradient=torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad),1.)
                optimizer.step();scheduler.step();step+=1
                changed=not torch.equal(before,witness.detach())
                head_changed=not torch.equal(before_head,head_witness.detach())
                if step>1 and not changed:raise RuntimeError('Adapter weights did not update')
                if step>1 and not head_changed:raise RuntimeError('Classification head did not update')
                if not math.isfinite(float(gradient)) or float(gradient)==0:raise RuntimeError('No finite gradient')
                record={'step':step,'epoch':epoch+1,'loss':loss_sum,'gradientNorm':float(gradient),'adapterWeightChanged':changed,'classifierWeightChanged':head_changed,
                        'elapsedSeconds':time.monotonic()-started,'cudaPeakAllocatedBytes':torch.cuda.max_memory_allocated(),'actualPairs':len(batch)}
                if step>=50:record['estimatedRemainingSeconds']=record['elapsedSeconds']/step*(per_epoch*2-step)
                log.write(json.dumps(record)+'\n');log.flush();(args.output/'status.json').write_text(json.dumps({'state':'CORRESPONDENCE_TRAINING','latest':record},indent=2),encoding='utf-8')
                if step%500==0 and offset+32<len(order):save(epoch,offset+32)
            saved=save(epoch+1,0)
    model.eval();probe=tokenizer(rows[0]['query'],rows[0]['source'],return_tensors='pt').to('cuda')
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):expected=model(**probe).logits.float().cpu()
    del optimizer,scheduler,adapter,head,before,witness,before_head,head_witness,model,base
    gc.collect();torch.cuda.empty_cache()
    restored=PeftModel.from_pretrained(AutoModelForSequenceClassification.from_pretrained(args.model,torch_dtype=torch.bfloat16,local_files_only=True,trust_remote_code=False),saved/'adapter').to('cuda').eval()
    adapter_precision(restored)
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):actual=restored(**probe).logits.float().cpu()
    if not torch.allclose(expected,actual,atol=1e-4,rtol=1e-4):raise RuntimeError('Adapter/head reload changed inference')
    result={'state':'CORRESPONDENCE_TRAINING_COMPLETE','steps':step,'epochs':2,'checkpoint':saved.name,'reloadVerified':True,'qualityAccepted':False,'productActivated':False}
    (args.output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
