"""Source-attributed text metrics; missing predictions and unknown truth are explicit."""
import hashlib
import math
from collections import Counter,defaultdict

import numpy as np
from corpus import normalized


def rate(numerator,denominator):
    return {'numerator':int(numerator),'denominator':int(denominator),'value':numerator/denominator if denominator else None}


def _span(row,prefix,length):
    start,end=row[prefix+'Start'],row[prefix+'End']
    if not isinstance(start,int) or isinstance(start,bool) or not isinstance(end,int) or isinstance(end,bool) or not 0<=start<end<=length:raise ValueError('Invalid original-codepoint range')
    return start,end


def _overlap(a,b):return min(a[1],b[1])>max(a[0],b[0])


def _accepted(decision):
    return decision.get('acceptedCandidate') is True or decision.get('semanticHint') is True or decision.get('semanticDecision') in {'WHOLE_CORRESPONDENCE','LOCAL_CORRESPONDENCE'}


def _supported(pair,prediction):
    if pair.get('evidenceKind')=='LITERAL_EXACT':return pair['queryText']==pair['sourceText']
    if 'scoreType' in pair:
        threshold=prediction.get('pairScoreThreshold',prediction.get('featureConfig',{}).get('pairScoreThreshold'))
        score=pair.get('score')
        return pair['scoreType'] in {'CONTENT_CORRESPONDENCE_SCORE','LEGACY_SEMANTIC_SCORE'} and isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and isinstance(threshold,(int,float)) and 0<=threshold<=score<=1
    return pair.get('supported') is True


