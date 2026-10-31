"""Training-lineage isolation using stable sources and conservative near duplicates."""
from collections import Counter,defaultdict
from difflib import SequenceMatcher
import hashlib,heapq,json,unicodedata
from pathlib import Path
from .preparation import prepared,sha

ROOT=Path(__file__).resolve().parents[3]
FIELDS=('sentences','groups','origins','normalized','texts')
SOURCE_FIELDS=('group_id','source_id','source_cluster_id','event_cluster_id')


def normalize(text):return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())


def collect(rows):
    result={key:set() for key in FIELDS}
    for row in rows:
        if row.get('_partitionGroup'):result['groups'].add(str(row['_partitionGroup']))
        for field in SOURCE_FIELDS:
            if row.get(field) not in (None,''):result['origins'].add(hashlib.sha256((field+'\0'+str(row[field]).strip()).encode()).hexdigest())
        for key in ('sentence1','sentence2'):
            text=row[key];result['sentences'].add(hashlib.sha256(text.encode()).hexdigest());text=normalize(text)
            if text:result['normalized'].add(hashlib.sha256(text.encode()).hexdigest())
            if len(text)>=64:result['texts'].add(text)
    return result


def merge(*values):return {key:set().union(*(value.get(key,[]) for value in values)) for key in FIELDS}


def fingerprints(text):
    return heapq.nsmallest(16,{hashlib.blake2b(text[i:i+8].encode(),digest_size=8).digest() for i in range(len(text)-7)})


def near_overlap(left,right):
    if not left or not right:return False
    references=list(right);index=defaultdict(list)
    for i,text in enumerate(references):
        for key in fingerprints(text):index[key].append(i)
    for text in left:
        candidates=Counter(i for key in fingerprints(text) for i in index.get(key,[]))
        for i,shared in candidates.items():
            other=references[i]
            if shared>=4 and min(len(text),len(other))/max(len(text),len(other))>=.94 and SequenceMatcher(None,text,other,autojunk=False).ratio()>=.97:return True
    return False


def require_disjoint(left,right,message):
    if any(set(left.get(key,[]))&set(right.get(key,[])) for key in FIELDS if key!='texts') or near_overlap(left.get('texts',[]),right.get('texts',[])):raise ValueError(message)


def ancestry(folder):
    """Enrich legacy web records from their saved, hash-matched preparation.

    Model artifacts remain immutable. New lineage files contain the merged sets;
    older files are supplemented by the verified preparation and parent chain.
    """
    result={'train':merge(),'holdout':merge()};pending=[(Path(folder).resolve(),None)];seen=set()
    while pending:
        current,expected=pending.pop()
        if not current.is_relative_to(ROOT/'runtime') or current in seen:raise ValueError('模型训练谱系无效')
        seen.add(current);manifest=json.loads((current/'manifest.json').read_text(encoding='utf-8'))
        if expected and sha(current/'manifest.json')!=expected:raise ValueError('模型祖先工件身份已变化')
        saved={}
        for name,side in [('train-identities.json','train'),('lineage-training-identities.json','train'),('protected-identities.json','holdout')]:
            path=current/name
            if path.is_file():
                if manifest.get('artifacts',{}).get(name)!=sha(path):raise ValueError('模型训练隔离记录校验失败')
                saved[name]=json.loads(path.read_text(encoding='utf-8'));result[side]=merge(result[side],saved[name])
        config_file=current.parent/'config.json'
        config=json.loads(config_file.read_text(encoding='utf-8')) if config_file.is_file() else {}
        if config.get('preparation'):
            source=Path(config['preparation']).resolve()
            if not source.is_relative_to(ROOT/'runtime') or sha(source/'manifest.json')!=manifest['preparationSha256']:raise ValueError('历史训练划分校验失败')
            _,splits=prepared(source);result['train']=merge(result['train'],collect(splits['train']))
            result['holdout']=merge(result['holdout'],collect([row for name,rows in splits.items() if name!='train' for row in rows]))
        complete=all(key in saved.get('lineage-training-identities.json',{}) and key in saved.get('protected-identities.json',{}) for key in FIELDS)
        parent=config.get('warmstart')
        if parent and not complete:
            if parent['manifestSha256']!=manifest.get('warmstart',{}).get('parentManifestSha256'):raise ValueError('历史父模型声明不一致')
            pending.append((Path(parent['folder']).resolve(),parent['manifestSha256']))
    return result


def require_evaluation(model_folder,prepared_folder):
    manifest,splits=prepared(prepared_folder)
    require_disjoint(collect(splits['test']),ancestry(model_folder)['train'],'评价集与模型及祖先训练材料存在来源/句子或近重复重合，请选择独立数据版本')
    return manifest,splits
