"""Freeze heldout construction slots and exact controls without loading models.

Pending generation and unsupported negative truth stay pending. READY freezes
this artifact; only fullQuerySetReady can indicate a complete query protocol.
"""
import argparse
import hashlib
import json
import re
from collections import Counter,defaultdict
from pathlib import Path

from corpus import normalized,read_jsonl
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]
TARGETS={
    'calibration':{'whole_synonym':40,'whole_reordered':40,'local':40,'multi_source':20,'copy_control':20,'same_event_negative':25,'template_normal':15},
    'dev':{'whole_synonym':84,'whole_reordered':83,'local':67,'multi_source':33,'copy_control':33,'same_event_negative':67,'template_normal':33},
    'final':{'whole_synonym':250,'whole_reordered':250,'local':200,'multi_source':100,'copy_control':100,'same_event_negative':200,'template_normal':100}}


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def reordered(original):
    text=original['text'];parts=list(re.finditer(r'.+?(?:[。！？；\n]|$)',text,re.S))
    if len(parts)<2:return None
    pivot=max(1,len(parts)//2);order=parts[pivot:]+parts[:pivot];pieces=[];mappings=[];cursor=0
    for part in order:
        piece=part[0];pieces.append(piece)
        mappings.append({'sourceRevisionId':original['documentId'],'sourceKey':'BODY','queryStart':cursor,'queryEnd':cursor+len(piece),
                         'sourceStart':part.start(),'sourceEnd':part.end(),'mappingType':'EXACT_SEGMENT'})
        cursor+=len(piece)
    query=''.join(pieces)
    if normalized(query)==normalized(text):return None
    return query,mappings


def build_protocol(partitions,natural,targets=None,seed=20261027):
    targets=TARGETS if targets is None else targets
    if set(partitions)!=set(targets) or set(partitions)-{'calibration','dev','final'}:raise ValueError('Use only disjoint calibration/dev/final source partitions')
    by_id={};event_splits={};cluster_splits={}
    for split,rows in partitions.items():
        for row in rows:
            if row.get('split')!=split or row['documentId'] in by_id:raise ValueError('Parent split/identity mismatch')
            by_id[row['documentId']]=row
            for key,seen in [('eventClusterId',event_splits),('sourceClusterId',cluster_splits)]:
                value=row[key]
                if value in seen and seen[value]!=split:raise ValueError('Source/event family crosses protocol splits')
                seen[value]=split
    plans=[];queries=[];seen_queries=set();event_usage=Counter();stats=Counter();natural_groups={}
    for record in natural:
        split=record['split']
        if split not in partitions:continue
        if len(record['sourceIds'])!=1:raise ValueError('Natural exact-content records require one canonical parent')
        parent=by_id[record['sourceIds'][0]]
        if parent['split']!=split or not record.get('contentProof',{}).get('accepted') or normalized(record['source'])!=normalized(parent['text']) or normalized(record['query'])!=normalized(parent['text']):raise ValueError('Natural exact-content provenance differs')
        if not 200<=len(record['query'])<=10000:stats['naturalOutsideProductLength']+=1;continue
        key=(split,normalized(record['query']))
        if key in natural_groups and natural_groups[key]['parent']['documentId']!=parent['documentId']:raise ValueError('Duplicate canonical parents need source-family reconciliation')
        group=natural_groups.setdefault(key,{'parent':parent,'query':record['query'],'records':[]})
        group['records'].append({'relationId':record['relationId'],'queryUrl':record.get('queryUrl'),'queryPageSha256':record.get('queryPageSha256')})
    for split,counts in targets.items():
        if set(counts)-set(TARGETS['final']) or any(not isinstance(n,int) or isinstance(n,bool) or n<0 for n in counts.values()):raise ValueError('Invalid query category targets')
        originals=[row for row in partitions[split] if 200<=len(row['text'])<=8000]
        home=0;assigned_primary=0;existing={};order_cache={}
        def slot(category,index,parents):
            key=(category,index);query_id='eval:'+split+':'+digest(f'{seed}:{split}:{category}:{index}')
            negative=category in {'same_event_negative','template_normal'}
            row={'queryId':query_id,'split':split,'category':category,'categoryIndex':index,'constructionParents':[p['documentId'] for p in parents],
                 'expectedSourceIds':[] if negative else [p['documentId'] for p in parents],
                 'eventClusterIds':sorted({p['eventClusterId'] for p in parents}),'sourceClusterIds':sorted({p['sourceClusterId'] for p in parents}),
                 'homePrimary':bool(parents and parents[0]['institutionName']=='南京传媒学院'),
                 'constructionStatus':'NEEDS_SUPPORTED_NEGATIVE_SCOPE' if negative else 'WAITING_HELDOUT_GENERATION',
                 'transformationKind':'PENDING_NEGATIVE_TRUTH' if negative else 'PARAPHRASE_REORDER' if category=='whole_reordered' else 'PARAPHRASE'}
            if not parents:row['constructionStatus']='NEEDS_NEW_PARENTS'
            existing[key]=row;plans.append(row);return row
        def emit(row,query,mappings,kind,natural_provenance=None):
            key=normalized(query)
            if key in seen_queries:row['constructionStatus']='DUPLICATE_QUERY_EXCLUDED';stats['duplicateQueriesExcluded']+=1;return
            if not 1<=len(query)<=10000:row['constructionStatus']='QUERY_OUTSIDE_PRODUCT_LENGTH';return
            seen_queries.add(key);row.update(constructionStatus='CONSTRUCTED',transformationKind=kind)
            natural_provenance=natural_provenance or []
            queries.append({**row,'query':query,'querySha256':digest(query),'queryManuscriptId':row['queryId'],
                            'truthScope':'known_positive_sources_only','labelConfidence':'known','humanVerified':False,
                            'labelOrigin':'traceable_correspondence' if natural_provenance else 'controlled_construction',
                            'expectedEvidenceScope':'WHOLE','sourceMappings':mappings,'naturalProvenance':natural_provenance,
                            'usedDetectorScoresForTruth':False})
        natural_for_split=sorted((group for (name,_),group in natural_groups.items() if name==split),key=lambda group:digest(group['query']))
        for group in natural_for_split:
            index=sum(key[0]=='copy_control' for key in existing)
            if index>=counts.get('copy_control',0):break
            parent=group['parent'];event=parent['eventClusterId']
            if event_usage[event]>=2:stats['naturalEventCapExcluded']+=1;continue
            event_usage[event]+=1;assigned_primary+=1;home+=parent['institutionName']=='南京传媒学院'
            row=slot('copy_control',index,[parent])
            emit(row,group['query'],[{'sourceRevisionId':parent['documentId'],'sourceKey':'BODY','queryStart':0,'queryEnd':len(group['query']),
                                    'sourceStart':0,'sourceEnd':len(parent['text']),'mappingType':'NORMALIZED_EXACT_WHOLE'}],
                 'NATURAL_NORMALIZED_EXACT_CONTENT',group['records'])
            stats['naturalRelationsReused']+=len(group['records'])
        def choose(category,index,excluded=(),secondary=False):
            prefer_home=not secondary and home<.6*max(1,assigned_primary+1)
            candidates=[]
            for original in originals:
                if original['eventClusterId'] in excluded or event_usage[original['eventClusterId']]>=2:continue
                if category=='copy_control' and normalized(original['text']) in seen_queries:continue
                if category=='whole_reordered' and index%2==0:
                    if original['documentId'] not in order_cache:order_cache[original['documentId']]=reordered(original)
                    result=order_cache[original['documentId']]
                    if result is None or normalized(result[0]) in seen_queries:continue
                candidates.append(original)
            if not candidates:return None
            chosen=min(candidates,key=lambda p:(int((p['institutionName']=='南京传媒学院')!=prefer_home),event_usage[p['eventClusterId']],digest(p['documentId'])))
            event_usage[chosen['eventClusterId']]+=1;return chosen
        for index in range(max(counts.values(),default=0)):
            for category,count in counts.items():
                if index>=count or (category,index) in existing:continue
                primary=choose(category,index);parents=[] if primary is None else [primary]
                if primary is not None and category=='multi_source':
                    secondary=choose(category,index,excluded={primary['eventClusterId']},secondary=True)
                    if secondary is None:event_usage[primary['eventClusterId']]-=1;parents=[]
                    else:parents.append(secondary)
                row=slot(category,index,parents)
                if not parents:continue
                assigned_primary+=1;home+=parents[0]['institutionName']=='南京传媒学院'
                if category=='copy_control':
                    emit(row,primary['text'],[{'sourceRevisionId':primary['documentId'],'sourceKey':'BODY','queryStart':0,'queryEnd':len(primary['text']),
                                             'sourceStart':0,'sourceEnd':len(primary['text']),'mappingType':'EXACT_SEGMENT'}],'EXACT_COPY_CONTROL')
                elif category=='whole_reordered' and index%2==0:
                    query,mappings=order_cache[primary['documentId']];emit(row,query,mappings,'SENTENCE_REORDER_CONTROL')
    requested=sum(sum(counts.values()) for counts in targets.values())
    summary={'state':'QUERY_CONSTRUCTION_PLAN_AND_EXACT_CONTROLS_FROZEN','seed':seed,'requestedQuerySlots':requested,'plannedSlots':len(plans),
             'constructedQueries':len(queries),'pendingSlots':sum(row['constructionStatus']!='CONSTRUCTED' for row in plans),
             'fullQuerySetReady':len(queries)==requested and all(row['constructionStatus']=='CONSTRUCTED' for row in plans),
             'maximumPlannedQueriesPerEvent':max(event_usage.values(),default=0),'maximumAllowedQueriesPerEvent':2,
             'homeTargetFraction':.6,'splitCounts':{},'statistics':dict(stats),'generatedParaphraseQueries':0,
             'globallySupportedNormalQueries':0,'neuralTrainingPerformed':False,'modelPredictionsProduced':0,'humanGold':False,
             'scope':'Exact copy/reorder and natural normalized-exact controls only. Pending generation and negative-scope truth are not queries or quality scores. Repeated natural publication bodies merge into one query with multiple provenance records.'}
    for split,counts in targets.items():
        planned=[p for p in plans if p['split']==split];made=[q for q in queries if q['split']==split]
        summary['splitCounts'][split]={'target':sum(counts.values()),'constructed':len(made),'pending':sum(p['constructionStatus']!='CONSTRUCTED' for p in planned),
            'constructedByCategory':dict(Counter(q['category'] for q in made)),
            'plannedHomePrimaryQueries':sum(p['homePrimary'] for p in planned),'constructedHomePrimaryQueries':sum(q['homePrimary'] for q in made),
            'homeTargetMetForPlan':sum(p['homePrimary'] for p in planned)>=.6*len(planned),
            'naturalUniqueQueries':sum(q['labelOrigin']=='traceable_correspondence' for q in made),
            'naturalRelations':sum(len(q['naturalProvenance']) for q in made),
            'constructionStatuses':dict(Counter(p['constructionStatus'] for p in planned))}
    return {'plans':plans,'queries':queries,'summary':summary}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--partitions',type=Path,default=ROOT/'runtime/datasets/campus-partitions-20261026-v1')
    parser.add_argument('--natural',type=Path,default=ROOT/'runtime/datasets/campus-natural-relations-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/text-evaluation-protocol-v1');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()) or output.exists():raise ValueError('Use a new project protocol directory')
    partition_hashes=verify_ready(args.partitions);natural_hashes=verify_ready(args.natural)
    partitions={split:list(read_jsonl(args.partitions/(split+'.jsonl'))) for split in TARGETS}
    result=build_protocol(partitions,list(read_jsonl(args.natural/'relations.jsonl')))
    references=[]
    for split in ['train','calibration','dev','final']:
        for row in read_jsonl(args.partitions/(split+'.jsonl')):
            references.append({'sourceRevisionId':row['documentId'],'sourceWorkId':row['documentId'],'sourceKey':'BODY','manuscriptId':'reference:'+row['documentId'],
                               'title':row['title'],'text':row['text'],'url':row['url'],'sourceSplit':split,
                               'sourceClusterId':row['sourceClusterId'],'eventClusterId':row['eventClusterId'],'institutionName':row['institutionName']})
    output.mkdir(parents=True,exist_ok=False)
    for name,rows in [('construction-plan.jsonl',result['plans']),('queries.jsonl',result['queries']),('references.jsonl',references)]:
        with (output/name).open('w',encoding='utf-8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest={**result['summary'],'targetsBySplit':TARGETS,'partitionHashes':partition_hashes,'naturalHashes':natural_hashes,
              'referenceFields':len(references),'constructionCodeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'finalProtocolExecuted':False,'qualityAccepted':False}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    hashes={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ['construction-plan.jsonl','queries.jsonl','references.jsonl','manifest.json']}
    (output/'READY').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
