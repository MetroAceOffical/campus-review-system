"""Web-only neural checkpoints; the frozen formal training module is unchanged."""
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
from unittest.mock import patch

from . import training as base
from .preparation import prepared,sha,write_json


def identity(folder,family,cfg):
    manifest,_=prepared(folder)
    code={**base.dependencies(),str(Path(__file__).relative_to(base.ROOT)):sha(Path(__file__))}
    return {'family':family,'parameters':cfg,'preparationSha256':sha(Path(folder)/'manifest.json'),
            'inputSha256':manifest['inputSha256'],'artifacts':manifest['artifacts'],'code':code,
            'environment':{'python':sys.version,'torch':importlib.metadata.version('torch'),
                           'numpy':importlib.metadata.version('numpy'),'transformers':importlib.metadata.version('transformers')}}


def checkpoint_metadata(folder,expected_sha=None):
    folder=Path(folder).resolve();boundary=base.ROOT/'runtime'
    if not folder.is_relative_to(boundary):raise ValueError('续训来源须为项目内运行')
    file=folder/'resume.json'
    if file.stat().st_size>64000 or expected_sha and sha(file)!=expected_sha:raise ValueError('续训元数据已变化')
    meta=json.loads(file.read_text(encoding='utf-8'))
    if meta.get('schemaVersion')!=1 or meta.get('taskType')!='WEB_NEURAL_CHECKPOINT':raise ValueError('该运行没有可核验的网页神经检查点')
    if meta.get('checkpointFile') not in ('checkpoint-a.pt','checkpoint-b.pt'):raise ValueError('检查点文件名无效')
    if sha(folder/meta['checkpointFile'])!=meta.get('checkpointSha256'):raise ValueError('续训检查点校验失败')
    best=meta.get('bestSha256')
    if best and (not isinstance(meta.get('bestFile'),str) or not __import__('re').fullmatch(r'best-epoch-[0-9]{4}\.pt',meta['bestFile'])):raise ValueError('最佳模型文件名无效')
    if best and sha(folder/meta['bestFile'])!=best:raise ValueError('续训最佳模型校验失败')
    allowed={'vocab.json','protected-identities.json','lineage-training-identities.json','bert/tokenizer.json','bert/tokenizer_config.json','bert/special_tokens_map.json','bert/vocab.txt'}
    for name,digest in meta.get('encoderFiles',{}).items():
        if name not in allowed or sha(folder/name)!=digest:raise ValueError('续训编码器或隔离记录校验失败')
    return meta


def train(folder,output,family,values,emit,resume=None,warmstart=None):
    if family not in ('cnn','bilstm','bert'):raise ValueError('仅神经模型支持检查点续训')
    if resume and warmstart:raise ValueError('断点恢复与已完成模型继续训练须分别选择')
    from . import training_warmstart as warm
    info=warm.check_parent(warmstart,folder,family) if warmstart else None
    cfg=base.parameters(family,values);bound=identity(folder,family,cfg);source=None;meta=None
    bound['code'][str(Path(warm.__file__).relative_to(base.ROOT))]=sha(warm.__file__)
    if warmstart:bound['parentModelSha256']=warmstart['manifestSha256']

    if resume:
        source=Path(resume['folder']).resolve();meta=checkpoint_metadata(source,resume['metadataSha256'])
        if meta.get('identity',{}).get('parentModelSha256'):bound['parentModelSha256']=meta['identity']['parentModelSha256']
        if meta.get('identity')!=bound:raise ValueError('数据、参数、代码或环境不同，请新建实验')
    runner=lambda old,rows,dev,target,kind,parameters,notify:neural_train(old,rows,dev,target,kind,parameters,notify,bound,source,meta,warmstart,info)
    # One isolated CLI process owns this temporary replacement; formal jobs use
    # their unchanged module/function and are never hot patched in another process.
    with patch.object(base,'neural_train',runner):result=base.train(folder,output,family,values,emit)
    if (Path(output)/'warmstart.json').is_file():result['warmstart']=json.loads((Path(output)/'warmstart.json').read_text(encoding='utf-8'))
    result['dependencies'][str(Path(__file__).relative_to(base.ROOT))]=sha(Path(__file__))
    result['dependencies'][str(Path(warm.__file__).relative_to(base.ROOT))]=sha(warm.__file__)
    if result.get('warmstart'):result['trainingMode']='CONTINUE'
    if source:
        for name in ['protected-identities.json','lineage-training-identities.json']:
            if (source/name).is_file():shutil.copyfile(source/name,Path(output)/name)
    if warmstart:
        warm.save_lineage(output,info)
        result['trainingMode']='CONTINUE'
        result['artifacts'].update({name:sha(Path(output)/name) for name in ['protected-identities.json','lineage-training-identities.json']})
    result['resumedFromMetadataSha256']=resume['metadataSha256'] if resume else None
    result['artifacts'].update({name:sha(Path(output)/name) for name in ['protected-identities.json','lineage-training-identities.json'] if (Path(output)/name).is_file()})
    write_json(Path(output)/'manifest.json',result)
    return result


