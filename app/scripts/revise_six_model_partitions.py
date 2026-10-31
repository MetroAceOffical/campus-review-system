import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.curated_bundles import isolate,exclude_near_training
from campus_workbench.preparation import sha,write_json
source=ROOT/'runtime/datasets/six-model-20261031-v1';target=ROOT/'runtime/datasets/six-model-20261031-v2'
if (target/'manifest.json').exists():raise RuntimeError('Already frozen')
target.mkdir(exist_ok=True)
manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'));sets={}
for name in manifest['sets']:sets[name]=[json.loads(s) for s in (source/(name+'.jsonl')).read_text(encoding='utf8').splitlines() if s]
all_rows,conflicts,conflict_counts=isolate([r for name,rows in sets.items() if name!='combined-pairs' for r in rows]);kept,bad,near_counts=exclude_near_training(all_rows)
allowed={(r['sentence1'],r['sentence2'],r['split']) for r in kept};allowed|={(b,a,p) for a,b,p in list(allowed)}
result={'previousPackageSha256':sha(source/'manifest.json'),'nearDuplicateQuarantine':near_counts,'conflicts':conflict_counts,'sets':{}}
from collections import Counter
for name,rows in sets.items():
    rows=[r for r in rows if (r['sentence1'],r['sentence2'],r['split']) in allowed]
    path=target/(name+'.jsonl');path.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows),encoding='utf8')
    result['sets'][name]={'path':str(path.relative_to(ROOT)),'sha256':sha(path),'rows':len(rows),'partitions':{p:dict(Counter(str(r['label']) for r in rows if r['split']==p)) for p in ('train','validation','test')}}
(target/'quarantine.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in bad+conflicts),encoding='utf8')
write_json(target/'manifest.json',result);print(json.dumps(result,ensure_ascii=False))
