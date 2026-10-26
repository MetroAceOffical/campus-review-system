"""Offline BGE auxiliary retrieval training; no business config activation."""
import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]


def retrieval_loss(query, passages, temperature=.05):
    query = F.normalize(query.float(),dim=-1)
    passages = F.normalize(passages.float(),dim=-1)
    scores = torch.einsum('bd,bnd->bn',query,passages)/temperature
    return F.cross_entropy(scores,torch.zeros(len(query),device=query.device,dtype=torch.long))


def explicit_groups(pairs):
    negatives = defaultdict(set)
    positives = set()
    for left,right,target in pairs:
        if target:
            positives.add(tuple(sorted((left,right))))
        else:
            negatives[left].add(right)
            negatives[right].add(left)
    groups = []
    for left,right in sorted(positives):
        if len(negatives[left]-{right}) < 4:
            left,right = right,left
        available = sorted(negatives[left]-{right})
        if len(available) >= 4:
            groups.append({'queryId':left,'positiveId':right,'negativeIds':available[:4]})
    return groups


def check_files(folder, entries):
    for name,expected in entries.items():
        with (folder/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != expected:
                raise ValueError('Immutable input changed: '+name)


def main():
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=ROOT/'runtime/datasets/final-training-v1')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--initial-weights',type=Path)
    args = parser.parse_args()
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('Configured CUDA BF16 training is unavailable; do not silently change environments')
    check_files(args.data,json.loads((args.data/'READY').read_text(encoding='utf-8')))
    acquisition = json.loads((args.model/'acquisition.json').read_text(encoding='utf-8'))
    if acquisition['status'] != 'download_verified_not_trained':
        raise ValueError('Base model acquisition incomplete')
    check_files(args.model,{item['file']:item['sha256'] for item in acquisition['files']})
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'run.json').exists() and not args.resume:
        raise RuntimeError('Existing run requires explicit checkpoint resume')
    seed = 20261026
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(4)
    db = sqlite3.connect(args.data/'auxiliary.sqlite')
    documents = dict(db.execute('SELECT id,text FROM documents'))
    train = explicit_groups(list(db.execute("SELECT left_id,right_id,target FROM pairs WHERE split='aux_train'")))
    validation = explicit_groups(list(db.execute("SELECT left_id,right_id,target FROM pairs WHERE split='aux_validation'")))
    db.close()
    if not train:
        raise ValueError('No queries have four distinct explicit labelled negatives')
    config = {'taskType':'RETRIEVAL_RELEVANCE','stage':'public_event_story_auxiliary_only','seed':seed,'epochs':2,'maxTokensPerSide':256,
              'microbatch':2,'effectiveQueries':32,'explicitNegatives':4,'learningRate':2e-5,'weightDecay':.01,'warmupRatio':.06,
              'trainGroups':len(train),'validationGroups':len(validation),'baseRevision':acquisition['revision'],
              'datasetManifestSha256':hashlib.sha256((args.data/'manifest.json').read_bytes()).hexdigest(),
              'warning':'Known event/story relevance, not campus correspondence training; auxiliary uses leading 256-token windows. Not a product quality result.'}
    config_sha = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    if args.initial_weights:
        with (args.initial_weights/'model.safetensors').open('rb') as stream:
            config['initialCheckpointSha256'] = hashlib.file_digest(stream,'sha256').hexdigest()
        config_sha = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    (args.output/'run.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    (args.output/'train-groups.json').write_text(json.dumps(train,indent=2),encoding='utf-8')
    tokenizer = AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    model = AutoModel.from_pretrained(args.resume/'model' if args.resume else args.initial_weights or args.model,local_files_only=True,trust_remote_code=False)
    model.gradient_checkpointing_enable()
    model.to('cuda')
    update_witness = next(parameter for name,parameter in model.named_parameters() if name.endswith('attention.self.query.weight'))
    optimizer = torch.optim.AdamW(model.parameters(),lr=2e-5,weight_decay=.01)
    steps_per_epoch = math.ceil(len(train)/32)
    scheduler = get_linear_schedule_with_warmup(optimizer,math.ceil(steps_per_epoch*2*.06),steps_per_epoch*2)
    global_step,first_epoch,first_cursor = 0,0,0
    if args.resume:
        state = torch.load(args.resume/'state.pt',map_location='cpu',weights_only=False)
        if state['configSha256'] != config_sha:
            raise ValueError('Resume configuration or data changed')
        optimizer.load_state_dict(state['optimizer']);scheduler.load_state_dict(state['scheduler'])
        random.setstate(state['pythonRandom']);np.random.set_state(state['numpyRandom']);torch.set_rng_state(state['torchRandom']);torch.cuda.set_rng_state_all(state['cudaRandom'])
        global_step,first_epoch,first_cursor = state['step'],state['nextEpoch'],state['nextCursor']
        if first_epoch >= config['epochs']:
            print(json.dumps({'state':'ALREADY_COMPLETED','step':global_step,'checkpoint':str(args.resume)}),flush=True)
            return

    def encode(texts):
        tokens = tokenizer(texts,padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
        return model(**tokens).last_hidden_state[:,0]

    @torch.no_grad()
    def evaluate():
        model.eval()
        losses = []
        for group in validation[:128]:
            ids = [group['positiveId']]+group['negativeIds']
            with torch.autocast('cuda',dtype=torch.bfloat16):
                q = encode([documents[group['queryId']]])
                p = encode([documents[key] for key in ids]).unsqueeze(0)
                losses.append(retrieval_loss(q,p).item())
        model.train()
        return sum(losses)/len(losses) if losses else None

    def checkpoint(next_epoch,next_cursor):
        folder = args.output/f'checkpoint-{global_step:06d}'
        temporary = args.output/f'.checkpoint-{global_step:06d}.partial'
        temporary.mkdir(exist_ok=False)
        model.save_pretrained(temporary/'model');tokenizer.save_pretrained(temporary/'model')
        state = {'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),'step':global_step,'nextEpoch':next_epoch,'nextCursor':next_cursor,
                 'pythonRandom':random.getstate(),'numpyRandom':np.random.get_state(),'torchRandom':torch.get_rng_state(),
                 'cudaRandom':torch.cuda.get_rng_state_all(),'configSha256':config_sha}
        torch.save(state,temporary/'state.pt')
        hashes = {p.relative_to(temporary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in temporary.rglob('*') if p.is_file()}
        (temporary/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
        temporary.replace(folder)
        return folder

    log_path = args.output/'history.jsonl'
    started = time.monotonic()
    baseline = evaluate() if not args.resume else None
    with log_path.open('a',encoding='utf-8') as log:
        log.write(json.dumps({'event':'start_or_resume','step':global_step,'baselineValidationLoss':baseline,'configSha256':config_sha})+'\n');log.flush()
        for epoch in range(first_epoch,2):
            order = list(range(len(train)));random.Random(seed+epoch).shuffle(order)
            cursor = first_cursor if epoch == first_epoch else 0
            for offset in range(cursor,len(order),32):
                batch = [train[index] for index in order[offset:offset+32]]
                optimizer.zero_grad(set_to_none=True)
                old = update_witness.detach().flatten()[:64].clone()
                total_loss = 0
                for micro in range(0,len(batch),2):
                    selected = batch[micro:micro+2]
                    queries = [documents[g['queryId']] for g in selected]
                    passages = [documents[key] for g in selected for key in [g['positiveId']]+g['negativeIds']]
                    with torch.autocast('cuda',dtype=torch.bfloat16):
                        q = encode(queries);p = encode(passages).reshape(len(selected),5,-1)
                        loss = retrieval_loss(q,p)
                    if not torch.isfinite(loss):
                        raise RuntimeError('Non-finite training loss')
                    (loss*len(selected)/len(batch)).backward()
                    total_loss += loss.item()*len(selected)/len(batch)
                gradient = torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
                optimizer.step();scheduler.step();global_step += 1
                updated = not torch.equal(old,update_witness.detach().flatten()[:64])
                if global_step > 1 and not updated:
                    raise RuntimeError('Trainable query weights did not update')
                update_norm = float(gradient)
                if not math.isfinite(update_norm) or update_norm == 0:
                    raise RuntimeError('No finite gradient update')
                record = {'step':global_step,'epoch':epoch+1,'nextCursor':min(offset+32,len(order)),
                          'loss':total_loss,'gradientNorm':update_norm,'parameterSliceChanged':updated,
                          'elapsedSeconds':time.monotonic()-started,'cudaPeakBytes':torch.cuda.max_memory_allocated(),
                          'actualQueries':len(batch),'explicitPassagesPerQuery':5,'learningRate':scheduler.get_last_lr()[0]}
                log.write(json.dumps(record)+'\n');log.flush()
                (args.output/'status.json').write_text(json.dumps({'state':'TRAINING','latest':record},indent=2),encoding='utf-8')
                if global_step % 500 == 0 and offset+32 < len(order):
                    checkpoint(epoch,offset+32)
            validation_loss = evaluate()
            saved = checkpoint(epoch+1,0)
            log.write(json.dumps({'event':'epoch_end','epoch':epoch+1,'step':global_step,'validationLoss':validation_loss,'checkpoint':saved.name})+'\n');log.flush()
    # Reload actual serialized weights and verify one fixed embedding in the same precision.
    model.eval()
    probe = documents[train[0]['queryId']]
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
        before = encode([probe]).float().cpu()
    reloaded = AutoModel.from_pretrained(saved/'model',local_files_only=True,trust_remote_code=False).to('cuda').eval()
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
        inputs = tokenizer([probe],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
        after = reloaded(**inputs).last_hidden_state[:,0].float().cpu()
    if not torch.allclose(before,after,atol=1e-5,rtol=1e-5):
        raise RuntimeError('Serialized checkpoint reload changed inference')
    result = {'state':'AUXILIARY_TRAINING_COMPLETE','steps':global_step,'epochs':2,'checkpoint':saved.name,'reloadVerified':True,
              'elapsedSeconds':time.monotonic()-started,'campusAdaptationComplete':False,'productActivated':False,'qualityAccepted':False}
    (args.output/'status.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
