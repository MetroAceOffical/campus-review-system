"""Calibrate through the same frozen 128-token scorer used by the service.

The original web_bert.py is retained unchanged so registered v1 configurations
and their implementation hashes remain replayable.
"""
import copy,json,math
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256
from campus_workbench.preparation import prepared,write_json
from .models import ROOT
from . import web_bert as frozen


def choose_threshold(labels,scores):
    from sklearn.metrics import f1_score,precision_score,recall_score
    if len(labels)!=len(scores) or set(labels)!={0,1} or not all(math.isfinite(s) and 0<=s<=1 for s in scores):raise ValueError('校准集须包含两类有效分数')
    ordered=sorted(set(scores))
    candidates=[(a+b)/2 for a,b in zip(ordered,ordered[1:])]
    candidates.extend([ordered[0]/2,(ordered[-1]+1)/2,.5])
    candidates=[t for t in candidates if 0<t<1 and t not in ordered]
    def quality(t):
        predicted=[int(s>=t) for s in scores]
        return f1_score(labels,predicted,average='macro',zero_division=0),precision_score(labels,predicted,zero_division=0),-abs(t-.5)
    threshold=max(candidates,key=quality);predicted=[int(s>=threshold) for s in scores]
    return {'method':'inference-128-validation-midpoint-v2','threshold':threshold,'rows':len(scores),'maxTokens':128,'batchSize':8,'padding':'longest','precisionMode':'FP32',
            'minimumValidationMargin':min(abs(s-threshold) for s in scores),'macroF1':float(f1_score(labels,predicted,average='macro',zero_division=0)),
            'precision':float(precision_score(labels,predicted,zero_division=0)),'recall':float(recall_score(labels,predicted,zero_division=0)),
            'scoreMeaning':'MONOTONE_CALIBRATED_DECISION_SCORE','selectionPartition':'validation'}


def prepare(config,output,pair_verification):
    output=Path(output)
    # Reuse the frozen package/compatibility builder. Its initial calibration is
    # private to this process and replaced before this version can be registered.
    result=frozen.prepare(config,output,pair_verification)
    descriptor=json.loads((output/'adapter.json').read_text(encoding='utf-8'))
    original=descriptor['calibration']
    def write_package(fit):
        write_json(output/'calibration.json',fit)
        descriptor['calibration']=fit
        files=descriptor['verifiedFiles'];files[(output/'calibration.json').relative_to(ROOT).as_posix()]=file_sha256(output/'calibration.json')
        files[Path(__file__).relative_to(ROOT).as_posix()]=file_sha256(Path(__file__))
        text=descriptor['textConfig'];text['webBert']['calibrationSha256']=file_sha256(output/'calibration.json')
        text['webBert']['calibrationProtocolSha256']=file_sha256(Path(__file__))
        text['webBert']['calibrationProtocol']='inference-128-validation-midpoint-v2'
        text.pop('configId',None);text['configId']='text-'+digest_json(text)
        write_json(output/'adapter.json',descriptor)
    write_package({**original,'threshold':.5,'method':'PRIVATE_IDENTITY_SCORER'})
    models={'textConfigs':{}}
    selected=frozen.register(models,output/'adapter.json',file_sha256(output/'adapter.json'))
    _,partitions=prepared(config['preparation']);rows=partitions['validation']
    # A 0.5 mapping is exactly the raw-score identity. This calls the actual
    # service scorer, including longest padding and 128-token truncation, even
    # when the selected model was trained with longer input sequences.
    raw=models['webBertModels'][selected['configId']]['predictBert'](rows)
    fit=choose_threshold([int(row['label']) for row in rows],raw)
    fit.update({key:original[key] for key in ('dataSha256','modelManifestSha256')})
    write_package(fit)
    result.update(textConfig=copy.deepcopy(descriptor['textConfig']),calibration=fit,textAdapter={'path':(output/'adapter.json').relative_to(ROOT).as_posix(),'sha256':file_sha256(output/'adapter.json')},verifiedFiles={**descriptor['verifiedFiles'],(output/'adapter.json').relative_to(ROOT).as_posix():file_sha256(output/'adapter.json')})
    return result
