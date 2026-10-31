"""Immutable six-classifier release over one shared retrieval/alignment plan."""
from collections import Counter
from copy import deepcopy
import json,math,time
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256

ROOT=Path(__file__).resolve().parents[3]
FAMILIES=('lr','svm','rf','cnn','bilstm','bert')

def fit_threshold(labels,scores,family):
    if len(labels)!=len(scores) or set(labels)!={0,1} or any(not math.isfinite(s) for s in scores):raise ValueError('验证材料须含两个类别的有效分数')
    if family!='svm' and any(not 0<=s<=1 for s in scores):raise ValueError('概率分数超出范围')
    ordered=sorted(zip(scores,labels),reverse=True);positives=sum(labels);negatives=len(labels)-positives
    tp=fp=0;i=0
    initial=(2*negatives/(2*negatives+positives))/2
    best=((initial,0,0),dict(threshold=math.nextafter(float(ordered[0][0]),math.inf),macroF1=initial,f1=0.0,precision=0.0,recall=0.0,falsePositiveRate=0.0,confusionMatrix=[[negatives,0],[positives,0]]))
    while i<len(ordered):
        score=ordered[i][0]
        while i<len(ordered) and ordered[i][0]==score:
            if ordered[i][1]:tp+=1
            else:fp+=1
            i+=1
        threshold=(score+ordered[i][0])/2 if i<len(ordered) else score
        fn=positives-tp;tn=negatives-fp
        precision=tp/max(1,tp+fp);recall=tp/positives;f1=2*tp/max(1,2*tp+fp+fn);negative_f1=2*tn/max(1,2*tn+fp+fn)
        macro=(f1+negative_f1)/2;fpr=fp/negatives
        quality=(macro,-fpr,recall)
        if best is None or quality>best[0]:best=(quality,dict(threshold=threshold,macroF1=macro,f1=f1,precision=precision,recall=recall,falsePositiveRate=fpr,confusionMatrix=[[tn,fp],[fn,tp]]))
    fit=best[1];distances=sorted(abs(s-fit['threshold']) for s in scores)
    return dict(fit,rows=len(labels),scoreType='margin' if family=='svm' else 'probability',scale=max(1e-6,distances[len(distances)//2]),selectionPartition='validation',method='shared-validation-macro-f1-v1')

def decision_scores(scores,fit):
    threshold=fit['threshold']
    if fit['scoreType']=='probability':
        return [(.5*s/threshold if s<threshold and threshold>0 else .5+.5*(s-threshold)/max(1e-12,1-threshold)) if threshold<1 else .5*s/threshold for s in scores]
    return [1/(1+math.exp(-max(-40,min(40,(s-threshold)/fit['scale'])))) for s in scores]

def recommend(members):
    return max(members,key=lambda m:(m['calibration']['macroF1'],m['calibration']['recall'],-m['calibration']['falsePositiveRate'],FAMILIES.index(m['family'])))['family']

def calibrated_metrics(rows,fit):
    from campus_workbench.training import metric_report
    metrics,_=metric_report(rows,decision_scores([r['score'] for r in rows],fit),'lr')
    return metrics

def inference_dependencies():
    names=['app/python/campus_workbench/training.py','app/python/campus_workbench/preparation.py','app/python/campus_workbench/training_identities.py','app/python/campus_workbench/curated_bundles.py','app/python/campus_shared/contracts.py','validation/text/round2.py','validation/text/run_validation.py']
    return {name:file_sha256(ROOT/name) for name in names}

def prepare(config,output,verify_member):
    from campus_workbench.preparation import prepared,write_json
    from campus_workbench.training import load_model
    from .models import configurations
    from .contextual_text import configuration as contextual
    from .text_refinement import configuration as refined
    from .mutual_text import configuration as mutual
    output=Path(output);members=[];files={};common=None;rows_identity=None
    if len(config['members'])!=6 or {m['family'] for m in config['members']}!=set(FAMILIES):raise ValueError('模型组须包含六种不同算法')
    for item in config['members']:
        folder=Path(item['model']).resolve();preparation=Path(item['preparation']).resolve()
        for path,field in [(folder/'manifest.json','modelManifestSha256'),(Path(item['evaluation']),'evaluationSha256'),(preparation/'manifest.json','preparationSha256')]:
            if file_sha256(path)!=item[field]:raise ValueError('登记时选择的模型、评价或划分工件已变化')
        manifest=load_model(folder)
        if not folder.is_relative_to(ROOT/'runtime/workbench/computations') or manifest['family']!=item['family']:raise ValueError('模型组成员身份不一致')
        if manifest['family']=='bert' and manifest['parameters']['max_length']<128:raise ValueError('正文审核 BERT 最大输入长度须至少128')
        _,partitions=prepared(preparation)
        identity=(manifest['inputSha256'],manifest['preparationSha256'],file_sha256(preparation/'validation.jsonl'),file_sha256(preparation/'test.jsonl'))
        if common is not None and common!=identity:raise ValueError('六模型须使用同一数据及样本划分')
        common=identity
        if file_sha256(preparation/'manifest.json')!=manifest['preparationSha256']:raise ValueError('模型准备版本已变化')
        verification=verify_member({**item,'action':'MODEL','evaluationPreparation':str(preparation)})
        path=folder/'validation-predictions.jsonl'
        if manifest['artifacts'].get(path.name)!=file_sha256(path):raise ValueError('验证逐条预测不可核验')
        rows=[json.loads(s) for s in path.read_text(encoding='utf8').splitlines() if s]
        actual_identity=[(str(r['id']),r['sentence1'],r['sentence2'],int(r['label'])) for r in rows]
        expected_identity=[(str(r['id']),r['sentence1'],r['sentence2'],int(r['label'])) for r in partitions['validation']]
        if actual_identity!=expected_identity or rows_identity is not None and rows_identity!=actual_identity:raise ValueError('六模型验证材料不一致')
        rows_identity=actual_identity
        fit=fit_threshold([int(r['label']) for r in rows],[r['score'] for r in rows],item['family'])
        test_rows=[json.loads(s) for s in (Path(item['evaluation']).parent/'predictions.jsonl').read_text(encoding='utf8').splitlines() if s]
        calibrated_test=calibrated_metrics(test_rows,fit)
        members.append(dict(family=item['family'],modelId=item['modelId'],evaluationId=item['evaluationId'],modelFolder=folder.relative_to(ROOT).as_posix(),modelManifestSha256=file_sha256(folder/'manifest.json'),calibration=fit,validation=manifest['validation'],test=verification['metrics'],calibratedTest=calibrated_test))
        files.update(verification['verifiedFiles'])
        for p in (preparation/'manifest.json',preparation/'validation.jsonl',preparation/'test.jsonl'):files[p.relative_to(ROOT).as_posix()]=file_sha256(p)
    primary=recommend(members);write_json(output/'bundle-calibration.json',dict(members=members,primaryFamily=primary,selectionPartition='validation'))
    text,image=configurations();text=mutual(refined(contextual(text)))
    implementation=['six_model_bundle.py','contextual_text.py','text_refinement.py','mutual_text.py','semantic.py','text.py','reference_versions.py','models.py']
    files.update(inference_dependencies())
    for name in implementation:
        p=Path(__file__).parent/name;files[p.relative_to(ROOT).as_posix()]=file_sha256(p)
    p=output/'bundle-calibration.json';files[p.relative_to(ROOT).as_posix()]=file_sha256(p)
    binding={'bundleId':config['bundleId'],'primaryFamily':primary,'members':[{k:m[k] for k in ('family','modelId','evaluationId','modelManifestSha256')} for m in members],'calibrationSha256':file_sha256(p),'selectionPartition':'validation'}
    text.update(schemaVersion='text-six-model-v1',method='six-model-shared-context-20261031',sixModelBundle=binding)
    text.pop('configId');text['configId']='text-'+digest_json(text)
    descriptor=dict(schemaVersion='six-model-adapter-v1',textConfig=text,members=members,verifiedFiles=files)
    path=output/'adapter.json';write_json(path,descriptor)
    return dict(scene='TEXT_REUSE',bundleId=config['bundleId'],primaryFamily=primary,members=members,textConfig=text,imageConfig=image,textAdapter=dict(path=path.relative_to(ROOT).as_posix(),sha256=file_sha256(path)),verifiedFiles={**files,path.relative_to(ROOT).as_posix():file_sha256(path)})

def verify_descriptor(path,expected):
    path=Path(path).resolve()
    if path.name!='adapter.json' or path.parent.parent!=ROOT/'runtime/delivery/releases' or file_sha256(path)!=expected:raise ValueError('模型组适配身份无效')
    saved=json.loads(path.read_text(encoding='utf8'));config=saved['textConfig']
    if saved.get('schemaVersion')!='six-model-adapter-v1' or config.get('schemaVersion')!='text-six-model-v1':raise ValueError('模型组适配格式无效')
    if config['configId']!='text-'+digest_json({k:v for k,v in config.items() if k!='configId'}):raise ValueError('模型组配置摘要不一致')
    if len(saved['members'])!=6 or {m['family'] for m in saved['members']}!=set(FAMILIES):raise ValueError('模型组不完整')
    for name,sha in saved['verifiedFiles'].items():
        target=(ROOT/name).resolve()
        if Path(name).is_absolute() or not any(target.is_relative_to(ROOT/p) for p in ('app','runtime','validation')) or file_sha256(target)!=sha:raise ValueError('模型组已核验工件发生变化')
    return saved

def register(models,path,expected):
    saved=verify_descriptor(path,expected);config=saved['textConfig'];key=config['configId']
    models.setdefault('sixModelBundles',{})[key]=saved
    models.setdefault('textConfigs',{})[key]=config
    return config

def predict_pairs(descriptor,rows):
    from campus_workbench.training import predict
    saved=verify_descriptor(ROOT/descriptor['path'],descriptor['sha256']);results=[]
    for member in saved['members']:
        raw=predict(ROOT/member['modelFolder'],rows,lambda _:None,device_override='cpu');mapped=decision_scores([r['score'] for r in raw],member['calibration'])
        results.append(dict(family=member['family'],modelId=member['modelId'],rows=[{**row,'rawScore':row['score'],'score':score,'predicted':int(score>=.5),'scoreType':'decision'} for row,score in zip(raw,mapped)]))
    primary=next(r for r in results if r['family']==saved['textConfig']['sixModelBundle']['primaryFamily'])
    return dict(rows=primary['rows'],bundleResults=results,primaryFamily=primary['family'],bundleId=saved['textConfig']['sixModelBundle']['bundleId'],device='cpu')

def detect(request,library,models):
    from .contextual_text import detect as aligned
    from .semantic import semantic_summary
    from .text_refinement import refine
    from .mutual_text import apply_guard
    from campus_workbench.training import predict
    import torch
    started=time.perf_counter();key=request['configId'];saved=models['sixModelBundles'][key];captured=[]
    def collect(pairs):captured.extend(pairs);return [0.0]*len(pairs)
    # Retrieval and alignment execute once, before any classifier is scored.
    template=aligned(request,library,{**models,'predictBert':collect});results=[]
    for member in saved['members']:
        tick=time.perf_counter();folder=ROOT/member['modelFolder']
        if file_sha256(folder/'manifest.json')!=member['modelManifestSha256']:raise ValueError('模型组成员工件发生变化')
        scored=predict(folder,captured,lambda _:None,device_override='cuda' if torch.cuda.is_available() and member['family'] in ('cnn','bilstm','bert') else 'cpu') if captured else []
        if len(scored)!=len(captured):raise ValueError('模型组评分数量不一致')
        mapped=decision_scores([r['score'] for r in scored],member['calibration'])
        score_map={(row['sentence1'],row['sentence2']):value for row,value in zip(captured,mapped)}
        result=deepcopy(template)
        for evidence in result['evidence']:
            for window in evidence.get('semanticWindows',[]):window['score']=score_map[(window['queryText'],window['sourceText'])]
            windows=evidence.get('semanticWindows',[])
            if windows:evidence['semanticSummary']={**semantic_summary(windows,result['actualConfig']['contextPolicy']),'status':'EVALUATED','evaluatedPairs':len(windows)}
        if result['status']=='COMPLETED':refine(result,library,request['text']);apply_guard(result)
        warnings=[e for e in result['evidence'] if e.get('acceptedCandidate') or e.get('semanticSummary',{}).get('suspectedReuse')]
        result['modelBinding']=dict(bundleId=saved['textConfig']['sixModelBundle']['bundleId'],family=member['family'],modelId=member['modelId'],modelManifestSha256=member['modelManifestSha256'])
        results.append(dict(family=member['family'],modelId=member['modelId'],primary=member['family']==saved['textConfig']['sixModelBundle']['primaryFamily'],warningSources=len({e['sourceWorkId'] for e in warnings}),suspectedReuse=bool(warnings),scoredPairs=len(scored),elapsedMs=(time.perf_counter()-tick)*1000,calibration=member['calibration'],result=result))
    primary=next(r for r in results if r['primary']);output=deepcopy(primary['result'])
    output.update(bundleResults=results,bundleId=saved['textConfig']['sixModelBundle']['bundleId'],primaryFamily=primary['family'],sharedCandidatePlan=True,elapsedMs=(time.perf_counter()-started)*1000)
    return output
