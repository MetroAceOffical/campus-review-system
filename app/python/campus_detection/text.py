import collections
import math
import time
from campus_shared.contracts import ContractError,evidence_id,result_header,validate_request

def prepare_text_index(library,models):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from campus_detection.models import frozen_text_helpers
    helper=frozen_text_helpers();config=models['textConfig']
    documents=[dict(item) for item in library.get('documents',[]) if item.get('text','').strip()]
    by_id={str(item.get('sourceKey',item['sourceRevisionId'])):item for item in documents}
    if len(by_id)!=len(documents):raise ContractError('INVALID_LIBRARY','Duplicate reference revision identity')
    windows=[];indices={}
    for source_id,document in by_id.items():
        indices[source_id]=[]
        for window in helper.chunk_text(document['text'],models['tokenizer'],config['chunk']['tokens'],config['chunk']['overlap']):
            indices[source_id].append(len(windows));windows.append(dict(window,sourceRevisionId=source_id))
    vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(1,2),max_features=40000,lowercase=False,dtype=np.float32)
    matrix=vectorizer.fit_transform([window['text'] for window in windows]) if windows else None
    frequency=collections.Counter()
    for document in documents:frequency.update({document['text'][i:i+16] for i in range(max(0,len(document['text'])-15))})
    templates={gram for gram,count in frequency.items() if count>=max(3,math.ceil(.1*len(documents)))}
    return {'documents':by_id,'windows':windows,'indices':indices,'vectorizer':vectorizer,'matrix':matrix,'templates':templates,'featureSpaceId':config['featureSpaceId']}

