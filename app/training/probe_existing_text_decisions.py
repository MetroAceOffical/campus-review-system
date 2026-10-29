"""Recheck existing authored cases against immutable business reference generations.

This is a diagnostic, not the planned independent400/1200 evaluation. Human
document-level labels are reused only within their original four-source scope.
Additional source alerts are reported as unjudged instead of being called false.
"""
import argparse,json,sys,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import file_sha256,digest_json,validate_result
from campus_detection.semantic import semantic_summary
from run_document_evaluation import atomic_json


def source_id(evidence):
    return evidence.get('sourceMetadata',{}).get('initialImportKey')


def decision(report,expected,judged_sources,normal,lexical_floor=None):
    alerts=set();literal=set();semantic=set()
    for item in report['evidence']:
        sid=source_id(item) or 'WORK:'+str(item['sourceWorkId'])
        if item.get('literalAcceptedCandidate',item['acceptedCandidate']):literal.add(sid)
        summary=item.get('semanticSummary',{}) if lexical_floor is None else semantic_summary(item.get('semanticWindows',[]),dict(report['actualConfig']['semanticPolicy'],lexicalFloor=lexical_floor))
        if summary.get('suspectedReuse'):semantic.add(sid)
    alerts=literal|semantic
    return dict(alerts=sorted(alerts),literalAlerts=sorted(literal),semanticAlerts=sorted(semantic),
                correctSources=sorted(alerts&set(expected)),expectedSources=sorted(expected),
                completeExpectedSources=bool(expected) and set(expected)<=alerts,
                scopedNormalAlert=bool(normal and alerts&set(judged_sources)),
                unjudgedAlerts=sorted(alerts-set(judged_sources)),normal=normal)