def neural_train(old,rows,dev,output,family,cfg,emit,bound,source=None,source_meta=None,warmstart=None,warm_info=None):
    import numpy as np
    import torch
    from torch import nn
    vocab=old.make_vocab(rows) if family!='bert' else None;tokenizer=None
    inherited=None;warm_evidence=None
    if warmstart:
        from .training_warmstart import initialize
        model,vocab,tokenizer,inherited,warm_evidence=initialize(old,rows,family,cfg,output,warmstart,warm_info)
        emit({'stage':'WARM_STARTED',**warm_evidence})
    elif family=='bert':
        from transformers import AutoModelForSequenceClassification,AutoTokenizer
        model_source=base.ROOT/'validation/text/models/bert-base-chinese'
        sources=json.loads((base.ROOT/'validation/text/evidence/bert-source-manifest.json').read_text(encoding='utf-8'))
        if any(sha(model_source/item['file'])!=item['sha256'] for item in sources):raise ValueError('BERT基础权重校验失败')
        tokenizer=AutoTokenizer.from_pretrained(source/'bert' if source and (source/'bert/tokenizer.json').is_file() else model_source,local_files_only=True)
        model=AutoModelForSequenceClassification.from_pretrained(model_source,num_labels=2,local_files_only=True)
        tokenizer.save_pretrained(output/'bert')
    else:
        if source and (source/'vocab.json').is_file():vocab=json.loads((source/'vocab.json').read_text(encoding='utf-8'))
        model=old.SentencePairNet(family,len(vocab)+2,cfg['width']);model.head[2]=nn.Dropout(cfg['dropout']);write_json(output/'vocab.json',vocab)
    model.to(cfg['device']);data=base.encode(rows,family,cfg,vocab,tokenizer)
    labels=torch.tensor([int(row['label']) for row in rows],device=cfg['device'])
    optimizer=torch.optim.AdamW(model.parameters(),lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
    generator=torch.Generator().manual_seed(cfg['seed'])
    epoch,cursor,global_step=1,0,0;order=None;loss_sum=0.;seen=0;best=-1.;best_epoch=0;stale=0;history=[];updated=False;checkpoint_generation=0
    if source:
        checkpoint_generation=source_meta['checkpointGeneration']
        checkpoint=torch.load(source/source_meta['checkpointFile'],map_location=cfg['device'],weights_only=True)
        if checkpoint.get('identity')!=bound:raise ValueError('检查点内部身份与数据不匹配')
        model.load_state_dict(checkpoint['model']);optimizer.load_state_dict(checkpoint['optimizer'])
        epoch,cursor,global_step=checkpoint['epoch'],checkpoint['cursor'],checkpoint['globalStep'];order=checkpoint['order']
        if order is not None:order=order.cpu()
        loss_sum,seen=checkpoint['lossSum'],checkpoint['seen'];best,best_epoch,stale=checkpoint['best'],checkpoint['bestEpoch'],checkpoint['stale']
        history=checkpoint['history'];updated=checkpoint['updated'];generator.set_state(checkpoint['generator'].cpu())
        random.setstate(checkpoint['pythonRng']);state=checkpoint['numpyRng'];np.random.set_state((state[0],np.asarray(state[1],dtype=np.uint32),*state[2:]))
        torch.set_rng_state(checkpoint['torchRng'].cpu())
        if cfg['device']=='cuda':torch.cuda.set_rng_state_all([value.cpu() for value in checkpoint['cudaRng']])
        if source_meta.get('bestSha256'):
            shutil.copyfile(source/source_meta['bestFile'],output/source_meta['bestFile']);shutil.copyfile(output/source_meta['bestFile'],output/'best.pt')
        for name in ['protected-identities.json','lineage-training-identities.json']:
            if (source/name).is_file():shutil.copyfile(source/name,output/name)
        warm_evidence=source_meta.get('warmstart')
        emit({'stage':'RESUMED','epoch':epoch,'step':cursor//cfg['batch_size'],'processed':cursor,'total':len(rows)})
    def save():
        nonlocal checkpoint_generation
        checkpoint_generation+=1;checkpoint_file='checkpoint-a.pt' if checkpoint_generation%2 else 'checkpoint-b.pt'
        state=np.random.get_state();temporary=output/(checkpoint_file+'.tmp')
        payload={'identity':bound,'model':model.state_dict(),'optimizer':optimizer.state_dict(),'epoch':epoch,'cursor':cursor,'globalStep':global_step,
            'order':order,'lossSum':loss_sum,'seen':seen,'best':best,'bestEpoch':best_epoch,'stale':stale,'history':history,'updated':updated,
            'generator':generator.get_state(),'torchRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state_all() if cfg['device']=='cuda' else [],
            'numpyRng':(state[0],state[1].tolist(),*state[2:]),'pythonRng':random.getstate()}
        torch.save(payload,temporary);os.replace(temporary,output/checkpoint_file)
        meta={'schemaVersion':1,'taskType':'WEB_NEURAL_CHECKPOINT','identity':bound,'epoch':epoch,'completedEpochs':len(history),
            'cursor':cursor,'globalStep':global_step,'checkpointGeneration':checkpoint_generation,'checkpointFile':checkpoint_file,'checkpointSha256':sha(output/checkpoint_file),
            'bestFile':f'best-epoch-{best_epoch:04d}.pt' if best_epoch else None,'bestSha256':sha(output/f'best-epoch-{best_epoch:04d}.pt') if best_epoch else None}
        names=['vocab.json','protected-identities.json','lineage-training-identities.json','bert/tokenizer.json','bert/tokenizer_config.json','bert/special_tokens_map.json','bert/vocab.txt']
        meta['encoderFiles']={name:sha(output/name) for name in names if (output/name).is_file()}
        if warm_evidence is not None:meta['warmstart']=warm_evidence
        write_json(output/'resume.json.tmp',meta);os.replace(output/'resume.json.tmp',output/'resume.json')
        emit({'stage':'CHECKPOINT_SAVED','epoch':epoch,'step':cursor//cfg['batch_size'],'processed':cursor,'total':len(rows)})
    while epoch<=cfg['epochs'] and not (cfg['patience'] and stale>=cfg['patience']):
        if order is None:order=torch.randperm(len(rows),generator=generator);cursor=0;loss_sum=0.;seen=0
        model.train();optimizer.zero_grad(set_to_none=True);steps=math.ceil(len(rows)/cfg['batch_size'])
        for begin in range(cursor,len(rows),cfg['batch_size']):
            step=begin//cfg['batch_size']+1;index=order[begin:begin+cfg['batch_size']]
            logits=base.forward(model,family,data,index,cfg['device']);loss=nn.functional.cross_entropy(logits,labels[index.to(cfg['device'])])
            if not torch.isfinite(loss):raise ValueError('训练损失非有限值')
            window_start=((step-1)//cfg['gradient_accumulation'])*cfg['gradient_accumulation'];window_size=min(cfg['gradient_accumulation'],steps-window_start)
            (loss/window_size).backward();boundary=step%cfg['gradient_accumulation']==0 or step==steps
            if boundary:
                before=next(model.parameters()).detach().clone();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();optimizer.zero_grad(set_to_none=True)
                updated=updated or not torch.equal(before,next(model.parameters()).detach());global_step+=1
            value=float(loss.item());loss_sum+=value*len(index);seen+=len(index);cursor=begin+len(index)
            emit({'stage':'TRAINING','epoch':epoch,'epochs':cfg['epochs'],'step':step,'steps':steps,'loss':value,'learningRate':cfg['learning_rate'],'processed':cursor,'total':len(rows)})
            if boundary and (global_step==1 or global_step%50==0):save()
        scores=base.neural_scores(model,family,dev,cfg,vocab,tokenizer);metrics,_=base.metric_report(dev,scores,family)
        item={'epoch':epoch,'loss':loss_sum/seen,'validation':{key:value for key,value in metrics.items() if key not in ('roc','pr')}};history.append(item)
        emit({'stage':'EPOCH',**item})
        if metrics['macro_f1']>best+.0001:
            best=metrics['macro_f1'];best_epoch=epoch;stale=0
            best_file=output/f'best-epoch-{epoch:04d}.pt';torch.save(model.state_dict(),best_file.with_suffix('.tmp'));os.replace(best_file.with_suffix('.tmp'),best_file);shutil.copyfile(best_file,output/'best.pt')
        else:stale+=1
        epoch+=1;cursor=0;order=None;loss_sum=0.;seen=0;write_json(output/'history.json',history);save()
    if not updated:raise ValueError('模型参数没有更新')
    model.load_state_dict(torch.load(output/'best.pt',map_location=cfg['device'],weights_only=True))
    if warm_evidence is not None:
        from .training_warmstart import inherited_difference
        if inherited is not None:warm_evidence['trainedInheritedMaxDifference']=inherited_difference(model,inherited)
        write_json(output/'warmstart.json',warm_evidence)

    reference=np.asarray(base.neural_scores(model,family,dev,cfg,vocab,tokenizer))
    if family=='bert':
        from transformers import AutoModelForSequenceClassification
        model.save_pretrained(output/'bert');again=AutoModelForSequenceClassification.from_pretrained(output/'bert',local_files_only=True).to(cfg['device'])
    else:
        again=old.SentencePairNet(family,len(vocab)+2,cfg['width']).to(cfg['device']);again.load_state_dict(torch.load(output/'best.pt',map_location=cfg['device'],weights_only=True))
    actual=np.asarray(base.neural_scores(again,family,dev,cfg,vocab,tokenizer))
    return reference,history,best_epoch,float(np.max(np.abs(reference-actual)))
