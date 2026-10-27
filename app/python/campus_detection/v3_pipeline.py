"""Opt-in v3 correspondence analysis; not registered in the default service.

Literal acceptance remains the caller's independent result. This kernel uses
literal source ranks only for candidate fusion and never rewrites that result.
"""
import collections
import math
import time
from pathlib import Path

from campus_detection import retrieval,alignment,aggregation

DEFAULT_POLICY={'densePerBlock':10,'sourcePool':30,'sourcesPerBlock':3,'pairBudget':2048,
                'jointTokens':512,'pairScoreThreshold':.5}


def _policy(changes):
    changes=changes or {}
    if set(changes)-set(DEFAULT_POLICY):raise ValueError('Unknown v3 policy field')
    policy={**DEFAULT_POLICY,**changes}
    for key in ['densePerBlock','sourcePool','sourcesPerBlock','pairBudget','jointTokens']:
        if not isinstance(policy[key],int) or isinstance(policy[key],bool) or not 1<=policy[key]<=DEFAULT_POLICY[key]:raise ValueError('Invalid v3 processing budget')
    if not isinstance(policy['pairScoreThreshold'],(int,float)) or not math.isfinite(policy['pairScoreThreshold']) or not 0<=policy['pairScoreThreshold']<=1:raise ValueError('Invalid task support threshold')
    return policy


def _reference_context(index,documents):
    if retrieval._digest(documents)!=index['manifest']['inputManifestSha256']:raise ValueError('Library documents differ from immutable dense-index inputs')
    fields={};by_revision=collections.defaultdict(set)
    for document in documents:
        key=(str(document['sourceRevisionId']),document.get('sourceKey','BODY'))
        if key in fields:raise ValueError('Duplicate source revision/field')
        fields[key]={'text':document['text'],'blocks':[]}
        text=document['text'];by_revision[key[0]].update(text[i:i+16] for i in range(max(0,len(text)-15)))
    frequency=collections.Counter()
    for grams in by_revision.values():frequency.update(grams)
    templates={gram for gram,count in frequency.items() if count>=max(3,math.ceil(.1*len(by_revision)))}
    lengths={};identities={}
    for block in index['blocks']:
        identity=(str(block['sourceRevisionId']),block['sourceKey'])
        if identity not in fields:raise ValueError('Dense block source is absent from library')
        context=fields[identity]
        if block['text']!=context['text'][block['start']:block['end']]:raise ValueError('Dense block no longer reconstructs source')
        context['blocks'].append(block)
        key=identity[0]+':'+identity[1]
        if key in identities and identities[key]!=identity:raise ValueError('Ambiguous composite source identity')
        identities[key]=identity;lengths[key]=len(context['text'])
    return fields,lengths,templates


def _template_intervals(text,templates):
    rows=[]
    for start in range(max(0,len(text)-15)):
        if text[start:start+16] not in templates:continue
        end=start+16
        if rows and start<=rows[-1][1]:rows[-1]=(rows[-1][0],max(end,rows[-1][1]))
        else:rows.append((start,end))
    return rows


