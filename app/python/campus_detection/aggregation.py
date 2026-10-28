"""Pending v3 evidence-window aggregation and version-bound decision calibration.

Coverage is a union of supported context windows, never a copied-character rate.
No existing service calls this module until the v3 integration gates are met.
"""
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

FEATURE_NAMES=['rawQueryCoverage','informativeQueryCoverage','informativeSourceCoverage',
               'meanSupportScore','maximumScore','querySupportSpread','sourceSupportSpread','templateRatio']
ALGORITHM_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _feature_identity(feature_config):
    return _digest({'configuration':feature_config,'featureNames':FEATURE_NAMES,'algorithmSha256':ALGORITHM_SHA256})


def _intervals(values,length):
    rows=[]
    for start,end in values:
        if not isinstance(start,(int,np.integer)) or not isinstance(end,(int,np.integer)) or isinstance(start,bool) or isinstance(end,bool) or not 0<=start<end<=length:raise ValueError('Invalid original-codepoint interval')
        rows.append((int(start),int(end)))
    merged=[]
    for start,end in sorted(rows):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return merged


def _subtract(values,templates):
    output=[]
    for start,end in values:
        cursor=start
        for left,right in templates:
            if right<=cursor or left>=end:continue
            if left>cursor:output.append((cursor,left))
            cursor=max(cursor,right)
            if cursor>=end:break
        if cursor<end:output.append((cursor,end))
    return output


def _length(values):return sum(end-start for start,end in values)


def summarize_sources(pairs,query_length,source_lengths,feature_config,query_templates=(),source_templates=None):
    if query_length<1 or any(length<1 for length in source_lengths.values()):raise ValueError('Invalid query/source lengths')
    threshold=float(feature_config['pairScoreThreshold'])
    score_type=feature_config.get('pairScoreType','CONTENT_CORRESPONDENCE_SCORE')
    if score_type not in {'CONTENT_CORRESPONDENCE_SCORE','LEGACY_SEMANTIC_SCORE','PRETRAINED_RELEVANCE_SCORE'}:raise ValueError('Unsupported reranker score type')
    if not 0<=threshold<=1:raise ValueError('Invalid correspondence score threshold')
    query_templates=_intervals(query_templates,query_length);source_templates=source_templates or {};grouped=defaultdict(dict);identities={}
    for row in pairs:
        key=str(row['sourceRevisionId'])+':'+row.get('sourceKey','BODY')
        identity=(str(row['sourceRevisionId']),row.get('sourceKey','BODY'))
        if key in identities and identities[key]!=identity:raise ValueError('Ambiguous source field identity')
        identities[key]=identity
        if key not in source_lengths:raise ValueError('Missing source field length')
        _intervals([(row['queryStart'],row['queryEnd'])],query_length)
        _intervals([(row['sourceStart'],row['sourceEnd'])],source_lengths[key])
        score=float(row['score'])
        if row.get('scoreType')!=score_type or not math.isfinite(score) or not 0<=score<=1:raise ValueError('Require the bound reranker score type, not an auxiliary cosine/logit')
        identity=(row['queryStart'],row['queryEnd'],row['sourceStart'],row['sourceEnd'])
        grouped[key][identity]=max(grouped[key].get(identity,0.),score)
    sources=[];all_query=[]
    for key,windows in sorted(grouped.items()):
        accepted=[(span,score) for span,score in windows.items() if score>=threshold]
        length=source_lengths[key];templates=_intervals(source_templates.get(key,()),length)
        raw_query=_intervals([(span[0],span[1]) for span,_ in accepted],query_length)
        raw_source=_intervals([(span[2],span[3]) for span,_ in accepted],length)
        informative_query=_subtract(raw_query,query_templates);informative_source=_subtract(raw_source,templates)
        all_query.extend(informative_query)
        supports=[(left,right,score) for span,score in accepted for left,right in _subtract([(span[0],span[1])],query_templates)]
        boundaries=sorted({point for left,right,_ in supports for point in (left,right)});weighted=0.
        for start,end in zip(boundaries,boundaries[1:]):weighted+=(end-start)*max([score for left,right,score in supports if left<=start and right>=end] or [0.])
        features={'rawQueryCoverage':_length(raw_query)/query_length,
                  'informativeQueryCoverage':_length(informative_query)/max(1,query_length-_length(query_templates)),
                  'informativeSourceCoverage':_length(informative_source)/max(1,length-_length(templates)),
                  'meanSupportScore':weighted/max(1,_length(informative_query)),
                  'maximumScore':max([score for _,_,score in supports] or [0.]),
                  'querySupportSpread':(informative_query[-1][1]-informative_query[0][0])/query_length if informative_query else 0.,
                  'sourceSupportSpread':(informative_source[-1][1]-informative_source[0][0])/length if informative_source else 0.,
                  'templateRatio':_length(query_templates)/query_length}
        revision,source_key=identities[key]
        sources.append({'sourceRevisionId':revision,'sourceKey':source_key,'features':features,
                        'queryIntervals':[list(value) for value in informative_query],'sourceIntervals':[list(value) for value in informative_source],
                        'supportedWindowPairs':len(accepted),'featureConfigSha256':_feature_identity(feature_config)})
    return {'sources':sources,'allSourceQueryCoverage':_length(_intervals(all_query,query_length))/max(1,query_length-_length(query_templates)),
            'coverageMeasure':'supported_window_union_not_exact_reused_characters','featureConfigSha256':_feature_identity(feature_config)}


