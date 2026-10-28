"""Traceable text-v3 candidate scheduling. Scheduling is not neural evaluation."""
from collections import deque
import hashlib
import json
import math
import numpy as np
from campus_detection.retrieval import token_blocks


def split_pair(query,source,tokenizer,max_joint=512):
    for side in (query,source):
        if side['start']<0 or side['end']-side['start']!=len(side['text']):raise ValueError('Candidate codepoint range does not reconstruct')
    if len(tokenizer(query['text'],source['text'],truncation=False)['input_ids'])<=max_joint:
        return [{'queryStart':query['start'],'queryEnd':query['end'],'sourceStart':source['start'],'sourceEnd':source['end'],
                 'queryText':query['text'],'sourceText':source['text']}]
    special=tokenizer.num_special_tokens_to_add(pair=True);budget=min(240,(max_joint-special)//2)
    if budget<1:raise ValueError('Joint token budget cannot fit a pair')
    overlap=min(48,budget//4)
    left=token_blocks(query['text'],tokenizer,tokens=budget,overlap=overlap)
    right=token_blocks(source['text'],tokenizer,tokens=budget,overlap=overlap)
    rows=[]
    for qpart in left:
        for spart in right:
            if len(tokenizer(qpart['text'],spart['text'],truncation=False)['input_ids'])>max_joint:raise ValueError('Pair tokenizer budget mismatch; do not truncate')
            rows.append({'queryStart':query['start']+qpart['start'],'queryEnd':query['start']+qpart['end'],
                         'sourceStart':source['start']+spart['start'],'sourceEnd':source['start']+spart['end'],
                         'queryText':qpart['text'],'sourceText':spart['text']})
    return rows


def neighbor_context(hit,context,adjacent_blocks=1):
    """Extend an indexed hit within its exact immutable source field."""
    text=context['text'];blocks=sorted(context['blocks'],key=lambda row:(row['start'],row['end']))
    if not isinstance(adjacent_blocks,int) or isinstance(adjacent_blocks,bool) or adjacent_blocks<0:raise ValueError('Invalid neighbor budget')
    positions=[]
    for index,block in enumerate(blocks):
        if not 0<=block['start']<block['end']<=len(text) or block['text']!=text[block['start']:block['end']]:raise ValueError('Neighbor block does not reconstruct original field')
        if block['start']==hit['start'] and block['end']==hit['end']:positions.append(index)
    if len(positions)!=1 or hit['text']!=text[hit['start']:hit['end']]:raise ValueError('Retrieved hit differs from frozen source blocks')
    position=positions[0];selected=blocks[max(0,position-adjacent_blocks):position+adjacent_blocks+1]
    start=min(row['start'] for row in selected);end=max(row['end'] for row in selected)
    return {**hit,'start':start,'end':end,'text':text[start:end],
            'retrievedSourceRange':{'start':hit['start'],'end':hit['end']}}


def schedule_pairs(query_blocks,hits_by_query,tokenizer,max_pairs=2048,sources_per_query=3,max_joint=512,source_contexts=None):
    if len(query_blocks)!=len(hits_by_query) or max_pairs<1 or sources_per_query<1:raise ValueError('Invalid alignment input or budget')
    queues=[];total=0;empty_regions=[]
    for query_index,(query,hits) in enumerate(zip(query_blocks,hits_by_query)):
        chosen=[];sources=set()
        for hit in sorted(hits,key=lambda row:(-row['score'],str(row['sourceRevisionId']),row['start'])):
            source=str(hit['sourceRevisionId'])
            if source in sources:continue
            sources.add(source);chosen.append(hit)
            if len(chosen)>=sources_per_query:break
        candidates=[]
        # Interleave sources so one source's expanded long windows cannot monopolize a region.
        source_queues=[]
        for hit in chosen:
            retrieved={'start':hit['start'],'end':hit['end']}
            if source_contexts is not None:
                identity=(str(hit['sourceRevisionId']),hit.get('sourceKey','BODY'))
                if identity not in source_contexts:raise ValueError('Missing immutable source revision/field context')
                hit=neighbor_context(hit,source_contexts[identity])
            values=split_pair(query,hit,tokenizer,max_joint)
            source_queues.append(deque({**row,'queryBlockIndex':query_index,'sourceRevisionId':str(hit['sourceRevisionId']),
                                        'sourceWorkId':str(hit['sourceWorkId']),'sourceKey':hit.get('sourceKey','BODY'),
                                        'retrievalScore':float(hit['score']),'retrievedSourceRange':retrieved,
                                        'scoreType':'NOT_YET_RERANKED'} for row in values))
        while any(source_queues):
            for queue in source_queues:
                if queue:candidates.append(queue.popleft())
        total+=len(candidates);queues.append(deque(candidates))
        if not candidates:empty_regions.append({'start':query['start'],'end':query['end']})
    active=[index for index,queue in enumerate(queues) if queue]
    # If even one per region does not fit, spread the first round to include the end.
    if len(active)>max_pairs:
        order=[active[int(index)] for index in np.linspace(0,len(active)-1,max_pairs,dtype=int)]
    else:order=active
    selected=[]
    while len(selected)<max_pairs and any(queues[index] for index in order):
        for index in order:
            if queues[index]:selected.append(queues[index].popleft())
            if len(selected)>=max_pairs:break
    regions=sorted({(row['queryStart'],row['queryEnd']) for row in selected})
    return {'pairs':selected,'scheduledRegions':[{'start':start,'end':end} for start,end in regions],
            'emptyCandidateRegions':empty_regions,'candidatePairsBeforeBudget':total,'scheduledPairCount':len(selected),
            'deferredCandidatePairs':total-len(selected),'pairBudget':max_pairs,'jointTokenBudget':max_joint,
            'coveragePlan':'PARTIAL' if total>len(selected) or empty_regions else 'COMPLETE','neuralInferencePerformed':False,
            'scope':'Planned pairs only. Checked regions and evaluated pair counts must come from actual successful model calls. No lexical score floor creates or rejects correspondence truth.'}


def evaluate_pairs(plan,score_pair,model_config_id,*,score_type='CONTENT_CORRESPONDENCE_SCORE'):
    """Run the supplied task-model callback; retain failures outside evidence.

    The caller binds the verified classifier and its explicit score type.
    Offline BERT/M3 controls retain their own score types; retrieval cosine
    cannot substitute for a classifier. This function does not accept quality.
    """
    if score_type not in {'CONTENT_CORRESPONDENCE_SCORE','LEGACY_SEMANTIC_SCORE','PRETRAINED_RELEVANCE_SCORE'}:raise ValueError('Require an explicit trained-head score type, not retrieval cosine')
    if not isinstance(model_config_id,str) or not model_config_id.strip():raise ValueError('Missing task-model configuration identity')
    if plan['coveragePlan'] not in {'COMPLETE','PARTIAL'} or plan['scheduledPairCount']!=len(plan['pairs']):raise ValueError('Invalid alignment plan')
    evaluated=[];failures=[]
    for index,pair in enumerate(plan['pairs']):
        try:
            score=score_pair(dict(pair))
            if isinstance(score,(bool,np.bool_)):raise ValueError('Boolean is not a task-model score')
            score=float(score)
            if not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid task-model score')
        except Exception as error:
            failures.append({'pairIndex':index,'queryStart':pair['queryStart'],'queryEnd':pair['queryEnd'],
                             'sourceRevisionId':pair['sourceRevisionId'],'sourceKey':pair['sourceKey'],
                             'sourceStart':pair['sourceStart'],'sourceEnd':pair['sourceEnd'],'errorType':type(error).__name__})
            continue
        identity={key:pair[key] for key in ['queryStart','queryEnd','sourceRevisionId','sourceKey','sourceStart','sourceEnd','queryText','sourceText']}
        identity['modelConfigId']=model_config_id
        identity['scoreType']=score_type
        evidence_id='alignment-'+hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        evaluated.append({**pair,'score':score,'scoreType':score_type,
                          'modelConfigId':model_config_id,'evidenceId':evidence_id})
    regions=[]
    for start,end in sorted({(row['queryStart'],row['queryEnd']) for row in evaluated}):
        if regions and start<=regions[-1]['end']:regions[-1]['end']=max(end,regions[-1]['end'])
        else:regions.append({'start':start,'end':end})
    status='FAILED' if failures and not evaluated else 'PARTIAL' if not evaluated or failures or plan['coveragePlan']=='PARTIAL' else 'COMPLETE'
    return {'pairs':evaluated,'failures':failures,'checkedRegions':regions,'evaluatedPairCount':len(evaluated),
            'failedPairCount':len(failures),'scheduledPairCount':len(plan['pairs']),
            'candidatePairsBeforeBudget':plan['candidatePairsBeforeBudget'],'deferredCandidatePairs':plan['deferredCandidatePairs'],
            'emptyCandidateRegions':plan['emptyCandidateRegions'],'pairBudget':plan['pairBudget'],
            'jointTokenBudget':plan['jointTokenBudget'],'coverageStatus':status,'modelConfigId':model_config_id,
            'noReuseClaim':False,'qualityAccepted':False,
            'scope':'Checked regions are successful inference context-window unions, not reused characters or proof all sources were checked.'}
