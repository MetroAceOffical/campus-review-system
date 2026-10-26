"""Mine aligned, same-split difficult candidates. Ranking never creates negative truth."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from transformers import AutoTokenizer

from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]


def aligned_windows(text,tokenizer,window=240,overlap=48):
    offsets=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True,truncation=False,verbose=False)['offset_mapping']
    rows=[]
    for token_start in range(0,len(offsets),window-overlap):
        chosen=offsets[token_start:token_start+window]
        nonempty=[pair for pair in chosen if pair[1]>pair[0]]
        if not nonempty:continue
        start,end=nonempty[0][0],nonempty[-1][1]
        rows.append({'start':start,'end':end,'text':text[start:end],'tokens':len(chosen)})
        if token_start+window>=len(offsets):break
    return rows


def rank_outside_event(scores,blocked,maximum=100):
    values=scores.copy();values[blocked]=-np.inf
    if not len(values):return []
    selected=np.arange(len(values)) if len(values)<=maximum else np.argpartition(-values,maximum-1)[:maximum]
    return [int(i) for i in sorted(selected,key=lambda i:(-float(values[i]),int(i))) if np.isfinite(values[i])]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--partitions',type=Path,default=ROOT/'runtime/datasets/campus-partitions-20261026-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/datasets/campus-correspondence-candidates-v1')
    parser.add_argument('--sources-per-window',type=int,default=30)
    args=parser.parse_args()
    if (args.output/'READY').exists():raise RuntimeError('Candidate version already frozen')
    args.output.mkdir(parents=True,exist_ok=True)
    hashes=verify_ready(args.partitions)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'runtime/experiments/route-b-development-20261026/model',local_files_only=True,trust_remote_code=False,use_fast=True)
    originals=list(read_jsonl(args.partitions/'train.jsonl'))
    windows=[]
    for row in originals:
        for index,window in enumerate(aligned_windows(row['text'],tokenizer)):
            if len(window['text'].strip())<64:continue
            windows.append({**window,'windowId':row['documentId']+':'+str(index),'sourceId':row['documentId'],
                            'sourceClusterId':row['sourceClusterId'],'eventClusterId':row['eventClusterId'],
                            'institutionName':row['institutionName'],'title':row['title'],'publishedAt':row.get('publishedAt')})
    with (args.output/'windows.jsonl').open('w',encoding='utf-8') as stream:
        for row in windows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(2,3),max_features=40000,dtype=np.float32)
    matrix=vectorizer.fit_transform([row['text'] for row in windows])
    event_indices=defaultdict(list)
    for index,row in enumerate(windows):event_indices[row['eventClusterId']].append(index)
    count=0;parents=set()
    with (args.output/'candidates.jsonl').open('w',encoding='utf-8') as stream:
        for index,row in enumerate(windows):
            scores=(matrix[index]@matrix.T).toarray()[0]
            order=rank_outside_event(scores,np.array(event_indices[row['eventClusterId']],dtype=np.intp))
            order=sorted(order,key=lambda i:(-float(scores[i]),windows[i]['windowId']))
            used=set()
            for rank,other_index in enumerate(order,1):
                other=windows[other_index]
                if other['eventClusterId']==row['eventClusterId'] or other['sourceClusterId']==row['sourceClusterId'] or other['sourceId'] in used:continue
                if scores[other_index]<.08:continue
                if len(tokenizer(row['text'],other['text'],truncation=False)['input_ids'])>512:raise ValueError('Joint window unexpectedly exceeds budget')
                record={'candidateId':hashlib.sha256((row['windowId']+':'+other['windowId']).encode()).hexdigest(),
                        'taskType':'CONTENT_CORRESPONDENCE','split':'train','labelOrigin':'unlabelled_mined_candidate','labelConfidence':'unknown',
                        'querySource':row,'candidateSource':other,'lexicalRank':rank,'lexicalScore':float(scores[other_index]),
                        'target':None,'needsContentDifferenceBasis':True}
                stream.write(json.dumps(record,ensure_ascii=False)+'\n');count+=1;parents.add(row['sourceId']);used.add(other['sourceId'])
                if len(used)>=args.sources_per_window:break
            if index%500==0:
                (args.output/'progress.json').write_text(json.dumps({'processedWindows':index,'totalWindows':len(windows),'candidateCount':count,'labelsCreated':0}),encoding='utf-8')
    manifest={'state':'ALIGNED_CANDIDATES_NOT_LABELLED_TRAINING_PAIRS','windowCount':len(windows),'candidateCount':count,
              'sourceParentsWithCandidates':len(parents),'sourceTrainSha256':hashes['train.jsonl'],'windowTokens':240,'overlapTokens':48,'jointBudget':512,
              'labelsCreated':0,'maxDistinctSourcesPerWindow':args.sources_per_window,'sameEventExcludedBeforeRanking':True,
              'scope':'Offline mining budget is independent of inference Top3. No model score or lexical rank is interpreted as noncorrespondence. Content-difference evidence and label provenance are still required.'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    ready={}
    for path in args.output.iterdir():
        if path.is_file():
            with path.open('rb') as file:ready[path.name]=hashlib.file_digest(file,'sha256').hexdigest()
    (args.output/'READY').write_text(json.dumps(ready,indent=2),encoding='utf-8');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