def _feature_vector(features):
    values=np.asarray([features[name] for name in FEATURE_NAMES],dtype=np.float64)
    if not np.isfinite(values).all() or np.any(values<0) or np.any(values>1):raise ValueError('Invalid bounded aggregation features')
    return values


def fit_calibrator(rows,feature_config,partition_sha256,forbidden_events=(),calibration_events=None,minimum_rows=100,minimum_events=30):
    from sklearn.linear_model import LogisticRegression
    if len(rows)<minimum_rows or len(partition_sha256)!=64 or not feature_config.get('modelConfigId'):raise ValueError('Missing calibration scale or identity')
    allowed=set(calibration_events or ());forbidden=set(forbidden_events)
    if not allowed or allowed&forbidden:raise ValueError('Require a frozen calibration event set disjoint from neural/dev/final events')
    events=set();features=[];targets={'whole':[],'local':[]}
    for row in rows:
        if row.get('split')!='calibration' or row.get('queryEventClusterId') not in allowed or row['queryEventClusterId'] in forbidden:raise ValueError('Neural-training/dev/final events cannot fit aggregation calibration')
        if row.get('featureConfigSha256')!=_feature_identity(feature_config):raise ValueError('Cannot relabel features from another model or aggregation policy')
        known=row.get('labelConfidence')=='known' and row.get('labelOrigin') in {'human_verified','controlled_construction','traceable_correspondence'}
        basis=row.get('negativeBasis',{});rule=row.get('labelConfidence')=='supported_rule' and row.get('labelOrigin')=='rule_inferred_noncorrespondence' and basis.get('supported') and len(basis.get('factSpans',[]))>=2 and basis.get('checks') and all(basis['checks'].values())
        if not known and not rule:raise ValueError('Unknown calibration labels are not truth')
        if row.get('wholeTarget') not in (0,1) or row.get('localTarget') not in (0,1) or row['wholeTarget']>row['localTarget']:raise ValueError('Invalid whole/local targets')
        if rule and (row['wholeTarget'] or row['localTarget']):raise ValueError('A supported negative cannot become a positive calibration label')
        events.add(row['queryEventClusterId']);features.append(_feature_vector(row['features']))
        targets['whole'].append(row['wholeTarget']);targets['local'].append(row['localTarget'])
    if len(events)<minimum_events:raise ValueError('Insufficient independent calibration event groups')
    models={};minimum_class=min(20,max(2,minimum_rows//5))
    for name,target in targets.items():
        if min(target.count(0),target.count(1))<minimum_class:raise ValueError('Both calibration classes need sufficient examples')
        model=LogisticRegression(C=1.,solver='lbfgs',max_iter=1000,random_state=20261026).fit(features,target)
        models[name]={'coefficients':model.coef_[0].tolist(),'intercept':float(model.intercept_[0])}
    return {'schemaVersion':'aggregation-calibration-v1','featureNames':FEATURE_NAMES,'featureConfigSha256':_feature_identity(feature_config),'aggregationAlgorithmSha256':ALGORITHM_SHA256,
            'partitionCalibrationSha256':partition_sha256,'calibrationEventSetSha256':_digest(sorted(allowed)),'rows':len(rows),'queryEventGroups':len(events),'models':models,
            'formalCalibrationScaleMet':len(rows)>=100 and len(events)>=30 and all(min(target.count(0),target.count(1))>=20 for target in targets.values()),
            'labelOrigins':sorted({row['labelOrigin'] for row in rows}),'scoreType':'CALIBRATED_DECISION_SCORE_NOT_COPY_PERCENTAGE','productActivated':False}


def validate_calibrator(calibrator,feature_config,thresholds,require_formal_scale=True):
    if calibrator.get('featureNames')!=FEATURE_NAMES or calibrator.get('featureConfigSha256')!=_feature_identity(feature_config) or calibrator.get('aggregationAlgorithmSha256')!=ALGORITHM_SHA256:raise ValueError('Aggregation feature/model identities differ')
    if require_formal_scale and not calibrator.get('formalCalibrationScaleMet'):raise ValueError('Tiny engineering calibrator cannot be used as a formal model')
    if not isinstance(thresholds,dict) or set(thresholds)!={'whole','local'}:raise ValueError('Require both frozen operating thresholds')
    for name in ['whole','local']:
        model=calibrator.get('models',{}).get(name,{})
        coefficients=np.asarray(model.get('coefficients',[]),dtype=float)
        if coefficients.shape!=(len(FEATURE_NAMES),) or not np.isfinite(coefficients).all() or not math.isfinite(model.get('intercept',float('nan'))) or not 0<=thresholds[name]<=1:raise ValueError('Invalid calibration coefficients or operating point')


def decide(features,calibrator,feature_config,thresholds,coverage_status='COMPLETE',require_formal_scale=True):
    validate_calibrator(calibrator,feature_config,thresholds,require_formal_scale)
    if coverage_status not in {'COMPLETE','PARTIAL','FAILED'}:raise ValueError('Unknown processing coverage status')
    values=_feature_vector(features);scores={}
    for name in ['whole','local']:
        model=calibrator['models'][name];coefficients=np.asarray(model['coefficients'],dtype=float)
        logit=float(values@coefficients+model['intercept']);scores[name]=1/(1+math.exp(-logit)) if logit>=0 else math.exp(logit)/(1+math.exp(logit))
    whole=scores['whole']>=thresholds['whole'];local=scores['local']>=thresholds['local'] or whole
    supported=features['informativeQueryCoverage']>0 and features['informativeSourceCoverage']>0
    decision='WHOLE_CORRESPONDENCE' if whole and supported and coverage_status=='COMPLETE' else 'LOCAL_CORRESPONDENCE' if local and supported else 'NO_SUPPORTED_CORRESPONDENCE' if coverage_status=='COMPLETE' else 'INSUFFICIENT_EVIDENCE'
    return {'semanticDecision':decision,'decisionScores':scores,'scoreType':calibrator['scoreType'],'coverageStatus':coverage_status,
            'wholeDecisionDeferred':bool(whole and coverage_status!='COMPLETE'),'noReuseClaim':False,'literalAcceptedCandidateUnchanged':True}
