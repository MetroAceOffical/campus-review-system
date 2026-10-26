"""Prepare directed campus contrastive groups from supported correspondence material."""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter,defaultdict
from pathlib import Path

from corpus import normalized,read_jsonl,eligible_correspondence
from construct_correspondence import verify_ready
from negative_basis import assess_difference,RULE_VERSION

ROOT=Path(__file__).resolve().parents[2]


def supported_group(positive,original,candidates,tokenizer):
    if any(len(tokenizer(text,add_special_tokens=True,truncation=False,verbose=False)['input_ids'])>512 for text in [positive['query'],positive['source']]):return None
    query_id='campus-query:'+hashlib.sha256(normalized(positive['query']).encode()).hexdigest()
    left={'sourceId':query_id,'text':positive['query'],'start':0,'end':len(positive['query']),
          'sourceClusterId':original['sourceClusterId'],'eventClusterId':original['eventClusterId'],
          'title':original['title'],'institutionName':original['institutionName'],'publishedAt':original.get('publishedAt')}
    negatives=[];sources=set();texts={normalized(positive['source'])}
    for candidate in candidates:
        key=normalized(candidate['text'])
        if candidate['sourceId'] in sources or key in texts:continue
        if len(tokenizer(candidate['text'],add_special_tokens=True,truncation=False,verbose=False)['input_ids'])>512:continue
        basis=assess_difference(left,candidate)
        if not basis['supported']:continue
        negatives.append({'source':candidate,'basis':basis});sources.add(candidate['sourceId']);texts.add(key)
        if len(negatives)==4:
            return {'queryId':query_id,'query':positive['query'],'positive':positive,'parentSourceId':original['documentId'],
                    'eventClusterId':original['eventClusterId'],'transformationKind':positive['transformationKind'],'negatives':negatives}
    return None


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    from transformers import AutoTokenizer
    parser=argparse.ArgumentParser();parser.add_argument('--pairs',type=Path,default=ROOT/'runtime/datasets/campus-correspondence-training-v1')
    parser.add_argument('--negatives',type=Path,default=ROOT/'runtime/datasets/campus-supported-negatives-v4')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-retrieval-training-v1');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):raise ValueError('Use project dataset output')
    if (output/'READY').exists():raise ValueError('Campus retrieval shard already frozen')
    pair_hashes=verify_ready(args.pairs);negative_hashes=verify_ready(args.negatives)
    pair_manifest=json.loads((args.pairs/'manifest.json').read_text())
    if not pair_manifest['formalScaleAndBalanceReady']:raise ValueError('Correspondence material has not reached formal scale/balance')
    partitions=ROOT/'runtime/datasets/campus-partitions-20261026-v1';partition_hashes=verify_ready(partitions)
    negative_manifest=json.loads((args.negatives/'manifest.json').read_text())
    if negative_manifest['sourceTrainSha256']!=partition_hashes['train.jsonl'] or pair_manifest['partitionHashes']['train.jsonl']!=partition_hashes['train.jsonl']:raise ValueError('Source partitions differ')
    originals={row['documentId']:row for row in read_jsonl(partitions/'train.jsonl')}
    pool=defaultdict(list);seen_candidates=defaultdict(set)
    for row in read_jsonl(args.negatives/'negative-pairs.jsonl'):
        parent=row['positiveSource']['sourceId'];candidate=row['candidateSource'];original=originals[candidate['sourceId']]
        if candidate['text']!=original['text'][candidate['start']:candidate['end']] or any(candidate[key]!=original[key] for key in ['sourceClusterId','eventClusterId']):raise ValueError('Candidate original provenance changed')
        key=(candidate['sourceId'],candidate['start'],candidate['end'])
        if key not in seen_candidates[parent]:pool[parent].append(candidate);seen_candidates[parent].add(key)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'runtime/models/final/bge-base-zh-v1.5/f03589ceff5aac7111bd60cfc7d497ca17ecac65',local_files_only=True,trust_remote_code=False,use_fast=True)
    qualified=defaultdict(list);seen_queries=set();stats=Counter()
    for positive in read_jsonl(args.pairs/'pairs.jsonl'):
        if positive['target']!=1:continue
        if not eligible_correspondence(positive) or positive['split']!='train' or len(positive['sourceIds'])!=1:raise ValueError('Invalid campus positive')
        parent=positive['sourceIds'][0];original=originals[parent];span=positive['sourceOffsets']
        if positive['source']!=original['text'][span['start']:span['end']]:raise ValueError('Positive original range changed')
        key=normalized(positive['query'])
        if key in seen_queries:stats['repeatedQueryTextsExcluded']+=1;continue
        group=supported_group(positive,original,pool[parent],tokenizer)
        if not group:stats['noFourSupportedDistinctNegativeSourcesOrTokenBudget']+=1;continue
        seen_queries.add(key);qualified[group['transformationKind']].append(group)
    # Keep generated paraphrases >=50% of groups and bound correlated windows per source.
    selected=[];source_counts=Counter()
    def take(groups,limit):
        count=0
        for group in sorted(groups,key=lambda row:row['queryId']):
            if count>=limit:break
            if source_counts[group['parentSourceId']]>=8:stats['sourceWindowCapExcluded']+=1;continue
            selected.append(group);source_counts[group['parentSourceId']]+=1;count+=1
        return count
    paraphrases=take(qualified['PARAPHRASE'],len(qualified['PARAPHRASE']))
    take(qualified['COPY_CONTROL'],paraphrases//2);take(qualified['SENTENCE_REORDER'],paraphrases//2)
    output.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(output/'auxiliary.sqlite')
    db.executescript('CREATE TABLE documents(id TEXT PRIMARY KEY,text TEXT NOT NULL); CREATE TABLE pairs(left_id TEXT,right_id TEXT,target INT,split TEXT,PRIMARY KEY(left_id,right_id));')
    def document(text,role):
        key=role+':'+hashlib.sha256(text.encode()).hexdigest();db.execute('INSERT OR IGNORE INTO documents VALUES(?,?)',(key,text));return key
    with (output/'groups.jsonl').open('w',encoding='utf-8') as stream:
        for group in selected:
            query=document(group['query'],'query');positive=document(group['positive']['source'],'passage')
            db.execute('INSERT INTO pairs VALUES(?,?,?,?)',(query,positive,1,'train'))
            for item in group['negatives']:
                passage=document(item['source']['text'],'passage');db.execute('INSERT INTO pairs VALUES(?,?,?,?)',(query,passage,0,'train'))
            stream.write(json.dumps(group,ensure_ascii=False)+'\n')
    db.commit();document_count=db.execute('SELECT count(*) FROM documents').fetchone()[0];pair_count=db.execute('SELECT count(*) FROM pairs').fetchone()[0];db.close()
    formal=len(selected)>=1000 and paraphrases>=len(selected)*.5
    manifest={'taskType':'CONTENT_CORRESPONDENCE','objective':'DIRECTED_CONTRASTIVE_RETRIEVAL','split':'train','ruleVersion':RULE_VERSION,
              'state':'CAMPUS_RETRIEVAL_SHARD_READY' if formal else 'INSUFFICIENT_CAMPUS_RETRIEVAL_GROUPS',
              'formalScaleAndBalanceReady':formal,'trainGroups':len(selected),'uniqueQueryTexts':len(selected),'uniquePairs':pair_count,'documents':document_count,
              'positivePairs':len(selected),'negativePairs':len(selected)*4,'independentQuerySourceParents':len(source_counts),
              'automaticQueryEventGroups':len({row['eventClusterId'] for row in selected}),'maxGroupsPerSourceParent':8,
              'transformationCounts':dict(Counter(row['transformationKind'] for row in selected)),
              'qualifiedBeforeSourceBalance':{kind:len(rows) for kind,rows in qualified.items()},'statistics':dict(stats),
              'maxTokensPerSide':512,'sourceTrainSha256':partition_hashes['train.jsonl'],'correspondencePairsSha256':pair_hashes['pairs.jsonl'],
              'negativeManifestSha256':negative_hashes['manifest.json'],'neuralTrainingStarted':False,
              'scope':'Every generated query is independently rechecked against actual candidate text facts. Four distinct negative source IDs AND normalized texts; no inherited detector scores or silent prefix truncation. Window counts are not independent articles/events.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'READY').write_text(json.dumps({name:sha(output/name) for name in ['auxiliary.sqlite','groups.jsonl','manifest.json']},indent=2),encoding='utf-8');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
