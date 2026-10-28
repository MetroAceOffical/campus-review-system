"""Offline-only, hash-bound model controls. Never registers a service profile."""
import argparse
import contextlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection import retrieval,v3_runtime

BGE=ROOT/'runtime/models/final/bge-base-zh-v1.5/f03589ceff5aac7111bd60cfc7d497ca17ecac65'
M3=ROOT/'runtime/experiments/route-b-development-20261026/model'
M3_MANIFEST=M3.parent/'candidate-manifest.json'
BERT=ROOT/'validation/text/models/bert-base-chinese'
LOCK=ROOT/'validation/text/round2/selection-lock.json'
VARIANTS={'untrained-dense':'LEGACY_SEMANTIC_SCORE','trained-dense-unadapted-reranker':'PRETRAINED_RELEVANCE_SCORE'}


def official(folder,manifest_path,repo,revision,weight,weight_sha):
    manifest=v3_runtime.read(manifest_path)
    if manifest.get('repo')!=repo or manifest.get('revision')!=revision:raise ValueError('Select the pinned official pretrained revision')
    files={row['file']:row['sha256'] for row in manifest['files']}
    names={'config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json',weight}
    names|={name for name in ('vocab.txt','sentencepiece.bpe.model','added_tokens.json') if (folder/name).exists()}
    if not names<=files.keys() or files[weight]!=weight_sha:raise ValueError('Official asset manifest is incomplete or weights differ')
    for name in names:
        if retrieval._sha(folder/name)!=files[name]:raise ValueError('Pretrained component changed: '+name)
    return {'folder':str(folder),'files':{name:files[name] for name in sorted(names)},'repo':repo,'revision':revision,
            'acquisitionManifestSha256':retrieval._sha(manifest_path)}


def base_bge():
    return official(BGE,BGE/'acquisition.json','BAAI/bge-base-zh-v1.5',BGE.name,'pytorch_model.bin',
                    '731cf5d88ed555a21ff2f2d9fa4db43b10489173ddd9178db3eecfd7a2bae044')


def base_m3():
    return {**official(M3,M3_MANIFEST,'BAAI/bge-reranker-v2-m3','953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e','model.safetensors',
                      'd9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286'),
            'scoreType':'PRETRAINED_RELEVANCE_SCORE','head':'SIGMOID_SINGLE_LOGIT'}


def frozen_bert():
    lock=v3_runtime.read(LOCK);artifact=(ROOT/'validation/text'/lock['selected']['bert']['artifact']).resolve()
    if not artifact.is_relative_to(ROOT/'validation/text/round2/search/bert') or retrieval._sha(artifact)!=lock['artifact_sha256']['bert']:
        raise ValueError('Frozen BERT checkpoint differs from the selected model')
    names={'config.json','tokenizer.json','tokenizer_config.json','vocab.txt'}
    names|={name for name in ('special_tokens_map.json','added_tokens.json') if (BERT/name).exists()}
    return {'folder':str(BERT),'files':{name:retrieval._sha(BERT/name) for name in sorted(names)},
            'weightPath':str(artifact),'weightSha256':lock['artifact_sha256']['bert'],'selectionLockSha256':retrieval._sha(LOCK),
            'scoreType':'LEGACY_SEMANTIC_SCORE','head':'SOFTMAX_CLASS_1','trainingDomain':'FROZEN_PAWS_X_NOT_CAMPUS'}


