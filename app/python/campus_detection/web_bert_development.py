"""Compare a registered web scorer on the existing development material."""
import json,sys,time,urllib.request,urllib.error,uuid
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256,validate_result
from .models import ROOT


def evaluate(config):
    sys.path.insert(0,str(ROOT/'app/training'))
    from probe_existing_text_decisions import prepare_cases,decision
    from text_verifier_metrics import counts
    from campus_workbench.preparation import write_json
    output=Path(config['output']).resolve();output.mkdir(exist_ok=True)
    if not output.is_relative_to(ROOT/'runtime/delivery/releases'):raise ValueError('开发评价输出位置无效')
    token=(ROOT/'runtime/private-config/internal-token').read_text().strip()
    port=config.get('port',18081)
    def request(path,data=None):
        req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),headers={'X-Internal-Token':token,'Content-Type':'application/json'})
        for retry in range(120):
            try:
                with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code not in (409,503) or retry==119:raise ValueError('开发评价服务未完成：'+str(error.code)) from error
                time.sleep(1)
    health=request('/health');baseline=health['configs']['textConfig']['configId'];candidate=config['configId']
    cases,files=prepare_cases()
    normal=ROOT/'runtime/experiments/final-training-20261029/real-news-corroboration-v1/material.json'
    if not normal.is_file():raise ValueError('缺少既有真实新闻开发材料')
    real=json.loads(normal.read_text(encoding='utf-8'))['cases'];files.append(normal)
    library=ROOT/'runtime/indexes/18/manifest.json'
    corpus=[('known',row) for row in cases]+[('realNews',row) for row in real]
    sources={p.relative_to(ROOT).as_posix():file_sha256(p) for p in [*files,library,Path(__file__),ROOT/'app/training/probe_existing_text_decisions.py',ROOT/'app/training/text_verifier_metrics.py']}
    write_json(output/'development-material.json',{'sources':sources,'knownCases':len(cases),'realNewsCases':len(real),'libraryGenerationId':'18','baselineConfigId':baseline,'candidateConfigId':candidate})
    results=[];started=time.monotonic();total=len(corpus)*2
    with (output/'development-predictions.jsonl').open('w',encoding='utf-8') as stream:
        for suite,row in corpus:
            for method,key in [('baseline',baseline),('candidate',candidate)]:
                attempt='web-bert-dev-'+str(uuid.uuid4())
                req=dict(taskId=attempt,attemptId=attempt,scene='PRECHECK',versionId=attempt,inputSnapshotKey='development:'+attempt,inputSha256=digest_json(row['text']),libraryGenerationId='18',libraryManifestSha256=file_sha256(library),configId=key,text=row['text'],excludeManuscriptId=None)
                report=request('/detect/text',req);validate_result(report,req)
                item={'suite':suite,'caseId':row.get('caseId',row.get('documentId')),'method':method,'report':report}
                if suite=='known':item['decision']=decision(report,row['expected'],row['judgedSources'],row['normal'])
                item['alertedSources']=sorted({e['sourceWorkId'] for e in report.get('evidence',[]) if e.get('acceptedCandidate') or e.get('semanticSummary',{}).get('suspectedReuse')})
                results.append(item);stream.write(json.dumps(item,ensure_ascii=False)+'\n');stream.flush()
                write_json(output/'development-progress.json',{'processed':len(results),'total':total,'elapsedSeconds':time.monotonic()-started})
    summary={'status':'COMPLETED','knownCases':len(cases),'realNewsCases':len(real),'requests':len(results),'elapsedSeconds':time.monotonic()-started,'sourceScope':'EXISTING_DEVELOPMENT','finalTestUsed':False}
    for method in ('baseline','candidate'):
        summary[method]={'known':counts([r['decision'] for r in results if r['suite']=='known' and r['method']==method]),'realNewsAlertedDocuments':sum(bool(r['alertedSources']) for r in results if r['suite']=='realNews' and r['method']==method)}
    write_json(output/'development-summary.json',summary)
    paths=[output/n for n in ['development-material.json','development-predictions.jsonl','development-summary.json']]
    return {'development':summary,'verifiedFiles':{**sources,**{p.relative_to(ROOT).as_posix():file_sha256(p) for p in paths}}}
