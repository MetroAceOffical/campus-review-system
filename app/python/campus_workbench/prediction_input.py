"""Read fixed uploaded sentence pairs for prediction only, without training labels."""
import csv
import hashlib
import io
import json
from pathlib import Path

MAX_BYTES=50*1024*1024
MAX_ROWS=100000
MAX_TEXT=20000
ALIASES={'sentence1':('sentence1','text1','文本一','句子一','原文'),
         'sentence2':('sentence2','text2','文本二','句子二','待比对文本'),
         'label':('label','标签'),'id':('id','编号')}


def read_prediction_input(descriptor,runtime):
    runtime=Path(runtime).resolve();path=Path(descriptor['path']).resolve()
    if not path.is_relative_to(runtime/'workbench/computations') or not path.is_file():
        raise ValueError('预测文件不在本项目任务目录内')
    format=descriptor.get('format')
    if format not in ('csv','jsonl') or path.name!='prediction-source.'+format:raise ValueError('预测文件格式无效')
    if path.stat().st_size>MAX_BYTES:raise ValueError('预测文件不能超过50MiB')
    raw=path.read_bytes()
    if not raw or len(raw)>MAX_BYTES:raise ValueError('请选择不超过50MiB的预测文件')
    if hashlib.sha256(raw).hexdigest()!=descriptor.get('sha256'):raise ValueError('预测输入文件校验失败')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('预测文件须使用UTF-8编码') from None
    csv.field_size_limit(MAX_BYTES)
    def records():
        if format=='csv':
            reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
            if reader.fieldnames:reader.fieldnames=[name.strip().lower() for name in reader.fieldnames]
            if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('CSV表头缺失或重复')
            for row in reader:
                if None in row:raise ValueError('CSV列数与表头不一致')
                yield row
        else:
            for number,line in enumerate(io.StringIO(text),1):
                if not line.strip():continue
                try:yield json.loads(line)
                except ValueError:raise ValueError(f'JSONL第{number}行格式无效') from None
    rows=[];seen=set()
    try:
        for number,record in enumerate(records(),1):
            if number>MAX_ROWS:raise ValueError('预测文件最多100000行')
            if not isinstance(record,dict):raise ValueError(f'第{number}行须为句对对象')
            row={}
            for field,aliases in ALIASES.items():
                keys=[key for key in aliases if key in record]
                if len(keys)>1:raise ValueError(f'第{number}行{field}重复映射')
                if keys:row[field]=record[keys[0]]
            for field in ('sentence1','sentence2'):
                value=row.get(field)
                if not isinstance(value,str) or not value.strip() or len(value)>MAX_TEXT:
                    raise ValueError(f'第{number}行{field}须为1—20000字的文本')
            label=row.get('label')
            if isinstance(label,str):label=label.strip()
            if label is None or isinstance(label,str) and not label.strip():row.pop('label',None)
            elif type(label) is int and label in (0,1) or isinstance(label,str) and label in ('0','1'):row['label']=int(label)
            else:raise ValueError(f'第{number}行标签仅支持0或1')
            identifier=row.get('id')
            if identifier is None or identifier=='':identifier=str(number)
            if isinstance(identifier,bool) or not isinstance(identifier,(str,int)) or not 1<=len(str(identifier))<=200:
                raise ValueError(f'第{number}行编号无效')
            row['id']=str(identifier)
            if row['id'] in seen:raise ValueError(f'第{number}行编号重复')
            seen.add(row['id']);rows.append(row)
    except csv.Error:raise ValueError('CSV内容格式无效，请检查引号和分隔符') from None
    if not rows:raise ValueError('预测文件没有有效句对')
    return rows