def analyze_correspondence(text,index,documents,retriever,reranker,*,literal_hits=(),exclude_manuscript_id=None,policy=None,calibrator=None,thresholds=None):
    started=time.perf_counter();policy=_policy(policy)
    if not isinstance(text,str) or not text.strip() or len(text)>10000:raise ValueError('Require 1..10000 original query codepoints')
    if calibrator is not None and thresholds is None:raise ValueError('A formal calibrator requires frozen operating thresholds')
    if 'tokenizer' not in reranker:raise ValueError('Bind the actual task-model tokenizer; do not substitute retrieval tokenization')
    manifest=index['manifest'];chunk=manifest['configuration']['chunk']
    if manifest['configuration']['encoder']!=retriever['identity']:raise ValueError('Query encoder and dense-index feature identities differ')
    if chunk!={'tokens':192,'overlap':48,'coordinates':'ORIGINAL_CODEPOINTS'}:raise ValueError('Require the fixed v3 index chunk policy')
    fields,source_lengths,templates=_reference_context(index,documents)
    configuration={'schemaVersion':'v3-correspondence-policy-v1','denseFeatureSpaceId':manifest['featureSpaceId'],
                   'taskModelConfigId':reranker['configuration']['configId'],'policy':policy,
                   'templatePolicy':{'gramCodepoints':16,'minimumSourceRevisions':3,'sourceRevisionRatio':.1},
                   'algorithmSha256':{name:retrieval._sha(Path(module.__file__)) for name,module in
                                      [('retrieval',retrieval),('alignment',alignment),('aggregation',aggregation)]},
                   'pipelineAlgorithmSha256':retrieval._sha(Path(__file__))}
    config_id='v3-'+retrieval._digest(configuration)
    feature_config={'modelConfigId':config_id,'pairScoreThreshold':policy['pairScoreThreshold']}
    if calibrator is not None:aggregation.validate_calibrator(calibrator,feature_config,thresholds)
    all_revisions={str(document['sourceRevisionId']) for document in documents}
    excluded={str(document['sourceRevisionId']) for document in documents if exclude_manuscript_id is not None and document.get('manuscriptId') is not None and str(document['manuscriptId'])==str(exclude_manuscript_id)}
    allowed=all_revisions-excluded
    literal=[];seen_literal=set()
    for hit in literal_hits:
        revision=str(hit['sourceRevisionId'])
        if revision not in all_revisions:raise ValueError('Literal source rank belongs to another library')
        if revision in allowed and revision not in seen_literal:literal.append(hit);seen_literal.add(revision)
    query_blocks=retrieval.token_blocks(text,retriever['tokenizer'],tokens=192,overlap=48)
    if not query_blocks:raise ValueError('No encodable query regions')
    query_vectors=retriever['encode']([row['text'] for row in query_blocks])
    dense=retrieval.search_dense(index,query_vectors,top_k=policy['densePerBlock'],exclude_manuscript_id=exclude_manuscript_id,allowed_source_revision_ids=allowed)
    pool=retrieval.hybrid_sources(literal[:policy['sourcePool']],[hit for values in dense for hit in values],maximum=policy['sourcePool'])
    hits=retrieval.search_dense(index,query_vectors,top_k=policy['sourcesPerBlock'],exclude_manuscript_id=exclude_manuscript_id,
                                allowed_source_revision_ids={row['sourceRevisionId'] for row in pool},distinct_sources=True)
    plan=alignment.schedule_pairs(query_blocks,hits,reranker['tokenizer'],
                                  max_pairs=policy['pairBudget'],sources_per_query=policy['sourcesPerBlock'],max_joint=policy['jointTokens'],source_contexts=fields)
    executed=alignment.evaluate_pairs(plan,reranker['scorePair'],reranker['configuration']['configId'])
    query_templates=_template_intervals(text,templates)
    source_templates={revision+':'+key:_template_intervals(context['text'],templates) for (revision,key),context in fields.items() if revision+':'+key in source_lengths}
    summary=aggregation.summarize_sources(executed['pairs'],len(text),source_lengths,feature_config,query_templates,source_templates)
    decisions=[]
    if calibrator is not None:
        for source in summary['sources']:
            decision=aggregation.decide(source['features'],calibrator,feature_config,thresholds,coverage_status=executed['coverageStatus'])
            decisions.append({'sourceRevisionId':source['sourceRevisionId'],'sourceKey':source['sourceKey'],**decision})
    return {**executed,'methodVersion':'text-v3-development','configuration':configuration,'configId':config_id,
            'featureConfig':feature_config,'libraryInputSha256':manifest['inputManifestSha256'],
            'templateSetSha256':retrieval._digest(sorted(templates)),'queryTemplateIntervals':[list(row) for row in query_templates],
            'queryBlockCount':len(query_blocks),'candidateSources':pool,'candidateCount':len(pool),
            'aggregation':summary,'sourceDecisions':decisions,'calibrationStatus':'APPLIED' if calibrator is not None else 'PENDING_CALIBRATION',
            'literalAcceptanceChanged':False,'noReuseClaim':False,'elapsedMs':(time.perf_counter()-started)*1000}
