"""Compose immutable clean versions; original bodies and partitions stay intact."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .datasets import MAX_INTERNAL_BYTES, MAX_ROWS, read_dataset, clean_dataset

ROOT=Path(__file__).resolve().parents[3]
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')


def compose(input_path,output,kind,emit):
    input_path=Path(input_path).resolve();output=Path(output).resolve();boundary=ROOT/'runtime/workbench/datasets'
    if not input_path.is_relative_to(boundary) or not output.is_relative_to(boundary):raise ValueError('组合版本须保存在项目数据目录')
    if output.exists():raise ValueError('组合版本已存在，请创建新任务')
    if input_path.stat().st_size>20000:raise ValueError('组合来源清单过大')
    config=json.loads(input_path.read_text(encoding='utf-8'));sources=config.get('sources')
    if config.get('schemaVersion')!=1 or config.get('kind')!=kind or not isinstance(sources,list) or not 2<=len(sources)<=10:raise ValueError('请选择2—10个同类型清洗版本')
    identities=set();datasets=set();files=[];total_bytes=0
    events=[]
    def notify(value):
        event={**value,"sequence":len(events)+1};events.append(event);emit(event)
    for source in sources:
        dataset,version=source.get('datasetId',''),source.get('versionId','')
        if not isinstance(dataset,str) or not isinstance(version,str) or not UUID.fullmatch(dataset) or not UUID.fullmatch(version) or (dataset,version) in identities or dataset in datasets:raise ValueError('组合来源版本无效或重复')
        identities.add((dataset,version));datasets.add(dataset);path=(boundary/dataset/version/'corpus.jsonl').resolve()
        if not path.is_relative_to(boundary) or not re.fullmatch('[0-9a-f]{64}',str(source.get('sha256',''))) or sha(path)!=source['sha256']:raise ValueError('组合来源文件校验失败')
        total_bytes+=path.stat().st_size
        if total_bytes>MAX_INTERNAL_BYTES:raise ValueError('组合来源合计不能超过512MiB')
        files.append(path)
    rows=[];lineage=[];summaries=[]
    notify({'stage':'COMPOSING','processed':0,'total':len(sources)})
    for source,path in zip(sources,files):
        data=read_dataset(path,kind,internal=True)
        if data['sourceSha256']!=source['sha256'] or data['issues']:raise ValueError('组合来源内容不完整或已变化')
        start=len(rows)
        for row in data['rows']:
            if len(rows)>=MAX_ROWS:raise ValueError('组合后最多100000行，请分批组合')
            record={key:value for key,value in row.items() if not key.startswith('_') or key=='_provenance'}
            record['id']=source['datasetId']+':'+row['id']
            rows.append(record);lineage.append({'rowNumber':len(rows),'composedRowId':record['id'],'datasetId':source['datasetId'],'versionId':source['versionId'],'sourceRowId':row['id'],'sourceRowNumber':row['_rowNumber'],'inputSha256':source['sha256']})
        summaries.append({key:source[key] for key in ('datasetId','versionId','name','sha256')}|{'inputRows':len(rows)-start,'retainedRows':0,'duplicateRows':0,'quarantineRows':0})
        notify({'stage':'COMPOSING','processed':len(summaries),'total':len(sources),'rows':len(rows)})
    if not rows:raise ValueError('组合来源没有有效记录')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='compose-') as temporary:
        joined=Path(temporary)/'joined.jsonl'
        with joined.open('w',encoding='utf-8',newline='\n') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
        joined_sha=sha(joined)
        data=read_dataset(joined,kind,internal=True)
        cleaned=clean_dataset(data,options={'strip_html':False,'normalize_whitespace':False},on_event=notify)
    output.mkdir(parents=True,exist_ok=False)
    manifest={'schemaVersion':1,'processorVersion':'composition-1','taskType':'DATASET_COMPOSITION','status':'COMPLETED','kind':kind,
              'inputSha256':sha(input_path),'joinedInputSha256':joined_sha,'inputRows':cleaned['inputRows'],
              'outputRows':cleaned['outputRows'],'duplicateRows':cleaned['duplicateRows'],'quarantineRows':len(cleaned['quarantine']),
              'options':cleaned['options'],'mapping':data['mapping'],'artifacts':{}}
    by_source={item['datasetId']+':'+item['versionId']:item for item in summaries}
    changes={row['rowNumber']:row for row in cleaned['changes']}
    with (output/'lineage.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for row in lineage:
            change=changes.get(row['rowNumber']);action=change['action'] if change else 'QUARANTINED'
            row['action']=action
            if change:row['retainedId']=change['retainedId']
            summary=by_source[row['datasetId']+':'+row['versionId']]
            summary[{'RETAINED':'retainedRows','DUPLICATE':'duplicateRows','QUARANTINED':'quarantineRows'}[action]]+=1
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'schemaVersion':1,'sources':summaries,'inputRows':manifest['inputRows'],'outputRows':manifest['outputRows'],'duplicateRows':manifest['duplicateRows'],'quarantineRows':manifest['quarantineRows'],'policy':{'rowIds':'DATASET_NAMESPACE','sourceEventGroups':'ORIGINAL_CONSERVATIVE_GROUPS','conflicts':'QUARANTINE','split':'PRESERVE'},'joinedInputSha256':joined_sha}
    write(output/'composition.json',report)
    for name,records in [('corpus.jsonl',cleaned['rows']),('quarantine.jsonl',cleaned['quarantine']),('changes.jsonl',cleaned['changes'])]:
        with (output/name).open('w',encoding='utf-8',newline='\n') as stream:
            for row in records:stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    write(output/'audit.json',cleaned['before'])
    write(output/'cleaning.json',{key:value for key,value in cleaned.items() if key not in ('rows','quarantine','changes')})
    final={'stage':'COMPLETED','processed':len(rows),'total':len(rows),'outputRows':manifest['outputRows'],'sequence':len(events)+1}
    with (output/'events.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for event in events+[final]:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
    for name in ('corpus.jsonl','quarantine.jsonl','changes.jsonl','audit.json','cleaning.json','events.jsonl','composition.json','lineage.jsonl'):
        manifest['artifacts'][name]=sha(output/name)
    write(output/'manifest.json',manifest)
    emit(final)
    return manifest
