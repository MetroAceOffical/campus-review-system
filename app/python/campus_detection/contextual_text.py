"""Version-budgeted clause/context evidence using the unchanged trained BERT scorer."""
import re,time
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256,evidence_id,ContractError
from .semantic import sentence_units,semantic_summary
from .reference_versions import reference_groups


def context_units(text,tokenizer,budget=60,limit=None):
    import numpy as np
    base=sentence_units(text,tokenizer,budget);extra=[]
    for first,second in zip(base,base[1:]):
        value=text[first['start']:second['end']]
        if len(tokenizer(value,add_special_tokens=False)['input_ids'])<=budget:extra.append(dict(start=first['start'],end=second['end'],text=value))
    for match in re.finditer(r'[^，,。！？；;\n]+[，,。！？；;\n]*',text):
        a,b=match.span()
        while a<b and text[a].isspace():a+=1
        while b>a and text[b-1].isspace():b-=1
        if b-a>=12 and len(tokenizer(text[a:b],add_special_tokens=False)['input_ids'])<=budget:extra.append(dict(start=a,end=b,text=text[a:b]))
    result=[];seen=set();base_length=0
    for position,unit in enumerate(base+extra):
        identity=(unit['start'],unit['end'])
        if identity not in seen:result.append(unit);seen.add(identity)
        if position<len(base):base_length=len(result)
    if limit and len(result)>limit:
        if base_length>=limit:result=[result[i] for i in np.linspace(0,base_length-1,limit,dtype=int)]
        else:
            additional=result[base_length:];result=result[:base_length]+[additional[i] for i in np.linspace(0,len(additional)-1,limit-base_length,dtype=int)]
    return sorted(result,key=lambda u:(u['start'],u['end']))


def select_versions(records,max_groups=3,max_versions=2):
    groups={};selected=[]
    for row in records:
        group=row['group']
        if group not in groups:
            if len(groups)>=max_groups:continue
            groups[group]=0
        if groups[group]>=max_versions:continue
        selected.append(row);groups[group]+=1
    return selected


def configuration(base,hybrid=False,retriever=None):
    from . import reference_versions
    value={**base,'method':'context-version-budget-20261029','baseConfigId':base['configId'],
           'contextAlgorithmSha256':file_sha256(Path(__file__)),'referenceGroupingSha256':file_sha256(reference_versions.__file__),
           'contextPolicy':dict(unitTokens=60,maxQueryUnits=48,maxSourceGroups=3,maxVersionsPerGroup=2,maxPairs=768,
                                lexicalCandidates=2 if hybrid else 4,denseCandidates=2 if hybrid else 0,alignmentMinimum=.08,
                                scoreThreshold=.5,lexicalFloor=.25,minimumPairs=2,minimumCharacters=64),
           'contextRetriever':retriever if hybrid else None}
    value.pop('configId');value['configId']='text-'+digest_json(value);return value


