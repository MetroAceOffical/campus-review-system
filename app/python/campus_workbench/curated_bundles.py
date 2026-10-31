"""Stable training-domain subdivisions; never move a held-out row to training."""
from collections import Counter,defaultdict
from difflib import SequenceMatcher
import hashlib,heapq,unicodedata

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())

def partition(identity):
    value=int(hashlib.sha256(('six-model-20261031\0'+identity).encode()).hexdigest()[:8],16)%100
    return 'train' if value<80 else 'validation' if value<90 else 'test'

def isolate(rows):
    """Quarantine conflicting duplicates and all cross-partition sentences."""
    pairs={};conflicts=set();counts=Counter()
    for row in rows:
        key=tuple(sorted((normalized(row['sentence1']),normalized(row['sentence2']))))
        if not all(key):counts['empty']+=1;continue
        if key in pairs:
            old=pairs[key]
            if int(old['label'])!=int(row['label']) or old['split']!=row['split']:conflicts.add(key)
            else:counts['duplicate']+=1
        else:pairs[key]=row
    owners=defaultdict(set)
    for row in pairs.values():
        for field in ('sentence1','sentence2'):owners[normalized(row[field])].add(row['split'])
    kept=[];quarantine=[]
    for key,row in pairs.items():
        reason='conflicting_pair' if key in conflicts else 'cross_partition_sentence' if any(len(owners[normalized(row[f])])>1 for f in ('sentence1','sentence2')) else None
        if reason:counts[reason]+=1;quarantine.append(dict(row,reason=reason))
        else:kept.append(row)
    return kept,quarantine,dict(counts)

def exclude_near_training(rows):
    """Keep test identity fixed; quarantine near matches from earlier folds.

    Matches the model lineage guard's >=64 characters, >=4 shared bottom-16
    fingerprints, length ratio >=.94 and SequenceMatcher >=.97 criteria.
    """
    def fingerprints(text):
        return heapq.nsmallest(16,{hashlib.blake2b(text[i:i+8].encode(),digest_size=8).digest() for i in range(len(text)-7)})
    rejected=[];counts=Counter();kept=list(rows)
    for part,protected in [('validation',{'test','calibration'}),('train',{'validation','test','calibration'})]:
        texts=sorted({normalized(row[f]) for row in kept if row['split'] in protected for f in ('sentence1','sentence2') if len(normalized(row[f]))>=64})
        index=defaultdict(list)
        for i,text in enumerate(texts):
            for key in fingerprints(text):index[key].append(i)
        matches={}
        def overlaps(text):
            if text in matches:return matches[text]
            candidates=Counter(i for key in fingerprints(text) for i in index.get(key,[]))
            found=any(shared>=4 and min(len(text),len(texts[i]))/max(len(text),len(texts[i]))>=.94 and SequenceMatcher(None,text,texts[i],autojunk=False).ratio()>=.97 for i,shared in candidates.items())
            matches[text]=found;return found
        next_rows=[]
        for row in kept:
            if row['split']==part and any(len(text:=normalized(row[f]))>=64 and overlaps(text) for f in ('sentence1','sentence2')):
                rejected.append(dict(row,reason='near_protected_sentence'));counts[part]+=1
            else:next_rows.append(row)
        kept=next_rows
    return kept,rejected,dict(counts)
