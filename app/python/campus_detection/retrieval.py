"""Versioned dense-index primitives for the pending text-v3 pipeline.

No model is loaded here. Callers must bind the encoder to verified weights and
tokenizer identities; existing text-v1/v2 routing and indexes are unchanged.
"""
import hashlib
import json
import re
from pathlib import Path

import numpy as np


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def token_blocks(text,tokenizer,tokens=192,overlap=48):
    if not 0<=overlap<tokens:raise ValueError('Invalid token window overlap')
    boundaries={match.end() for match in re.finditer(r'[。！？!?；;\n.]',text)}
    rows=[];cursor=0
    while cursor<len(text):
        # ponytail: re-tokenize suffixes for exact wordpiece/SentencePiece boundary
        # behavior; optimize only if this measured cost dominates model encoding.
        offsets=tokenizer(text[cursor:],add_special_tokens=False,return_offsets_mapping=True,truncation=False,verbose=False)['offset_mapping']
        offsets=[tuple(pair) for pair in offsets if pair[1]>pair[0]]
        if not offsets:break
        end=min(tokens,len(offsets))
        if end<len(offsets):
            sentence_ends=[i+1 for i in range(max(1,tokens-overlap)-1,end) if cursor+offsets[i][1] in boundaries]
            if sentence_ends:end=max(sentence_ends)
        while end:
            end_char=len(text) if end==len(offsets) else cursor+offsets[end-1][1]
            chunk=text[cursor:end_char]
            if len(tokenizer(chunk,add_special_tokens=False,truncation=False,verbose=False)['input_ids'])<=tokens:break
            end-=1
        if not end:raise ValueError('Token budget cannot fit a nonempty original-codepoint slice')
        rows.append({'start':cursor,'end':end_char,'text':chunk})
        if end_char==len(text):break
        advance=max(1,end-overlap)
        cursor=cursor+offsets[advance][0] if advance<end else cursor+offsets[end-1][1]
    return rows


def _configuration(identity,tokens,overlap):
    for key in ['weightSha256','tokenizerSha256']:
        if not re.fullmatch('[0-9a-f]{64}',identity.get(key,'')):raise ValueError('Missing fixed encoder identity: '+key)
    if identity.get('pooling')!='CLS' or identity.get('normalization')!='L2' or not identity.get('precision'):raise ValueError('Unsupported encoder feature policy')
    return {'encoder':identity,'dimensions':768,'chunk':{'tokens':tokens,'overlap':overlap,'coordinates':'ORIGINAL_CODEPOINTS'},
            'algorithmSha256':_sha(Path(__file__))}


def _vectors(values,expected_rows):
    values=np.asarray(values,dtype=np.float32)
    if values.shape!=(expected_rows,768) or not np.isfinite(values).all() or not np.allclose(np.linalg.norm(values,axis=1),1.,atol=1e-4):raise ValueError('Dense vectors must be finite, normalized, 768-dimensional rows')
    return values


def build_dense_index(documents,tokenizer,encode,output,identity,tokens=192,overlap=48,batch=16):
    output=Path(output)
    if output.exists():raise ValueError('Use a new immutable dense-index directory')
    if batch<1:raise ValueError('Invalid encoder batch size')
    config=_configuration(identity,tokens,overlap);blocks=[];seen_sources=set()
    for original in documents:
        source=str(original['sourceRevisionId'])+':'+str(original.get('sourceKey','BODY'))
        if source in seen_sources:raise ValueError('Duplicate source revision/field identity')
        seen_sources.add(source)
        for block in token_blocks(original.get('text',''),tokenizer,tokens,overlap):
            blocks.append({**{key:value for key,value in original.items() if key!='text'},**block,
                           'sourceRevisionId':str(original['sourceRevisionId']),'sourceWorkId':str(original['sourceWorkId']),
                           'sourceKey':original.get('sourceKey','BODY'),'originalTextSha256':hashlib.sha256(original['text'].encode()).hexdigest(),
                           'blockId':source+':'+str(block['start'])+':'+str(block['end'])})
    output.mkdir(parents=True,exist_ok=False)
    with (output/'blocks.jsonl').open('w',encoding='utf-8') as stream:
        for block in blocks:stream.write(json.dumps(block,ensure_ascii=False)+'\n')
    vectors_path=output/'vectors.f32'
    if blocks:
        vectors=np.memmap(vectors_path,dtype=np.float32,mode='w+',shape=(len(blocks),768))
        try:
            for start in range(0,len(blocks),batch):
                selected=blocks[start:start+batch];vectors[start:start+len(selected)]=_vectors(encode([row['text'] for row in selected]),len(selected))
            vectors.flush()
        finally:vectors._mmap.close()
    else:vectors_path.write_bytes(b'')
    manifest={'schemaVersion':'dense-index-v1','featureSpaceId':'dense-'+_digest(config),'configuration':config,
              'blockCount':len(blocks),'sourceFieldCount':len(seen_sources),'inputManifestSha256':_digest(documents),
              'files':{name:_sha(output/name) for name in ['blocks.jsonl','vectors.f32']}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'READY').write_text(_sha(output/'manifest.json'),encoding='utf-8')
    return manifest