def trained_bge(run):
    if run is None:raise ValueError('Select the actual completed campus BGE run')
    run=v3_runtime.controlled(run)
    if not (run/'status.json').is_file() or not (run/'run.json').is_file():raise ValueError('Campus BGE training has not completed')
    state=v3_runtime.read(run/'status.json');cfg=v3_runtime.read(run/'run.json')
    if state.get('state')!='CAMPUS_RETRIEVAL_TRAINING_COMPLETE' or state.get('epochs')!=2 or state.get('reloadVerified') is not True:
        raise ValueError('Campus BGE training/reload not complete')
    if cfg.get('epochs')!=2 or cfg.get('trainGroups',0)<1000 or cfg.get('effectiveQueries')!=32 or cfg.get('maxTokensPerSide')!=512:
        raise ValueError('Campus BGE formal scale/configuration differs')
    name=state.get('checkpoint','')
    if not re.fullmatch(r'checkpoint-\d{6}',name):raise ValueError('Invalid completed campus checkpoint')
    checkpoint=run/name;files=v3_runtime.verify_files(checkpoint)
    return {'folder':str(checkpoint/'model'),'files':{k[6:]:v for k,v in files.items() if k.startswith('model/')},
            'run':str(run),'runSha256':retrieval._sha(run/'run.json'),'statusSha256':retrieval._sha(run/'status.json')}


def validate_variant(manifest):
    variant=manifest.get('variant')
    if variant not in VARIANTS or manifest.get('reranker',{}).get('scoreType')!=VARIANTS[variant]:raise ValueError('Ablation variant/head differs')
    if manifest.get('campusRetrieverTrainingComplete') is not (variant=='trained-dense-unadapted-reranker') or manifest.get('correspondenceTrainingComplete') is not False or manifest.get('productActivated') is not False:
        raise ValueError('Ablation cannot claim completed task training or production activation')


def register(variant,references,output,retriever_run=None):
    if variant not in VARIANTS:raise ValueError('Unknown offline ablation')
    references=v3_runtime.controlled(references);output=v3_runtime.controlled(output)
    if output.exists():raise ValueError('Use a new immutable ablation bundle')
    trained=variant=='trained-dense-unadapted-reranker'
    manifest={'schemaVersion':'offline-ablation-bundle-v1','variant':variant,'purpose':'OFFLINE_CONTROL_ONLY',
              'retriever':trained_bge(retriever_run) if trained else base_bge(),'reranker':base_m3() if trained else frozen_bert(),
              'references':{'path':str(references),'sha256':retrieval._sha(references)},
              'campusRetrieverTrainingComplete':trained,'correspondenceTrainingComplete':False,'formalCalibrationFrozen':False,'productActivated':False}
    manifest['bundleId']='ablation-bundle-'+retrieval._digest(manifest);validate_variant(manifest)
    output.mkdir(parents=True)
    (output/'bundle.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'READY').write_text(json.dumps({'bundle.json':retrieval._sha(output/'bundle.json')}),encoding='utf-8')
    return manifest


def verify_bundle(folder):
    folder=v3_runtime.controlled(folder);v3_runtime.verify_files(folder);manifest=v3_runtime.read(folder/'bundle.json')
    if manifest.get('schemaVersion')!='offline-ablation-bundle-v1' or manifest.get('purpose')!='OFFLINE_CONTROL_ONLY' or manifest.get('bundleId')!='ablation-bundle-'+retrieval._digest({k:v for k,v in manifest.items() if k!='bundleId'}):
        raise ValueError('Offline ablation identity differs')
    validate_variant(manifest);trained=manifest['variant']=='trained-dense-unadapted-reranker'
    expected_retriever=trained_bge(manifest['retriever'].get('run')) if trained else base_bge()
    expected_reranker=base_m3() if trained else frozen_bert()
    if manifest['retriever']!=expected_retriever or manifest['reranker']!=expected_reranker:raise ValueError('Frozen ablation components changed')
    if retrieval._sha(v3_runtime.controlled(manifest['references']['path']))!=manifest['references']['sha256']:raise ValueError('Ablation reference bank changed')
    return manifest


def pair_scorer(model,tokenizer,descriptor,*,device,precision):
    import torch
    if device not in {'cpu','cuda'} or precision not in {'FP32','BF16'} or device=='cpu' and precision!='FP32':raise ValueError('Unsupported ablation execution policy')
    if device=='cuda' and (not torch.cuda.is_available() or precision=='BF16' and not torch.cuda.is_bf16_supported()):raise RuntimeError('Requested CUDA/BF16 unavailable')
    kind=descriptor['scoreType'];labels=2 if kind=='LEGACY_SEMANTIC_SCORE' else 1
    if kind not in VARIANTS.values() or model.config.num_labels!=labels:raise ValueError('Ablation classifier head differs')
    config={'schemaVersion':'offline-ablation-head-v1','assetsSha256':retrieval._digest(descriptor),'scoreType':kind,
            'device':device,'precision':precision,'parameterPrecision':'FP32','maxJointTokens':512,'truncation':False,
            'algorithmSha256':retrieval._sha(Path(__file__))}
    config['configId']='ablation-head-'+retrieval._digest(config)
    def score(pair):
        if any(not isinstance(pair[k],str) or not pair[k].strip() for k in ('queryText','sourceText')):raise ValueError('Require original nonempty query/source slices')
        tokens=tokenizer(pair['queryText'],pair['sourceText'],truncation=False,return_tensors='pt')
        if tokens['input_ids'].shape[1]>512:raise ValueError('Ablation pair exceeds joint512; no truncation')
        tokens={k:v.to(device) for k,v in tokens.items()}
        with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16) if precision=='BF16' else contextlib.nullcontext():
            logits=model(**tokens).logits.float()
        if logits.shape!=(1,labels) or not torch.isfinite(logits).all():raise ValueError('Invalid ablation classifier logits')
        return float(torch.softmax(logits,dim=-1)[0,1] if labels==2 else torch.sigmoid(logits[0,0]))
    return {'model':model,'tokenizer':tokenizer,'configuration':config,'scorePair':score}