def add_context(output,index,text,models,config,encode=None):
    import numpy as np
    policy=config['contextPolicy'];tokenizer=models['tokenizer'];query_units=context_units(text,tokenizer,policy['unitTokens'],policy['maxQueryUnits'])
    groups=reference_groups(list(index['documents'].values()))
    descriptors={evidence_id(output['attemptId'],'text',key):(key,source) for key,source in index['documents'].items()}
    candidates=[]
    for evidence in output['evidence']:
        key,source=descriptors[evidence['evidenceId']]
        evidence['literalAcceptedCandidate']=evidence['acceptedCandidate'];evidence['referenceGroupId']=groups[key]
        evidence['semanticWindows']=[];evidence['semanticSummary']={**semantic_summary([],policy),'status':'NOT_EVALUATED'}
        if source.get('sourceKind','BODY')=='BODY':candidates.append(dict(key=key,group=groups[key],source=source,evidence=evidence))
    selected=select_versions(candidates,policy['maxSourceGroups'],policy['maxVersionsPerGroup'])
    query_matrix=index['vectorizer'].transform([u['text'] for u in query_units]) if query_units else None
    query_dense=encode([u['text'] for u in query_units]) if encode and query_units else None
    prepared=[]
    for row in selected:
        units=context_units(row['source']['text'],tokenizer,policy['unitTokens'])
        if not units or not query_units:continue
        lexical=(query_matrix@index['vectorizer'].transform([u['text'] for u in units]).T).toarray()
        dense=query_dense@encode([u['text'] for u in units]).T if encode else None
        prepared.append((row,units,lexical,dense))
    pairs=[];assignments=[]
    # Round-robin queries/sources; a repeated long first record cannot consume the budget.
    for qi,query in enumerate(query_units):
        for row,units,lexical,dense in prepared:
            positions=[int(i) for i in np.argsort(-lexical[qi],kind='stable')[:policy['lexicalCandidates']]]
            positions=[i for i in positions if lexical[qi,i]>=policy['alignmentMinimum']]
            if dense is not None:positions+=list(map(int,np.argsort(-dense[qi],kind='stable')[:policy['denseCandidates']]))
            for si in dict.fromkeys(positions):
                source=units[si]
                if len(tokenizer(query['text'],source['text'],add_special_tokens=True)['input_ids'])>128:raise ContractError('BERT_WINDOW_TOO_LONG','Context pair exceeds frozen BERT budget')
                pairs.append(dict(sentence1=query['text'],sentence2=source['text'],label=0))
                window=dict(queryStart=query['start'],queryEnd=query['end'],sourceStart=source['start'],sourceEnd=source['end'],queryText=query['text'],sourceText=source['text'],tfidfScore=float(lexical[qi,si]),alignment='context-clause')
                if dense is not None:window['denseScore']=float(dense[qi,si])
                assignments.append((row['evidence'],window))
    planned=len(pairs)
    if planned>policy['maxPairs']:
        positions=list(map(int,np.linspace(0,planned-1,policy['maxPairs'],dtype=int)));pairs=[pairs[i] for i in positions];assignments=[assignments[i] for i in positions]
    # Reuse identical text-pair inference, retaining every selected occurrence's
    # offsets. Different citation states must still get their own evidence rows.
    unique={}
    for pair in pairs:unique.setdefault((pair['sentence1'],pair['sentence2']),pair)
    unique_scores=models['predictBert'](list(unique.values()))
    if len(unique_scores)!=len(unique):raise ContractError('MODEL_OUTPUT_MISMATCH','Missing context scores')
    score_map=dict(zip(unique,unique_scores));scores=[score_map[(p['sentence1'],p['sentence2'])] for p in pairs]
    if len(scores)!=len(assignments) or not all(np.isfinite(s) and 0<=s<=1 for s in scores):raise ContractError('MODEL_OUTPUT_MISMATCH','Invalid context scores')
    for (evidence,window),score in zip(assignments,scores):evidence['semanticWindows'].append(dict(window,score=float(score)))
    for row in selected:
        evidence=row['evidence'];windows=evidence['semanticWindows']
        if windows:evidence['semanticSummary']={**semantic_summary(windows,policy),'status':'EVALUATED','evaluatedPairs':len(windows)}
        windows.sort(key=lambda w:(-w['score'],w['queryStart'],w['sourceStart']))
    output['semanticEvaluation']=dict(method='context-clause-version-groups',availableQueryUnits=len(context_units(text,tokenizer,policy['unitTokens'])),evaluatedQueryUnits=len(query_units),
        evaluatedSources=sum(bool(r['evidence']['semanticWindows']) for r in selected),evaluatedGroups=len({r['group'] for r in selected}),evaluatedPairs=len(pairs),uniqueScoredPairs=len(unique),plannedPairs=planned,maxPairs=policy['maxPairs'],
        sourceRecordsRetained=len(output['evidence']),scope='Selected reference groups and bounded contexts only; unselected versions and sources remain unassessed')
    output['semanticEvaluationEnabled']=True;output['qualityFlags']=list(dict.fromkeys(output.get('qualityFlags',[])+['PARTIAL_SEMANTIC_COVERAGE']))


def detect(request,library,models,encode=None):
    from .text import detect_text
    start=time.perf_counter();config=models['textConfigs'][request['configId']]
    output=detect_text(request,library,models,semantic_enabled=False)
    if output['status']=='COMPLETED' and output['evidence']:add_context(output,library['_textIndex'],request['text'],models,config,encode)
    output['elapsedMs']=(time.perf_counter()-start)*1000;return output