def load_dense_index(output,identity,tokens=192,overlap=48):
    output=Path(output)
    if not (output/'READY').is_file() or (output/'READY').read_text().strip()!=_sha(output/'manifest.json'):raise ValueError('Dense index not READY or manifest changed')
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'));expected=_configuration(identity,tokens,overlap)
    if manifest['configuration']!=expected or manifest['featureSpaceId']!='dense-'+_digest(expected):raise ValueError('Incompatible dense feature space; rebuild in a new generation')
    if set(manifest['files'])!={'blocks.jsonl','vectors.f32'}:raise ValueError('Unexpected dense-index component')
    for name,checksum in manifest['files'].items():
        if _sha(output/name)!=checksum:raise ValueError('Dense-index component changed: '+name)
    with (output/'blocks.jsonl').open(encoding='utf-8') as stream:blocks=[json.loads(line) for line in stream if line.strip()]
    if len(blocks)!=manifest['blockCount'] or (output/'vectors.f32').stat().st_size!=len(blocks)*768*4:raise ValueError('Dense-index shape differs from manifest')
    vectors=np.memmap(output/'vectors.f32',dtype=np.float32,mode='r',shape=(len(blocks),768)) if blocks else np.empty((0,768),dtype=np.float32)
    return {'manifest':manifest,'blocks':blocks,'vectors':vectors}


def search_dense(index,query_vectors,top_k=10,scan_rows=2048,exclude_manuscript_id=None):
    queries=np.asarray(query_vectors,dtype=np.float32)
    queries=_vectors(queries,len(queries))
    if top_k<1 or scan_rows<1:raise ValueError('Invalid dense search budget')
    results=[[] for _ in queries];blocks=index['blocks'];vectors=index['vectors']
    for start in range(0,len(blocks),scan_rows):
        stop=min(start+scan_rows,len(blocks));scores=queries@vectors[start:stop].T
        for query_index in range(len(queries)):
            candidates=results[query_index][:]
            for relative,block in enumerate(blocks[start:stop]):
                if exclude_manuscript_id is not None and block.get('manuscriptId') is not None and str(block['manuscriptId'])==str(exclude_manuscript_id):continue
                candidates.append({**block,'score':float(scores[query_index,relative]),'scoreType':'COSINE_DENSE_RETRIEVAL','featureSpaceId':index['manifest']['featureSpaceId']})
            results[query_index]=sorted(candidates,key=lambda row:(-row['score'],row['sourceRevisionId'],row['sourceKey'],row['start'],row['blockId']))[:top_k]
    return results


def hybrid_sources(literal_hits,dense_hits,maximum=30):
    if maximum<1:raise ValueError('Invalid hybrid source budget')
    dense={}
    for hit in dense_hits:
        key=str(hit['sourceRevisionId'])
        dense[key]=max(dense.get(key,-float('inf')),float(hit['score']))
    branches=[list(dict.fromkeys(str(hit['sourceRevisionId']) for hit in literal_hits)),
              sorted(dense,key=lambda key:(-dense[key],key))]
    scores={};provenance={}
    for name,keys in zip(['literal','dense'],branches):
        for rank,key in enumerate(keys,1):scores[key]=scores.get(key,0.)+1/(60+rank);provenance.setdefault(key,[]).append(name)
    return [{'sourceRevisionId':key,'fusionScore':scores[key],'retrievalBranches':provenance[key]} for key in sorted(scores,key=lambda key:(-scores[key],key))[:maximum]]
