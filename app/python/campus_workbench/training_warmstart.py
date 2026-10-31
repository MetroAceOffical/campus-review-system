"""Verified completed-model initialization, separate from interrupted-job recovery."""
import json
from pathlib import Path
from .preparation import prepared,sha,write_json
from .training import ROOT
from .training_identities import collect as identities,merge,ancestry,require_disjoint

def check_parent(descriptor,preparation,family):
    folder=Path(descriptor['folder']).resolve()
    if not folder.is_relative_to(ROOT/'runtime'):raise ValueError('起始模型须为项目内模型')
    if sha(folder/'manifest.json')!=descriptor['manifestSha256']:raise ValueError('起始模型身份已变化')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='COMPLETED' or manifest.get('family')!=family:raise ValueError('起始模型类型不兼容')
    for name,digest in manifest['artifacts'].items():
        if name in ('best.pt','vocab.json','train-identities.json','protected-identities.json','lineage-training-identities.json') or name.startswith('bert/'):
            path=(folder/name).resolve()
            if not path.is_relative_to(folder) or sha(path)!=digest:raise ValueError('起始模型工件校验失败')
    parent_preparation=Path(descriptor['preparation']).resolve()
    if not parent_preparation.is_relative_to(ROOT/'runtime') or sha(parent_preparation/'manifest.json')!=descriptor['preparationSha256']:raise ValueError('起始样本划分已变化')
    _,old=prepared(parent_preparation);_,new=prepared(preparation)
    def optional(name):return json.loads((folder/name).read_text(encoding='utf-8')) if (folder/name).is_file() else {}
    history=ancestry(folder)
    protected=merge(identities([row for name,rows in old.items() if name!='train' for row in rows]),optional('protected-identities.json'),history['holdout'])
    trained=merge(identities(old['train']),optional('lineage-training-identities.json'),history['train'])
    new_train=identities(new['train']);new_holdout=identities([row for name,rows in new.items() if name!='train' for row in rows])
    require_disjoint(new_train,protected,'继续训练材料与历史验证/测试来源或近重复材料不隔离，请调整划分')
    require_disjoint(new_holdout,trained,'新评价材料与祖先训练来源或近重复材料不隔离，请调整划分')
    return {**manifest,'protected':merge(protected,new_holdout),'lineageTraining':merge(trained,new_train)}

def save_lineage(output,info):
    for name,key in [('protected-identities.json','protected'),('lineage-training-identities.json','lineageTraining')]:
        write_json(Path(output)/name,{field:sorted(values) for field,values in info[key].items()})

def inherited_difference(model,state):
    import torch
    difference=0.
    for key,old in state.items():
        current=model.state_dict()[key].detach().cpu()
        if key=='embedding.weight':current=current[:old.shape[0]]
        difference=max(difference,float((current.float()-old.cpu().float()).abs().max()))
    return difference

def initialize(old,rows,family,cfg,output,descriptor,info):
    import torch
    folder=Path(descriptor['folder']);added=0;tokenizer=None;vocab=None
    if family=='bert':
        from transformers import AutoModelForSequenceClassification,AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(folder/'bert',local_files_only=True)
        model=AutoModelForSequenceClassification.from_pretrained(folder/'bert',local_files_only=True)
        if model.config.num_labels!=2:raise ValueError('起始模型类别不兼容')
        state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};tokenizer.save_pretrained(output/'bert')
    else:
        if cfg['width']!=info['parameters']['width']:raise ValueError('继续训练须保持原网络宽度')
        vocab=json.loads((folder/'vocab.json').read_text(encoding='utf-8'));fresh=old.make_vocab(rows)
        for token in fresh:
            if token not in vocab and len(vocab)<12000:vocab[token]=len(vocab)+2;added+=1
        model=old.SentencePairNet(family,len(vocab)+2,cfg['width']);model.head[2]=torch.nn.Dropout(cfg['dropout'])
        state=torch.load(folder/'best.pt',map_location='cpu',weights_only=True);target=model.state_dict()
        for key,value in state.items():
            if key=='embedding.weight':target[key][:value.shape[0]].copy_(value)
            else:target[key]=value
        model.load_state_dict(target);write_json(output/'vocab.json',vocab)
    save_lineage(output,info)
    initial=inherited_difference(model,state)
    if initial!=0:raise ValueError('起始模型权重继承校验失败')
    return model,vocab,tokenizer,state,{'parentManifestSha256':descriptor['manifestSha256'],'initialInheritedMaxDifference':initial,'addedTokens':added}
