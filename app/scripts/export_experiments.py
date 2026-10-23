"""Read frozen evaluation records and atomically publish a versioned dashboard package.

No model loading, training, threshold selection, raw sentence export, or source writes.
"""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[2]
EXPERIMENT='pawsx-zh-round2'
LABELS={'lr':'逻辑回归','svm':'支持向量机','rf':'随机森林','cnn':'CNN','bilstm':'BiLSTM','bert':'微调BERT'}
CHARTS=['metric_comparison','positive_precision_recall','inference_latency','split_class_counts','model_resource_peaks',
        'confusion_matrix','roc','precision_recall_curve','score_distribution','error_type_counts',
        'train_loss','validation_macro_f1','validation_accuracy','validation_positive_share','validation_time',
        'search_validation_f1','selected_fit_time','search_time_vs_f1','test_protocol_delta','preprocessing_validation_f1']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
def optional_number(value,integer=False):return None if value=='' or value is None else int(value) if integer else float(value)

def export_experiment(frozenRoot:Path,output:Path):
    import numpy as np
    from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,confusion_matrix,roc_auc_score,roc_curve,precision_recall_curve,average_precision_score
    source=Path(frozenRoot).resolve();output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'runtime'):raise ValueError('Experiment packages must stay within project runtime')
    protocol=read(source/'protocol.json');lock=read(source/'selection-lock.json');preprocessing=read(source/'preprocessing.json');freeze=read(source/'freeze-evidence.json')
    if sha(source/'protocol.json')!=lock['protocol_sha256'] or sha(source/'preprocessing.json')!=lock['preprocessing_sha256']:raise ValueError('Frozen protocol checksum differs')
    families=list(LABELS)
    if set(lock['selected'])!=set(families):raise ValueError('Expected six frozen model families')
    files=[source/name for name in ('protocol.json','selection-lock.json','preprocessing.json','freeze-evidence.json','test-summary.csv','search-summary.csv')]
    summaries=csv_rows(source/'test-summary.csv');search_rows=csv_rows(source/'search-summary.csv')
    if len(summaries)!=12 or len(search_rows)!=20:raise ValueError('Frozen six-model/twenty-configuration contract differs')
    selections=lock['selected'];metrics={'sets':{},'splitCounts':{key:{'n':row['n'],'labels':row['labels']} for key,row in protocol['split_manifest'].items()}}
    curves={'sets':{}};history={'split':'validation','runs':[]};search={'selectionMetric':'validation Macro-F1','configurations':[],'preprocessingComparisons':preprocessing['comparisons']}
    for row in search_rows:
        family=row['family'];index=int(row['index']);record={'family':family,'index':index,'config':json.loads(row['config']),
            'validation_macro_f1':float(row['validation_macro_f1']),'fit_or_train_seconds':float(row['fit_or_train_seconds']),
            'best_epoch':optional_number(row['best_epoch'],True),'epochs_run':optional_number(row['epochs_run'],True),
            'peak_allocated_bytes':optional_number(row['peak_allocated_bytes'],True),'peak_working_set_bytes':optional_number(row['peak_working_set_bytes'],True),
            'selected':index==selections[family]['config_index']}
        search['configurations'].append(record)
        result_path=source/f'search/{family}/config-{index}/result.json';files.append(result_path)
        result=read(result_path)
        if result.get('protocol_sha256')!=lock['protocol_sha256']:raise ValueError('Search result protocol mismatch')
        history_path=source/f'search/{family}/config-{index}/history.json'
        if history_path.exists():
            files.append(history_path);epochs=read(history_path)
            if len(epochs)!=record['epochs_run']:raise ValueError('Recorded history length differs from executed epochs')
            history['runs'].append({'family':family,'index':index,'config':record['config'],'selected':record['selected'],'bestEpoch':record['best_epoch'],'epochs':epochs})
    common_identity=None
    for family in families:
        prediction_path=source/f'evaluation/{family}/test-predictions.csv';error_path=source/f'evaluation/{family}/error-summary.json';files.extend((prediction_path,error_path))
        predictions=csv_rows(prediction_path);identity=[(row['id'],row['label'],row['in_no_val_overlap_subset']) for row in predictions]
        if common_identity is None:common_identity=identity
        elif common_identity!=identity:raise ValueError('Model test IDs or labels differ')
        for set_id in ('official_test','test_no_val_overlap'):
            rows=predictions if set_id=='official_test' else [row for row in predictions if row['in_no_val_overlap_subset']=='True']
            truth=np.asarray([int(row['label']) for row in rows]);predicted=np.asarray([int(row['prediction']) for row in rows]);score=np.asarray([float(row['score']) for row in rows])
            if not np.isfinite(score).all() or set(truth)!={0,1}:raise ValueError('Evaluation scores or labels invalid')
            if family!='svm' and ((score<0).any() or (score>1).any()):raise ValueError('Probability score outside range')
            expected=next(row for row in summaries if row['family']==family and row['set']==set_id)
            cm=confusion_matrix(truth,predicted,labels=[0,1]).tolist()
            values={'n':len(rows),'accuracy':float(accuracy_score(truth,predicted)),'positive_precision':float(precision_score(truth,predicted,zero_division=0)),
                'positive_recall':float(recall_score(truth,predicted,zero_division=0)),'positive_f1':float(f1_score(truth,predicted,zero_division=0)),
                'macro_precision':float(precision_score(truth,predicted,average='macro',zero_division=0)),'macro_recall':float(recall_score(truth,predicted,average='macro',zero_division=0)),
                'macro_f1':float(f1_score(truth,predicted,average='macro',zero_division=0)),'roc_auc':float(roc_auc_score(truth,score)),'confusion_matrix':cm,
                'end_to_end_ms_per_pair':float(expected['end_to_end_ms_per_pair']),
                'errors':{'false_positive':cm[0][1],'false_negative':cm[1][0]},'mechanicalErrorAudit':read(error_path) if set_id=='official_test' else None}
            if len(rows)!=int(expected['n']) or cm!=json.loads(expected['confusion_matrix']):raise ValueError('Frozen confusion/count mismatch')
            for key in ('accuracy','positive_precision','positive_recall','positive_f1','macro_f1','roc_auc'):
                if not math.isclose(values[key],float(expected[key]),abs_tol=1e-12):raise ValueError('Frozen metric mismatch: '+family+'/'+set_id+'/'+key)
            metrics['sets'].setdefault(set_id,{'n':len(rows),'models':{}})['models'][family]=values
            fpr,tpr,thresholds=roc_curve(truth,score);precision,recall,pr_thresholds=precision_recall_curve(truth,score)
            minimum=0.0 if family!='svm' else float(score.min());maximum=1.0 if family!='svm' else float(score.max())
            if minimum==maximum:maximum=minimum+1
            edges=np.linspace(minimum,maximum,21)
            curves['sets'].setdefault(set_id,{'models':{}})['models'][family]={
                'scoreType':'decision_margin' if family=='svm' else 'positive_class_probability',
                'roc':{'fpr':fpr.tolist(),'tpr':tpr.tolist(),'thresholds':[float(value) if math.isfinite(value) else None for value in thresholds]},
                'pr':{'precision':precision.tolist(),'recall':recall.tolist(),'thresholds':pr_thresholds.tolist(),'averagePrecision':float(average_precision_score(truth,score))},
                'histogram':{'edges':edges.tolist(),'negative':np.histogram(score[truth==0],edges)[0].tolist(),'positive':np.histogram(score[truth==1],edges)[0].tolist()}}
    source_files=[{'path':path.relative_to(source).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size} for path in sorted(set(files))]
    content_version=digest({'exporterSha256':sha(__file__),'sourceFiles':source_files})
    final=output/EXPERIMENT/'versions'/content_version
    if final.exists():
        manifest=read(final/'manifest.json')
        if sha(final/'manifest.json')!=(final/'READY').read_text().strip() or any(sha(final/name)!=checksum for name,checksum in manifest['artifacts'].items()):raise ValueError('Existing immutable package is corrupt')
    else:
        building=output/EXPERIMENT/'versions'/(content_version+'.building-'+uuid.uuid4().hex);building.mkdir(parents=True,exist_ok=False)
        artifacts={'metrics.json':metrics,'curves.json':curves,'history.json':history,'search.json':search}
        for name,value in artifacts.items():write(building/name,value)
        manifest={'schemaVersion':'1','id':EXPERIMENT,'title':'PAWS-X中文 · 六模型冻结复述分类实验','taskType':'text_pair_classification',
            'dataset':'PAWS-X 中文','datasetRevision':protocol['version'],'frozenAt':datetime.fromisoformat(freeze['frozen_time']).isoformat(),
            'updatedAt':datetime.now(timezone.utc).isoformat(),'contentVersion':content_version,
            'testSets':[{'id':'official_test','label':'官方测试口径（1975对）'},{'id':'test_no_val_overlap','label':'排除验证单句精确重合的嵌套子集（1527对）'}],
            'splitProtocol':{'subsetRule':protocol['subset_rule'],'labelPolicy':protocol['label_policy'],'warning':protocol['warning'],'seed':protocol['seed'],'dataFileHashes':protocol['data_files']},
            'models':[{'id':family,'label':LABELS[family],'selectedConfig':selections[family],'artifactSha256':lock['artifact_sha256'][family],
                       'scoreType':'decision_margin' if family=='svm' else 'positive_class_probability','threshold':0 if family=='svm' else .5,
                       'device':'CPU' if family in ('lr','svm','rf') else 'GPU','hasHistory':any(run['family']==family for run in history['runs'])} for family in families],
            'metricDefinitions':{'accuracy':'正确分类比例','macro_f1':'两类别F1的算术平均','positive_precision':'正类复述Precision','positive_recall':'正类复述Recall','positive_f1':'正类复述F1','macro_precision':'两类别Precision平均','macro_recall':'两类别Recall平均','roc_auc':'基于原始预测分数的ROC AUC'},
            'labels':{'0':'非复述','1':'复述'},'chartCapabilities':CHARTS,'sourceFiles':source_files,
            'notes':['这是PAWS-X复述二分类评价，不是校园复用检索或抄袭判定准确率。','两个测试口径为嵌套集合，不是独立重复试验；标签冲突保留，人工复核未完成。',
                     '所选模型只依据验证集；测试成绩未用于改阈值、配置或训练轮数。','SVM分数为决策间隔，不称概率。其他模型为正类输出分数，不是抄袭概率。',
                     '逐轮历史只画实际记录；CNN/BiLSTM达到3轮上限不证明收敛，BERT所选配置实际2轮、最佳第1轮；未入选退化配置也保留。',
                     '延迟为冻结实验batch8/CPU4线程、不含加载的端到端句对计时，不代表网站吞吐。工作集是进程累计峰值，GPU allocated不是全部驱动显存。'],
            'artifacts':{name:sha(building/name) for name in artifacts}}
        write(building/'manifest.json',manifest);(building/'READY').write_text(sha(building/'manifest.json'));building.rename(final)
    output.mkdir(parents=True,exist_ok=True)
    catalog={'schemaVersion':'1','lastCheckedAt':datetime.now(timezone.utc).isoformat(),'experiments':[{'id':EXPERIMENT,'manifest':(final/'manifest.json').relative_to(output).as_posix(),'manifestSha256':sha(final/'manifest.json')}]}
    temporary=output/'catalog.json.tmp';write(temporary,catalog);temporary.replace(output/'catalog.json')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--frozen-root',type=Path,default=ROOT/'validation/text/round2');parser.add_argument('--output',type=Path,default=ROOT/'runtime/experiments');args=parser.parse_args()
    result=export_experiment(args.frozen_root,args.output);print(json.dumps({'id':result['id'],'contentVersion':result['contentVersion'],'models':len(result['models']),'charts':len(result['chartCapabilities'])}))