def detect_text(request,library,models):
    start=time.perf_counter();config=models.get('textConfigs',{}).get(request.get('configId'),models['textConfig']);validate_request(request,config,library)
    output=result_header(request,config)
    text=request.get('text')
    if not isinstance(text,str) or len(text)>10000:raise ContractError('INVALID_TEXT','Text must contain at most 10000 Unicode code points')
    if not text.strip():output.update(status='NOT_APPLICABLE',elapsedMs=(time.perf_counter()-start)*1000);return output
    if config.get('schemaVersion')=='text-v3':
        from campus_detection.v3_runtime import detect
        return detect(request,library,models)
    documents=[item for item in library.get('documents',[]) if item.get('text','').strip() and not (request.get('excludeManuscriptId') is not None and item.get('manuscriptId') is not None and str(item['manuscriptId'])==request['excludeManuscriptId'])]
    if not documents:output.update(qualityFlags=['EMPTY_LIBRARY'],elapsedMs=(time.perf_counter()-start)*1000);return output
    import numpy as np
    from campus_detection.models import frozen_text_helpers
    helper=frozen_text_helpers()
    index=library.get('_textIndex')
    if index is None:index=prepare_text_index(library,models);library['_textIndex']=index
    if index['featureSpaceId']!=config['featureSpaceId']:raise ContractError('INCOMPATIBLE_FEATURE_SPACE','Text index configuration is incompatible')
    query_windows=helper.chunk_text(text,models['tokenizer'],config['chunk']['tokens'],config['chunk']['overlap'])
    similarities=(index['vectorizer'].transform([window['text'] for window in query_windows])@index['matrix'].T).toarray()
    allowed={str(item.get('sourceKey',item['sourceRevisionId'])) for item in documents}
    scores={sid:float(np.mean(np.sort(similarities[:,index['indices'][sid]].max(axis=1))[-min(3,len(query_windows)):])) for sid in allowed}
    # Self exclusion is applied before TopK, never after candidate truncation.
    candidates=sorted(scores,key=lambda sid:(-scores[sid],sid))[:config['candidateK']]
    pairs=[];pair_keys=[];evidence=[]
    def template(value):
        grams=[value[i:i+16] for i in range(max(0,len(value)-15))]
        return bool(grams) and sum(gram in index['templates'] for gram in grams)/len(grams)>=.8
    for sid in candidates:
        source=index['documents'][sid];matches=[];semantic_candidates=[]
        for qi,query in enumerate(query_windows):
            best=sorted(index['indices'][sid],key=lambda j:(-similarities[qi,j],j))[:2]
            for j in best:
                reference=index['windows'][j]
                for match in helper.literal_matches(query['text'],reference['text'],20):
                    if not template(match['text']):matches.append(dict(match,q_start=match['q_start']+query['start'],q_end=match['q_end']+query['start'],s_start=match['s_start']+reference['start'],s_end=match['s_end']+reference['start']))
            semantic_candidates.append((float(similarities[qi,best[0]]),qi,best[0]))
        merged=[match for match in helper.merge_matches(matches,text) if len(match['text'])>=config['params']['literal_minimum']]
        summary=helper.evidence_summary(merged,len(text));params=config['params']
        accepted=summary['matched_characters']>=params['min_chars'] and (summary['query_character_coverage']>=params['min_coverage'] or summary['longest_match']>=2*params['min_chars'])
        item={'evidenceId':evidence_id(request['attemptId'],'text',sid),'evidenceType':'TEXT_SIMILARITY',
              'sourceScope':'LIBRARY','sourceKind':source.get('sourceKind','BODY'),'sourceWorkId':str(source['sourceWorkId']),
              'sourceRevisionId':str(source['sourceRevisionId']),'sourceKey':source.get('sourceKey','BODY'),'sourceTitle':source['title'],'sourceUrl':source.get('url'),'sourceMetadata':source.get('sourceMetadata',{}),
              'tfidfScore':scores[sid],'acceptedCandidate':bool(accepted),'literalSummary':summary,'matches':[],'semanticWindows':[]}
        for match in merged:
            query_piece=text[match['q_start']:match['q_end']];source_piece=source['text'][match['s_start']:match['s_end']]
            if query_piece!=source_piece:raise ContractError('EVIDENCE_OFFSET_MISMATCH','Evidence does not match immutable input')
            item['matches'].append({'queryStart':match['q_start'],'queryEnd':match['q_end'],'sourceStart':match['s_start'],'sourceEnd':match['s_end'],'queryText':query_piece,'sourceText':source_piece})
        for _,qi,j in ([] if config.get('schemaVersion')=='text-v2' else sorted(semantic_candidates,reverse=True)[:2]):
            query=query_windows[qi];reference=index['windows'][j]
            if len(models['tokenizer'](query['text'],reference['text'],add_special_tokens=True)['input_ids'])>128:raise ContractError('BERT_WINDOW_TOO_LONG','Frozen BERT pair budget exceeded')
            pairs.append({'sentence1':query['text'],'sentence2':reference['text'],'label':0});pair_keys.append((item,query,reference))
        evidence.append(item)
    semantic_scores=models['predictBert'](pairs)
    if len(semantic_scores)!=len(pair_keys):raise ContractError('MODEL_OUTPUT_MISMATCH','BERT returned an inconsistent window count')
    for (item,query,reference),score in zip(pair_keys,semantic_scores):
        item['semanticWindows'].append({'queryStart':query['start'],'queryEnd':query['end'],'sourceStart':reference['start'],'sourceEnd':reference['end'],'queryText':query['text'],'sourceText':reference['text'],'score':float(score)})
    output.update(evidence=evidence,qualityFlags=['PARTIAL_SEMANTIC_COVERAGE'],queryWindowCount=len(query_windows),candidateCount=len(candidates),semanticAlpha=0,elapsedMs=(time.perf_counter()-start)*1000)
    if config.get('schemaVersion')=='text-v2':
        from campus_detection.semantic import add_semantic_evidence
        add_semantic_evidence(output,index,text,models,config)
        output['elapsedMs']=(time.perf_counter()-start)*1000
    if len(text)<config['params']['min_chars']:output['qualityFlags'].append('INSUFFICIENT_TEXT')
    return output