def load_bundle(folder,*,device='cuda',precision='BF16',batch_size=8,legacy_models=None):
    from transformers import AutoConfig,AutoModelForSequenceClassification,AutoTokenizer
    import torch
    from campus_detection.retrieval_model import load_retrieval_model
    manifest=verify_bundle(folder);retriever=manifest['retriever'];head=manifest['reranker']
    encoder=load_retrieval_model(retriever['folder'],expected_hashes=retriever['files'],device=device,precision=precision,batch_size=batch_size)
    if head['scoreType']=='LEGACY_SEMANTIC_SCORE':
        if legacy_models is not None:
            if legacy_models['loadedWeights']['bert']!=head['weightSha256']:raise ValueError('Loaded legacy BERT differs')
            model=legacy_models['bert'];tokenizer=legacy_models['tokenizer']
        else:
            cfg=AutoConfig.from_pretrained(head['folder'],local_files_only=True,num_labels=2,trust_remote_code=False)
            model=AutoModelForSequenceClassification.from_config(cfg,trust_remote_code=False)
            model.load_state_dict(torch.load(head['weightPath'],map_location='cpu',weights_only=True))
            model=model.float().to(device).eval()
            tokenizer=AutoTokenizer.from_pretrained(head['folder'],local_files_only=True,use_fast=True,trust_remote_code=False)
    else:
        tokenizer=AutoTokenizer.from_pretrained(head['folder'],local_files_only=True,use_fast=True,trust_remote_code=False)
        model=AutoModelForSequenceClassification.from_pretrained(head['folder'],local_files_only=True,trust_remote_code=False,use_safetensors=True).float().to(device).eval()
    reranker=pair_scorer(model,tokenizer,head,device=device,precision=precision)
    with Path(manifest['references']['path']).open(encoding='utf-8') as stream:documents=[json.loads(line) for line in stream if line.strip()]
    return {'manifest':manifest,'retriever':encoder,'reranker':reranker,'documents':documents}


def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=list(VARIANTS),required=True);p.add_argument('--references',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--retriever-run',type=Path)
    args=p.parse_args();manifest=register(args.variant,args.references,args.output,args.retriever_run)
    print(json.dumps({'bundleId':manifest['bundleId'],'variant':manifest['variant'],'state':'OFFLINE_ABLATION_REGISTERED','neuralPredictionExecuted':False,'productActivated':False}))


if __name__=='__main__':main()
