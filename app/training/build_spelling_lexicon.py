"""Freeze train-partition document frequencies for conservative homophone support."""
import collections,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import file_sha256


def main():
    source=ROOT/'runtime/datasets/campus-quality-20261028-v1/train.jsonl'
    formal=json.loads((ROOT/'runtime/experiments/final-training-20261028/corrected-material-stage-v1/pipeline.json').read_text(encoding='utf-8'))
    source_sha=file_sha256(source)
    if source_sha!=formal['partitions']['train.jsonl']:raise ValueError('Frozen train partition changed')
    output=ROOT/'runtime/datasets/grammar-spelling-lexicon-20261029-v1'
    if output.exists():raise ValueError('Preserve frozen lexicon')
    counts=collections.Counter();documents=0
    for line in source.open(encoding='utf-8'):
        row=json.loads(line)
        if row['split']!='train':raise ValueError('Only existing train documents are allowed')
        grams=set()
        for match in re.finditer(r'[\u4e00-\u9fff]+',row['title']+'\n'+row['text']):
            text=match.group()
            for size in (2,3,4):grams.update(text[i:i+size] for i in range(len(text)-size+1))
        counts.update(grams);documents+=1
    output.mkdir()
    payload=dict(schemaVersion='spelling-lexicon-v1',sourceSha256=source_sha,sourceDocuments=documents,
                 counts={k:v for k,v in sorted(counts.items()) if v>=2 or len(k)==2},minimumCandidateDocuments=5,minimumContextDocuments=2,
                 sourceScope='Existing train partition only; document frequencies, no model-weight training, no dev/final text or expected corrections')
    (output/'lexicon.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    ready={'lexicon.json':file_sha256(output/'lexicon.json')};(output/'READY').write_text(json.dumps(ready,sort_keys=True),encoding='utf-8')
    print(json.dumps(dict(documents=documents,retainedNgrams=len(payload['counts']),sourceSha256=source_sha,**ready)))


if __name__=='__main__':main()