def prepare_cases():
    old=ROOT/'runtime/experiments/route-b-development-20261026'
    files=[old/name for name in ('development-12.json','development-originals.json','human-review/labels-v1.json')]
    recent=ROOT/'runtime/manual-demo/semantic-rewrites-20261027/materials.json';files.append(recent)
    labels=json.loads(files[2].read_text(encoding='utf-8'))
    if file_sha256(files[0])!=labels['samples_sha256']:raise ValueError('Reviewed case bytes changed')
    truth={row['id']:row for row in labels['labels']}
    judged={row['source_id'] for row in json.loads(files[1].read_text(encoding='utf-8'))}
    cases=[]
    for row in json.loads(files[0].read_text(encoding='utf-8')):
        label=truth[row['id']]
        if label['decision'] not in ('复用','正常') or label['expected_sources']!=row['expected_sources']:raise ValueError('Reviewed source label differs')
        cases.append(dict(caseId=row['id'],suite='HISTORICAL_REVIEWED12',text=row['text'],expected=row['expected_sources'],
                          judgedSources=sorted(judged),normal=label['decision']=='正常',originalGeneration='7',
                          truthScope='Single-reviewer document/source relationship; four supplied sources only, not span acceptance or natural independent gold'))
    library=json.loads((ROOT/'runtime/indexes/18/manifest.json').read_text(encoding='utf-8'))
    for row in json.loads(recent.read_text(encoding='utf-8')):
        source=next(d for d in library['documents'] if str(d['sourceWorkId'])==row['sourceWorkId'] and d.get('sourceKind','BODY')=='BODY')
        sid=source_id(source) or 'WORK:'+row['sourceWorkId']
        cases.append(dict(caseId=row['caseId'],suite='HISTORICAL_AUTHORED4',text='\n'.join(row['paragraphs']),expected=[sid],
                          judgedSources=[sid],normal=False,originalGeneration='17',truthScope='Known assistant-authored derivation; other source relationships unjudged'))
    assert len(cases)==16 and sum(c['normal'] for c in cases)==4
    return cases,files


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runtime/experiments') or output.exists():raise ValueError('Require a new project experiment directory')
    cases,files=prepare_cases();output.mkdir(parents=True)
    files += [Path(__file__),ROOT/'app/python/campus_detection/semantic.py',ROOT/'app/python/campus_detection/text.py',ROOT/'app/python/campus_detection/models.py']
    files += [ROOT/f'runtime/indexes/{g}/manifest.json' for g in ('7','17','18')]
    hashes={p.relative_to(ROOT).as_posix():file_sha256(p) for p in files}
    token=(ROOT/'runtime/private-config/internal-token').read_text().strip()
    def guard():
        for name,sha in hashes.items():
            if file_sha256(ROOT/name)!=sha:raise ValueError('Bound source changed: '+name)
    deadline=time.monotonic()+2*3600
    def request(path,value=None):
        while True:
            if time.monotonic()>deadline:raise TimeoutError('Two-hour finite resource wait expired')
            req=urllib.request.Request('http://127.0.0.1:18081'+path,data=None if value is None else json.dumps(value).encode(),headers={'X-Internal-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=240) as response:return json.loads(response.read())
            except urllib.error.HTTPError as failure:
                if failure.code!=409:raise
                detail=json.loads(failure.read())
                if detail.get('errorCode')!='PROCESS_BUSY':raise
                atomic_json(output/'status.json',dict(state='WAITING_SHARED_COMPUTE_SLOT',processed=len(rows),total=32))
                time.sleep(15)
    rows=[];started=time.perf_counter();health=request('/health');config=health['configs']['textConfig']
    if not health['ready'] or config['schemaVersion']!='text-v2':raise ValueError('Require current legacy text-v2 service')
    identity=dict(scope='EXISTING_AUTHORED_DIAGNOSTIC_ONLY',cases=cases,hashes=hashes,configuration=config,
                  normalTruthScope='Four previously reviewed sources only',formal400DevelopmentComplete=False,finalQueriesInferred=0,
                  newTrainingSamples=0,newWeights=False,productPolicyChanged=False)
    atomic_json(output/'run.json',identity)
    with (output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
        for case in cases:
            for generation in (case['originalGeneration'],'18'):
                guard();cid=case['caseId']+'-lib'+generation
                req=dict(taskId='stage24-'+cid,attemptId='stage24-'+cid,scene='PRECHECK',inputSnapshotKey='diagnostic:'+cid,
                         inputSha256=digest_json(case['text']),libraryGenerationId=generation,libraryManifestSha256=hashes[f'runtime/indexes/{generation}/manifest.json'],configId=config['configId'],text=case['text'],excludeManuscriptId=None)
                report=request('/detect/text',req);validate_result(report,req)
                if report['actualConfig']!=config or report['status']!='COMPLETED':raise ValueError('Actual report differs from bound method')
                row=dict(caseId=case['caseId'],suite=case['suite'],generation=generation,report=report,
                         variants={name:decision(report,case['expected'],case['judgedSources'],case['normal'],floor) for name,floor in [('current',None),('cachedFloor015',.15)]})
                rows.append(row);stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
                atomic_json(output/'status.json',dict(state='RUNNING_EXISTING_TEXT_DECISIONS',processed=len(rows),total=32,elapsedSeconds=time.perf_counter()-started))
    guard();results={}
    for generation in ('original','18'):
        selected=[r for r in rows if (r['generation']=='18')==(generation=='18')]
        for variant in ('current','cachedFloor015'):
            values=[r['variants'][variant] for r in selected]
            results[generation+'/'+variant]=dict(queries=len(values),positiveDocuments=sum(not v['normal'] for v in values),
                completeCorrectSourceDocuments=sum(v['completeExpectedSources'] for v in values),
                expectedSources=sum(len(v['expectedSources']) for v in values),correctSources=sum(len(v['correctSources']) for v in values),
                normalDocuments=sum(v['normal'] for v in values),scopedNormalAlerts=sum(v['scopedNormalAlert'] for v in values),
                normalAnySourceAlerts=sum(v['normal'] and bool(v['alerts']) for v in values),unjudgedSourceAlerts=sum(len(v['unjudgedAlerts']) for v in values))
    summary=dict(state='EXISTING_TEXT_DECISIONS_COMPLETE',queries=32,results=results,elapsedSeconds=time.perf_counter()-started,
                 finalQueriesInferred=0,normalPopulationFpr=None,formalDevelopmentComplete=False,productPolicyChanged=False)
    atomic_json(output/'summary.json',summary);atomic_json(output/'status.json',summary);print(json.dumps(summary))


if __name__=='__main__':main()
