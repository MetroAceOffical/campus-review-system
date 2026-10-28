"""Bridge actual v3 execution to existing reports and frozen prediction exports."""
import copy
import hashlib
import json
from collections import defaultdict


def merge_report(literal_result, semantic, documents):
    result=copy.deepcopy(literal_result)
    evidence={(str(r['sourceRevisionId']),r.get('sourceKey','BODY')):r for r in result['evidence']}
    for item in evidence.values():
        item['semanticWindows']=[]
        item.pop('semanticSummary',None)
    sources={(str(r['sourceRevisionId']),r.get('sourceKey','BODY')):r for r in documents}
    pairs=defaultdict(list)
    for row in semantic['pairs']:
        key=(str(row['sourceRevisionId']),row.get('sourceKey','BODY'))
        if key not in sources:raise ValueError('Semantic evidence source is absent from the pinned library')
        pairs[key].append(row)
    decisions={(str(r['sourceRevisionId']),r.get('sourceKey','BODY')):r for r in semantic['sourceDecisions']}
    summaries={(str(r['sourceRevisionId']),r.get('sourceKey','BODY')):r for r in semantic['aggregation']['sources']}
    for key,windows in pairs.items():
        source=sources[key]
        if key not in evidence:
            evidence[key]={'evidenceId':'v3-source-'+hashlib.sha256(json.dumps(key).encode()).hexdigest(),
                'evidenceType':'TEXT_SIMILARITY','sourceScope':'LIBRARY','sourceKind':source.get('sourceKind','BODY'),
                'sourceWorkId':str(source['sourceWorkId']),'sourceRevisionId':key[0],'sourceKey':key[1],
                'sourceTitle':source['title'],'sourceUrl':source.get('url'),'sourceMetadata':source.get('sourceMetadata',{}),
                'tfidfScore':0.,'acceptedCandidate':False,'literalSummary':{'matched_characters':0,'query_character_coverage':0.,'longest_match':0},'matches':[]}
        item=evidence[key];summary=summaries[key];decision=decisions.get(key,{})
        item['literalAcceptedCandidate']=item['acceptedCandidate']
        item['semanticWindows']=sorted(windows,key=lambda r:(-r['score'],r['queryStart'],r['sourceStart']))
        item['semanticSummary']={'status':'EVALUATED','suspectedReuse':decision.get('semanticDecision') in {'WHOLE_CORRESPONDENCE','LOCAL_CORRESPONDENCE'},
            'supportingPairs':summary['supportedWindowPairs'],'evaluatedPairs':len(windows),
            'matchedQueryCharacters':sum(b-a for a,b in summary['queryIntervals']),
            'queryCoverage':summary['features']['informativeQueryCoverage'],'sourceCoverage':summary['features']['informativeSourceCoverage'],
            'semanticDecision':decision.get('semanticDecision','PENDING_CALIBRATION'),'decisionScores':decision.get('decisionScores'),
            'scoreType':'CONTENT_CORRESPONDENCE_SCORE'}
    result.update(schemaVersion='text-report-v3',methodVersion='text-v3',evidence=list(evidence.values()),
        coverageStatus=semantic['coverageStatus'],checkedRegions=semantic['checkedRegions'],
        evaluatedPairCount=semantic['evaluatedPairCount'],candidateCount=semantic['candidateCount'],
        semanticConfigId=semantic['configId'],calibrationStatus=semantic['calibrationStatus'],noReuseClaim=False,
        semanticResult=semantic)
    return result


def prediction_record(query,result,method_config_id,reference_sha256,literal_result=None):
    decisions=list(result.get('sourceDecisions',[]));pairs=list(result.get('pairs',[]))
    for item in (literal_result or {}).get('evidence',[]):
        decisions.append({'sourceRevisionId':item['sourceRevisionId'],'sourceKey':item.get('sourceKey','BODY'),'acceptedCandidate':item['acceptedCandidate']})
        for match in item['matches']:
            pairs.append({**match,'sourceRevisionId':item['sourceRevisionId'],'sourceKey':item.get('sourceKey','BODY'),'evidenceKind':'LITERAL_EXACT'})
    scores=[max(row['decisionScores'].values()) for row in decisions if row.get('decisionScores')]
    return {'queryId':query['queryId'],'querySha256':query['querySha256'],'methodConfigId':method_config_id,
        'referenceManifestSha256':reference_sha256,'coverageStatus':result['coverageStatus'],
        'pairs':pairs,'sourceDecisions':decisions,'candidateSources':result.get('candidateSources',[]),
        'featureConfig':result.get('featureConfig',{}),'decisionScore':max(scores) if scores and result['coverageStatus']=='COMPLETE' else None,
        'elapsedMs':result.get('elapsedMs'),'checkedRegions':result.get('checkedRegions',[]),
        'failures':result.get('failures',[]),'evaluatedPairCount':result.get('evaluatedPairCount',0)}
