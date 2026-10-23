import json
from pathlib import Path
import time
from campus_ocr.recognizer import ROOT,recognize
from campus_shared.contracts import file_sha256

def run_probe():
    started=time.perf_counter();records=[]
    for number,name in enumerate(('mixed-known.png','mixed-blurred.png'),1):
        path=ROOT/'validation/remaining/vision/inputs'/name
        request={'taskId':'1','attemptId':str(number),'fileId':'ocr-probe-'+str(number),'path':str(path),'fileSha256':file_sha256(path)}
        result=recognize(request)
        records.append({'inputSha256':request['fileSha256'],'result':result})
    local=ROOT/'runtime/probes/M05';local.mkdir(parents=True,exist_ok=True)
    evidence=local/'actual-ocr.json';evidence.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    clear,blur=(item['result'] for item in records)
    assert clear['recognitionLines']
    assert all(0<=x<=record['result']['originalWidth'] and 0<=y<=record['result']['originalHeight'] for record in records for line in record['result']['recognitionLines'] for x,y in line['polygon'])
    summary={'actualRuns':2,'clearLineCount':len(clear['recognitionLines']),'blurLineCount':len(blur['recognitionLines']),
             'blurNoReuseClaim':blur['noReuseClaim'],'blurQualityFlags':blur['qualityFlags'],'inputHashes':[record['inputSha256'] for record in records],
             'configId':clear['actualConfig']['configId'],'modelFiles':clear['actualConfig']['modelFiles'],'localEvidenceSha256':file_sha256(evidence),
             'elapsedSeconds':time.perf_counter()-started,'scope':'current clear/blur inference probe; no real-image transcription accuracy claim'}
    (ROOT/'docs/midterm/evidence/M05-ocr.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary
