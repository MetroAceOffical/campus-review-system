"""Traceable text-v3 candidate scheduling. Scheduling is not neural evaluation."""
from collections import deque
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


def schedule_pairs(query_blocks,hits_by_query,tokenizer,max_pairs=2048,sources_per_query=3,max_joint=512):
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
            values=split_pair(query,hit,tokenizer,max_joint)
            source_queues.append(deque({**row,'queryBlockIndex':query_index,'sourceRevisionId':str(hit['sourceRevisionId']),
                                        'sourceWorkId':str(hit['sourceWorkId']),'sourceKey':hit.get('sourceKey','BODY'),
                                        'retrievalScore':float(hit['score']),'scoreType':'NOT_YET_RERANKED'} for row in values))
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
