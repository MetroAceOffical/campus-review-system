"""Versioned web BERT scorer for the existing retrieval/alignment pipeline."""
import json,math
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256
from .models import ROOT


def calibration(labels,scores):
    from sklearn.metrics import f1_score,precision_score,recall_score
    if len(labels)!=len(scores) or set(labels)!={0,1} or not all(math.isfinite(x) and 0<=x<=1 for x in scores):raise ValueError('校准集须包含两类有效分数')
    candidates=sorted(set([.5,*[min(1-1e-6,max(1e-6,float(s))) for s in scores]]))
    def quality(t):
        predicted=[int(s>=t) for s in scores]
        return (f1_score(labels,predicted,average='macro',zero_division=0),precision_score(labels,predicted,zero_division=0),-abs(t-.5))
    threshold=max(candidates,key=quality);predicted=[int(s>=threshold) for s in scores]
    return {'method':'validation-macro-f1-v1','threshold':threshold,'rows':len(labels),'macroF1':float(f1_score(labels,predicted,average='macro',zero_division=0)),
            'precision':float(precision_score(labels,predicted,zero_division=0)),'recall':float(recall_score(labels,predicted,zero_division=0)),
            'scoreMeaning':'MONOTONE_CALIBRATED_DECISION_SCORE','selectionPartition':'validation'}


def decision_scores(scores,fit):
    threshold=fit['threshold']
    if not 0<threshold<1:raise ValueError('校准阈值无效')
    # Piecewise monotone mapping retains ordering and places the validated
    # operating point at the existing evidence policy's 0.5 boundary.
    return [.5*s/threshold if s<threshold else .5+.5*(s-threshold)/(1-threshold) for s in scores]


def compatible(folder):
    from transformers import AutoTokenizer,AutoConfig
    from campus_workbench.training import load_model
    folder=Path(folder).resolve()
    if not folder.is_relative_to(ROOT/'runtime/workbench/computations'):raise ValueError('请选择项目内网页模型')
    manifest=load_model(folder)
    if manifest['family']!='bert' or manifest['parameters']['max_length']<128:raise ValueError('正文审核需要128词元以上的中文BERT句对模型')
    cfg=AutoConfig.from_pretrained(folder/'bert',local_files_only=True)
    if cfg.model_type!='bert' or cfg.hidden_size!=768 or cfg.num_labels!=2:raise ValueError('BERT结构或类别不兼容')
    tokenizer=AutoTokenizer.from_pretrained(folder/'bert',local_files_only=True)
    base=AutoTokenizer.from_pretrained(ROOT/'validation/text/models/bert-base-chinese',local_files_only=True)
    if tokenizer.get_vocab()!=base.get_vocab() or tokenizer.all_special_ids!=base.all_special_ids:raise ValueError('分词词表与参考库不兼容')
    probes=['南京传媒学院新闻中心开展校园采访。','师生参加新闻写作研讨，交流课程建设。']
    if tokenizer(probes)['input_ids']!=base(probes)['input_ids']:raise ValueError('分词编码与参考库不兼容')
    return manifest,tokenizer


def prepare(config,output,pair_verification):
    from campus_workbench.preparation import prepared,write_json
    from campus_workbench.training import predict
    from .models import configurations
    from .contextual_text import configuration as context_config
    from .text_refinement import configuration as refined_config
    from .mutual_text import configuration as mutual_config
    folder=Path(config['model']).resolve();preparation=Path(config['preparation']).resolve();output=Path(output)
    manifest,_=compatible(folder);_,partitions=prepared(preparation)
    if file_sha256(preparation/'manifest.json')!=manifest['preparationSha256']:raise ValueError('校准划分与模型版本不一致')
    rows=partitions['validation'];scored=predict(folder,rows,lambda _:None,device_override='cpu')
    fit=calibration([int(r['label']) for r in rows],[r['score'] for r in scored])
    fit['dataSha256']=file_sha256(preparation/'validation.jsonl');fit['modelManifestSha256']=file_sha256(folder/'manifest.json')
    write_json(output/'calibration.json',fit)
    text,image=configurations();text=mutual_config(refined_config(context_config(text)))
    implementation=['models.py','web_bert.py','contextual_text.py','text_refinement.py','mutual_text.py','semantic.py','text.py','reference_versions.py']
    files={**pair_verification['verifiedFiles'],**{(Path(__file__).parent/n).relative_to(ROOT).as_posix():file_sha256(Path(__file__).parent/n) for n in implementation}}
    files.update({p.relative_to(ROOT).as_posix():file_sha256(p) for p in [preparation/'manifest.json',preparation/'validation.jsonl',output/'calibration.json']})
    binding={'modelId':config['modelId'],'modelManifestSha256':file_sha256(folder/'manifest.json'),'weightSha256':file_sha256(folder/'bert/model.safetensors'),
             'tokenizerSha256':file_sha256(folder/'bert/tokenizer.json'),'adapterSha256':file_sha256(Path(__file__)),'calibrationSha256':file_sha256(output/'calibration.json'),
             'evaluationId':config['evaluationId'],'positiveLabel':1,'maxTokens':128,'scoreMeaning':fit['scoreMeaning']}
    text={**text,'schemaVersion':'text-web-bert-v1','method':'web-bert-context-20261031','webBert':binding,'weightSha256':binding['weightSha256'],'tokenizerSha256':binding['tokenizerSha256']}
    text.pop('configId');text['configId']='text-'+digest_json(text)
    descriptor={'schemaVersion':1,'textConfig':text,'calibration':fit,'modelFolder':folder.relative_to(ROOT).as_posix(),'verifiedFiles':files}
    path=output/'adapter.json';write_json(path,descriptor)
    return {'scene':'TEXT_REUSE','textConfig':text,'imageConfig':image,'textAdapter':{'path':path.relative_to(ROOT).as_posix(),'sha256':file_sha256(path)},
            'modelManifestSha256':binding['modelManifestSha256'],'calibration':fit,'pairEvaluation':pair_verification['metrics'],'verifiedFiles':{**files,path.relative_to(ROOT).as_posix():file_sha256(path)}}