def _families(records):
    parent=list(range(len(records)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    seen={}
    for index,row in enumerate(records):
        for event in row['eventClusterIds']:
            if event in seen:parent[find(index)]=find(seen[event])
            else:seen[event]=index
    groups=defaultdict(list)
    for i,row in enumerate(records):groups[find(i)].append(row)
    return list(groups.values())


def _rates(records):
    positive=[r for r in records if r['expectedSourceIds']]
    normal=[r for r in records if r['closedNormal']]
    multi=[r for r in positive if r['category']=='multi_source']
    values={'correctSourceEvidenceRate':rate(sum(r['correctSources']>0 for r in positive),len(positive)),
            'multiSourceAllFoundRate':rate(sum(r['correctSources']==len(r['expectedSourceIds']) for r in multi),len(multi)),
            'normalAnySourceFalsePromptRate':rate(sum(r['anySourceAlert'] for r in normal),len(normal)),
            'normalFalsePromptWorstCaseRate':rate(sum(r['anySourceAlert'] or r['coverageStatus']!='COMPLETE' for r in normal),len(normal)),
            'validEvidenceOffsets':rate(sum(r['validEvidence'] for r in records),sum(r['totalEvidence'] for r in records))}
    for k in [1,5,10,20,30]:
        values['correctSourceRecallAt'+str(k)]=rate(sum(r['retrievedAt'][k]>0 for r in positive),len(positive))
        values['sourceMicroRecallAt'+str(k)]=rate(sum(r['retrievedAt'][k] for r in positive),sum(len(r['expectedSourceIds']) for r in positive))
        values['multiSourceAllRetrievedAt'+str(k)]=rate(sum(r['retrievedAt'][k]==len(r['expectedSourceIds']) for r in multi),len(multi))
    return values


def _precision_recall(records):
    eligible=[r for r in records if r['expectedSourceIds'] or r['closedNormal']]
    measured=[r for r in eligible if r['decisionScore'] is not None]
    base={'eligibleQueries':len(eligible),'measuredScores':len(measured),'curve':None,
          'scope':'Any-correspondence decision score, not correct-source attribution; no missing score is invented.'}
    if len(measured)!=len(eligible):return {**base,'status':'MISSING_REAL_SCORES'}
    positives=sum(bool(r['expectedSourceIds']) for r in measured)
    if not positives or positives==len(measured):return {**base,'status':'INSUFFICIENT_CLASSES'}
    groups=defaultdict(list)
    for row in measured:groups[row['decisionScore']].append(row)
    curve=[];tp=fp=0
    for threshold,rows in sorted(groups.items(),reverse=True):
        tp+=sum(bool(r['expectedSourceIds']) for r in rows);fp+=sum(not r['expectedSourceIds'] for r in rows)
        curve.append({'threshold':threshold,'precision':tp/(tp+fp),'recall':tp/positives,'truePositives':tp,'falsePositives':fp})
    return {**base,'status':'COMPLETE_OBSERVED_SCORES','curve':curve}


def score_predictions(queries,predictions,references,method_config_id,*,reference_sha256,bootstrap_resamples=1000):
    if not isinstance(method_config_id,str) or not method_config_id or len(reference_sha256)!=64:raise ValueError('Require frozen method/reference identities')
    if not isinstance(bootstrap_resamples,int) or not 1<=bootstrap_resamples<=10000:raise ValueError('Invalid event-bootstrap resample count')
    refs={};reference_ids=set()
    for source in references:
        key=(str(source['sourceRevisionId']),source.get('sourceKey','BODY'))
        if key in refs:raise ValueError('Duplicate reference revision/field')
        refs[key]=source;reference_ids.add(key[0])
    by_query={row['queryId']:row for row in queries}
    if len(by_query)!=len(queries):raise ValueError('Repeated protocol query identities')
    predicted={}
    for row in predictions:
        qid=row['queryId']
        if qid in predicted or qid not in by_query:raise ValueError('Duplicate or foreign prediction identity')
        if row.get('methodConfigId')!=method_config_id or row.get('querySha256')!=by_query[qid]['querySha256'] or row.get('referenceManifestSha256')!=reference_sha256:raise ValueError('Prediction method/query/reference identity differs')
        predicted[qid]=row
    records=[]
    for query in queries:
        text=query['query'];expected={str(key) for key in query['expectedSourceIds']};scope=query['truthScope']
        if hashlib.sha256(text.encode()).hexdigest()!=query['querySha256'] or not query.get('eventClusterIds'):raise ValueError('Invalid query text/event provenance')
        if not expected.issubset(reference_ids):raise ValueError('Expected source not present in frozen reference bank')
        if scope not in {'known_positive_sources_only','closed_reference_set','unknown_negative_scope'}:raise ValueError('Unknown truth scope')
        if expected and query.get('labelConfidence')!='known':raise ValueError('Unknown positive labels cannot produce source recall')
        if not expected and scope=='known_positive_sources_only':raise ValueError('A positive-only scope cannot silently become normal truth')
        closed_normal=False;known_wrong=set()
        if scope=='closed_reference_set':
            negative=query.get('negativeScope',{});excluded={str(v) for v in negative.get('excludedSourceRevisionIds',[])}
            supported={str(v) for v in negative.get('supportedNegativeSources',[])}
            if negative.get('auditVerified') is not True or negative.get('referenceManifestSha256')!=reference_sha256 or not excluded.issubset(reference_ids) or expected&excluded or supported!=reference_ids-expected-excluded:raise ValueError('Negative truth does not cover this complete reference scope')
            known_wrong=supported;closed_normal=not expected
        truth=defaultdict(list)
        for mapping in query.get('sourceMappings',[]):
            key=(str(mapping['sourceRevisionId']),mapping.get('sourceKey','BODY'))
            if key not in refs or key[0] not in expected:raise ValueError('Truth mapping source identity differs')
            qspan=_span(mapping,'query',len(text));sspan=_span(mapping,'source',len(refs[key]['text']))
            a,b=text[qspan[0]:qspan[1]],refs[key]['text'][sspan[0]:sspan[1]];kind=mapping['mappingType']
            if kind not in {'EXACT_SEGMENT','NORMALIZED_EXACT_WHOLE','PARAPHRASE_SEGMENT'} or kind=='EXACT_SEGMENT' and a!=b or kind=='NORMALIZED_EXACT_WHOLE' and normalized(a)!=normalized(b):raise ValueError('Truth mapping content does not reproduce')
            truth[key].append((qspan,sspan))
        if expected!={key[0] for key in truth}:raise ValueError('Every expected source requires original-range truth')
        prediction=predicted.get(query['queryId'],{});status=prediction.get('coverageStatus','FAILED')
        if status not in {'COMPLETE','PARTIAL','FAILED'}:status='FAILED'
        accepted_fields={(str(row['sourceRevisionId']),row.get('sourceKey','BODY')) for row in prediction.get('sourceDecisions',[]) if _accepted(row)}
        accepted={key[0] for key in accepted_fields}
        valid=total=0;correct=set()
        for pair in prediction.get('pairs',[]):
            total+=1;key=(str(pair.get('sourceRevisionId')),pair.get('sourceKey','BODY'))
            try:
                if key not in refs:raise ValueError('Unknown evidence source field')
                qspan=_span(pair,'query',len(text));sspan=_span(pair,'source',len(refs[key]['text']))
                if pair.get('queryText')!=text[qspan[0]:qspan[1]] or pair.get('sourceText')!=refs[key]['text'][sspan[0]:sspan[1]]:raise ValueError('Evidence text does not reconstruct immutable ranges')
                valid+=1
                if status!='FAILED' and key in accepted_fields and _supported(pair,prediction) and any(_overlap(qspan,q) and _overlap(sspan,s) for q,s in truth.get(key,())):correct.add(key[0])
            except (ValueError,KeyError,TypeError):continue
        ranked=list(dict.fromkeys(str(row['sourceRevisionId']) for row in prediction.get('candidateSources',[])))
        score=prediction.get('decisionScore')
        if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score) or not 0<=score<=1:score=None
        elapsed=prediction.get('elapsedMs')
        if not isinstance(elapsed,(int,float)) or isinstance(elapsed,bool) or not math.isfinite(elapsed) or elapsed<0:elapsed=None
        records.append({'queryId':query['queryId'],'category':query['category'],'eventClusterIds':query['eventClusterIds'],
                        'expectedSourceIds':sorted(expected),'truthScope':scope,'closedNormal':closed_normal,'coverageStatus':status,
                        'missingPrediction':query['queryId'] not in predicted,'correctSources':len(correct),'anySourceAlert':bool(accepted),
                        'knownWrongSourceAcceptances':len(accepted&known_wrong),'unknownExtraSourceAcceptances':len(accepted-expected-known_wrong),
                        'totalEvidence':total,'validEvidence':valid,'decisionScore':score,'elapsedMs':elapsed,
                        'retrievedAt':{k:len(set(ranked[:k])&expected) for k in [1,5,10,20,30]},
                        'labelOrigin':query.get('labelOrigin','unknown')})
    values=_rates(records);families=_families(records);rng=np.random.default_rng(20261027);samples=defaultdict(list)
    for _ in range(bootstrap_resamples):
        chosen=[row for index in rng.integers(0,len(families),len(families)) for row in families[index]] if families else []
        for name,value in _rates(chosen).items():
            if value['value'] is not None:samples[name].append(value['value'])
    timings=[r['elapsedMs'] for r in records if r['elapsedMs'] is not None]
    return {'schemaVersion':'source-attributed-text-metrics-v1','queries':len(records),'predictionsProvided':len(predictions),
            'missingPredictions':sum(r['missingPrediction'] for r in records),'failedQueries':sum(r['coverageStatus']=='FAILED' for r in records),
            'partialQueries':sum(r['coverageStatus']=='PARTIAL' for r in records),'unscoredNormalQueries':sum(not r['expectedSourceIds'] and not r['closedNormal'] for r in records),
            'invalidEvidence':sum(r['totalEvidence']-r['validEvidence'] for r in records),
            'unknownExtraSourceAcceptances':sum(r['unknownExtraSourceAcceptances'] for r in records),
            'knownWrongSourceAcceptances':sum(r['knownWrongSourceAcceptances'] for r in records),
            'multiSourceExpectedSources':sum(len(r['expectedSourceIds']) for r in records if r['category']=='multi_source'),
            'automaticQueryFamilies':len(families),'rates':values,
            'familyBootstrap95':{name:{'interval':np.quantile(samples[name],[.025,.975]).tolist() if samples[name] else None,
                                       'validResamples':len(samples[name]),'requestedResamples':bootstrap_resamples} for name in values},
            'byCategory':{name:{'queries':len(rows),'rates':_rates(rows)} for name,rows in _group(records,'category').items()},
            'byLabelOrigin':{name:{'queries':len(rows),'rates':_rates(rows)} for name,rows in _group(records,'labelOrigin').items()},
            'latencyMs':{'measuredQueries':len(timings),'median':float(np.median(timings)) if timings else None,'p95':float(np.quantile(timings,.95)) if timings else None},
            'precisionRecall':_precision_recall(records),'methodConfigId':method_config_id,'referenceManifestSha256':reference_sha256,
            'qualityAccepted':False,'scope':'Failures stay in denominators; unknown normal/extra-source truth is separate. Bootstrap connects queries sharing any parent event, including multi-source bridges.',
            'queryResults':records}


def _group(records,key):
    result=defaultdict(list)
    for row in records:result[row[key]].append(row)
    return dict(sorted(result.items()))
