"""Read-only error archive of committed image-development predictions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from corpus import read_jsonl
from construct_correspondence import verify_ready
from evaluate_image_pipeline import counts, validate_saved, atomic_json, ROOT
from run_campus_stage import stage_lock
from campus_shared.contracts import digest_json, file_sha256

TRANSFORMS = ('original','resize','jpeg','crop','text_overlay','watermark','tint')
REASONS = ('EXECUTION_FAILURE','SOURCE_UNAVAILABLE','CANDIDATE_BUDGET','NOT_RECALLED','LOW_TEXTURE',
           'TOO_FEW_UNIQUE_MATCHES','DEGENERATE_GEOMETRY','WEAK_GEOMETRY','INSUFFICIENT_SPATIAL_SUPPORT',
           'WRONG_SCOPE','UNRESOLVED')


def reason(row):
    if row.get('error'):
        return 'EXECUTION_FAILURE'
    if row['enhancedAccepted']:
        return None if row['scopeCorrect'] else 'WRONG_SCOPE'
    geometry = row.get('geometry')
    if not geometry:
        return 'CANDIDATE_BUDGET' if 'PARTIAL_IMAGE_CANDIDATE_BUDGET' in row.get('qualityFlags',[]) else 'NOT_RECALLED'
    if geometry.get('status')=='SOURCE_UNAVAILABLE':
        return 'SOURCE_UNAVAILABLE'
    return next((key for key in REASONS if key in geometry.get('qualityFlags',[])), 'UNRESOLVED')


def read_prefix(path, committed, expected, run_id, previous=None):
    if not 0 <= committed <= len(expected):
        raise ValueError('Invalid committed query count')
    if previous and previous['rows'] > committed:
        raise ValueError('Committed query prefix rolled back')
    digest=hashlib.sha256();rows=[];position=0
    if committed:
        with path.open('rb') as stream:
            for index in range(committed):
                line=stream.readline(2*1024*1024)
                if not line.endswith(b'\n') or not line.strip():
                    raise ValueError('Committed prediction row is missing or incomplete')
                digest.update(line);position+=len(line)
                if position>128*1024*1024:
                    raise ValueError('Prediction prefix exceeds analysis byte budget')
                if previous and index+1==previous['rows'] and digest.hexdigest()!=previous['sha256']:
                    raise ValueError('Previously committed prediction prefix changed')
                rows.append(json.loads(line))
    validate_saved(rows,expected,run_id)
    return rows,dict(rows=committed,sha256=digest.hexdigest(),bytes=position,runId=run_id)


def summarize(rows, expected):
    value=counts(rows)
    value.update(processed=len(rows),total=len(expected),pendingQueries=len(expected)-len(rows),
                 enhancedGainCount=sum(not r['baselineAccepted'] and r['enhancedAccepted'] for r in rows),
                 enhancedRegressionCount=sum(r['baselineAccepted'] and not r['enhancedAccepted'] for r in rows),
                 falsePositiveRate=None,realHardNegativeTruthCount=0,finalQueriesEvaluated=0,qualityAccepted=False)
    family_sizes=Counter(r['imageFamilyId'] for r in expected)
    completed=Counter(r['imageFamilyId'] for r in rows)
    value['completedFamilies']=sum(completed[key]==count for key,count in family_sizes.items())
    value['totalFamilies']=len(family_sizes)
    value['byTransformation']={}
    for kind in TRANSFORMS:
        selected=[r for r in rows if r['transformation']==kind]
        planned=sum(r['transformation']==kind for r in expected)
        if not planned:continue
        value['byTransformation'][kind]=dict(**counts(selected),planned=planned,pending=planned-len(selected))
    value['reasonCounts']=dict(sorted(Counter(key for r in rows if (key:=reason(r))).items()))
    value['errorQueries']=sum(value['reasonCounts'].values())
    return value


def error_rows(rows):
    for row in rows:
        key=reason(row)
        if key is None:continue
        geometry=row.get('geometry') or {}
        yield {**{name:row[name] for name in ('queryId','querySha256','imageFamilyId','transformation','sourceRank',
                                            'baselineAccepted','enhancedAccepted','scopeCorrect')},
               'reason':key,'matches':geometry.get('matches'),'inliers':geometry.get('inliers'),
               'querySpatialCoverage':geometry.get('querySpatialCoverage'),'sourceSpatialCoverage':geometry.get('sourceSpatialCoverage')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parent',type=Path,default=ROOT/'runtime/experiments/final-training-20261028/image-development-pipeline-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/experiments/final-training-20261028/image-error-analysis-v1')
    parser.add_argument('--watch',action='store_true');parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();parent=args.parent.resolve();output=args.output.resolve();boundary=(ROOT/'runtime/experiments').resolve()
    if not all(p.is_relative_to(boundary) for p in (parent,output)) or parent.is_relative_to(output) or output.is_relative_to(parent):
        raise ValueError('Use separate project experiment directories')
    output.mkdir(parents=True,exist_ok=True)
    with stage_lock(output/'run.lock'):
        try:
            parent_file=parent/'run.json';source=json.loads(parent_file.read_text(encoding='utf-8'))
            if source['schemaVersion']!='image-development-pipeline-v1' or source['split']!='development':
                raise ValueError('Only complete declared image development protocols are supported')
            data=ROOT/'runtime/datasets/campus-image-protocol-v1';verify_ready(data)
            if file_sha256(data/'READY')!=source['datasetReadySha256']:raise ValueError('Parent dataset identity changed')
            queries=[r for r in read_jsonl(data/'queries.jsonl') if r['split']=='development']
            if len(queries)!=1064 or source['queries']!=len(queries):raise ValueError('Full development query protocol required')
            run_id=digest_json(source)
            paths=[Path(__file__),ROOT/'app/training/evaluate_image_pipeline.py',ROOT/'app/training/corpus.py',
                   ROOT/'app/training/construct_correspondence.py',ROOT/'app/training/run_campus_stage.py',ROOT/'app/python/campus_shared/contracts.py']
            identity=dict(schemaVersion='image-error-analysis-v1',parentRunId=run_id,parentRunSha256=file_sha256(parent_file),
                datasetReadySha256=source['datasetReadySha256'],watch=args.watch,queries=len(queries),
                algorithms={str(path.relative_to(ROOT)):file_sha256(path) for path in paths},neuralInferencePerformed=False)
            run_path=output/'run.json'
            if run_path.exists():
                if not args.resume or json.loads(run_path.read_text(encoding='utf-8'))!=identity:raise ValueError('Explicit same-identity analysis resume required')
            elif any(p.name!='run.lock' for p in output.iterdir()):raise ValueError('Nonempty analysis output has no run identity')
            atomic_json(run_path,identity)
            previous=None
            if (output/'snapshot.json').exists():previous=json.loads((output/'snapshot.json').read_text(encoding='utf-8'))['predictionPrefix']
            started=time.monotonic();deadline=started+24*3600
            while True:
                if file_sha256(parent_file)!=identity['parentRunSha256']:raise ValueError('Parent run changed')
                for name,h in {**source['algorithms'],**identity['algorithms']}.items():
                    if file_sha256(ROOT/name)!=h:raise ValueError('Bound image/analysis code changed: '+name)
                state=json.loads((parent/'status.json').read_text(encoding='utf-8'))
                if state.get('runId')!=run_id or state['total']!=len(queries):raise ValueError('Parent status identity mismatch')
                rows,receipt=read_prefix(parent/'predictions.jsonl',state['processed'],queries,run_id,previous)
                value=summarize(rows,queries)
                complete=state['state']=='IMAGE_DEVELOPMENT_EVALUATION_COMPLETE' and len(rows)==len(queries)
                status='IMAGE_ERROR_ANALYSIS_COMPLETE' if complete else 'RUNNING_IMAGE_ERROR_ANALYSIS'
                if state['state']=='IMAGE_EVALUATION_STOPPED':status='PARENT_IMAGE_EVALUATION_STOPPED'
                elif time.time()-(parent/'status.json').stat().st_mtime>900:status='WAITING_IMAGE_EVALUATION_PROGRESS'
                if time.monotonic()>deadline and not complete:status='IMAGE_ERROR_ANALYSIS_TIMEOUT'
                if not args.watch and not complete:status='IMAGE_ERROR_ANALYSIS_SNAPSHOT'
                value.update(state=status,parentRunId=run_id,predictionPrefix=receipt,
                             elapsedSeconds=time.monotonic()-started,analysisComplete=complete)
                errors=list(error_rows(rows));temporary=output/'errors.tmp'
                temporary.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in errors),encoding='utf-8')
                temporary.replace(output/'errors.jsonl');value['errorsSha256']=file_sha256(output/'errors.jsonl')
                atomic_json(output/'snapshot.json',value);atomic_json(output/'status.json',value)
                previous=receipt
                if complete:
                    verify_ready(data);atomic_json(output/'summary.json',value)
                if complete or not args.watch or status in ('PARENT_IMAGE_EVALUATION_STOPPED','IMAGE_ERROR_ANALYSIS_TIMEOUT'):
                    print(json.dumps({'state':status,'processed':len(rows),'errorQueries':len(errors)}),flush=True)
                    return
                time.sleep(30)
        except Exception as error:
            previous=json.loads((output/'status.json').read_text(encoding='utf-8')) if (output/'status.json').exists() else {}
            atomic_json(output/'status.json',previous|dict(state='IMAGE_ERROR_ANALYSIS_STOPPED',error=type(error).__name__+': '+str(error)))
            raise


if __name__=='__main__':main()