def verify_descriptor(path,expected):
    path=Path(path).resolve()
    if path.name!='adapter.json' or path.parent.parent!=ROOT/'runtime/delivery/releases' or file_sha256(path)!=expected:raise ValueError('正文模型适配配置身份无效')
    descriptor=json.loads(path.read_text(encoding='utf-8'));text=descriptor['textConfig']
    if descriptor.get('schemaVersion')!=1 or text.get('schemaVersion')!='text-web-bert-v1':raise ValueError('正文模型适配配置无效')
    for name,digest in descriptor['verifiedFiles'].items():
        file=(ROOT/name).resolve()
        if Path(name).is_absolute() or not any(file.is_relative_to(ROOT/p) for p in ('runtime','app','validation')) or file_sha256(file)!=digest:raise ValueError('正文模型适配工件已变化：'+name)
    identity={k:v for k,v in text.items() if k!='configId'}
    if text['configId']!='text-'+digest_json(identity):raise ValueError('正文模型配置摘要不一致')
    folder=(ROOT/descriptor['modelFolder']).resolve()
    if not folder.is_relative_to(ROOT/'runtime/workbench/computations') or file_sha256(folder/'manifest.json')!=text['webBert']['modelManifestSha256']:raise ValueError('正文模型版本已变化')
    return descriptor


def register(models,path,expected):
    descriptor=verify_descriptor(path,expected);config=descriptor['textConfig'];key=config['configId']
    loaded=models.setdefault('webBertModels',{})
    if key in loaded:return config
    from transformers import AutoModelForSequenceClassification
    import torch
    folder=ROOT/descriptor['modelFolder'];_,tokenizer=compatible(folder)
    # Keep one additional web scorer resident; descriptors remain reloadable.
    loaded.clear()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    device='cuda' if torch.cuda.is_available() else 'cpu'
    model=AutoModelForSequenceClassification.from_pretrained(folder/'bert',local_files_only=True).eval().to(device)
    tokenizer.model_max_length=10**8
    def predict(pairs):
        scores=[]
        with torch.inference_mode():
            for start in range(0,len(pairs),8):
                batch=pairs[start:start+8];inputs=tokenizer([p['sentence1'] for p in batch],[p['sentence2'] for p in batch],padding=True,truncation=True,max_length=128,return_tensors='pt').to(device)
                scores.extend(model(**inputs).logits.float().softmax(-1)[:,1].cpu().tolist())
        return decision_scores(scores,descriptor['calibration'])
    # Real inference must succeed before the config is advertised as available.
    probe=predict([{'sentence1':'南京传媒学院开展校园新闻工作。','sentence2':'学校组织校园新闻工作。'}])
    if len(probe)!=1 or not math.isfinite(probe[0]):raise ValueError('正文模型加载核验失败')
    loaded[key]={'predictBert':predict,'tokenizer':tokenizer}
    models['textConfigs'][key]=config
    models.setdefault('textAdapterDescriptors',{})[key]={'path':str(path),'sha256':expected}
    return config


def select_models(models,key):
    if 'webBert' not in models.get('textConfigs',{}).get(key,{}):return models
    binding=models.get('webBertModels',{}).get(key)
    if binding is None:raise ValueError('该正文BERT版本尚未加载')
    return {**models,**binding}
