"""Paired CPU mobile960/adaptive OCR evaluation with separate known-text and real scopes."""
import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_ocr.fallback import recognize_adaptive,fallback_configuration


def normalize(text):return ''.join(text.split())


def distance(left,right):
    if len(left)<len(right):left,right=right,left
    previous=list(range(len(right)+1))
    for i,character in enumerate(left,1):
        current=[i]
        for j,other in enumerate(right,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(character!=other)))
        previous=current
    return previous[-1]


def score_sample(sample,prediction):
    if not sample['cerEligible']:
        return {'CER':None,'editDistance':None,'truthCharacters':None,'truthLines':None,'coveredTruthLines':None,'scope':'No independent real transcription; excluded from CER/region accuracy.'}
    import cv2
    truth=normalize(sample['groundTruthText']);text=normalize(prediction['combinedText'])
    if not truth:raise ValueError('Known-text reference cannot be empty')
    edits=distance(truth,text);covered=0
    for line in sample['groundTruthLines']:
        polygon=cv2.convexHull(np.asarray(line['polygon'],dtype=np.float32));area=float(cv2.contourArea(polygon));best=0.
        for candidate in prediction['recognitionLines']:
            other=cv2.convexHull(np.asarray(candidate['polygon'],dtype=np.float32));overlap=float(cv2.intersectConvexConvex(polygon,other)[0])
            best=max(best,overlap/max(1e-9,area))
        covered+=best>=.5
    return {'CER':edits/len(truth),'editDistance':edits,'truthCharacters':len(truth),'truthLines':len(sample['groundTruthLines']),
            'coveredTruthLines':covered,'scope':'Known rendered strings; region metric is >=50% recognized-polygon coverage of each rendered line box, not real localization accuracy.'}


def summarize(rows):
    known=[row for row in rows if row['cerEligible']];real=[row for row in rows if not row['cerEligible']]
    branches={}
    for name in ['baseline','adaptive']:
        metrics=[row[name+'Metrics'] for row in known];characters=sum(row['truthCharacters'] for row in metrics)
        times=[row[name+'ElapsedMs'] for row in rows]
        branches[name]={'knownQueries':len(known),'truthCharacters':characters,'microCER':sum(row['editDistance'] for row in metrics)/characters if characters else None,
                        'macroCER':float(np.mean([row['CER'] for row in metrics])) if metrics else None,
                        'coveredTruthLines':sum(row['coveredTruthLines'] for row in metrics),'truthLines':sum(row['truthLines'] for row in metrics),
                        'latencyMs':{'median':float(np.median(times)) if times else None,'p95':float(np.quantile(times,.95)) if times else None}}
    families=defaultdict(list)
    for row in known:families[row['sourceFamilyId']].append(row)
    values=list(families.values());rng=np.random.default_rng(20261026);differences=[]
    for _ in range(1000):
        chosen=[row for index in rng.integers(0,len(values),len(values)) for row in values[index]] if values else []
        characters=sum(row['baselineMetrics']['truthCharacters'] for row in chosen)
        if characters:differences.append(sum(row['adaptiveMetrics']['editDistance']-row['baselineMetrics']['editDistance'] for row in chosen)/characters)
    return {'state':'OCR_RECOVERY_EVALUATION_COMPLETE','queries':len(rows),'knownTextQueries':len(known),'syntheticOriginalFamilies':len(families),
            'realRuntimeQueries':len(real),'realTranscriptionsAvailable':0,'realCER':None,'failedQueries':sum(bool(row['error']) for row in rows),
            'realRuntimeCompleted':sum(not row['error'] for row in real),'realEmptyAdaptive':sum(not row['adaptive']['combinedText'].strip() for row in real),
            'fallbackUsedQueries':sum(row['adaptive'].get('fallbackUsed',False) for row in rows),
            'partialProcessingQueries':sum(row['adaptive'].get('processingCoverageStatus')=='PARTIAL' for row in rows),
            'results':branches,'adaptiveMinusBaselineCERFamilyBootstrap95':np.quantile(differences,[.025,.975]).tolist() if differences else None,
            'qualityAccepted':False,'productActivated':False,
            'scope':'Known synthetic text CER and separate untranscribed real runtime coverage. Failures/empty outputs stay in known-text denominators. Does not measure reuse detection, real CER or production SLA.'}


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    from campus_ocr.recognizer import configuration,load_pipeline
    import psutil
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'runtime/datasets/campus-ocr-controls-v1')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--split',choices=['development','final'],default='development')
    parser.add_argument('--include-real-runtime',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--development-run',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/experiments').resolve()):raise ValueError('Use project experiment output')
    hashes=verify_ready(args.data);samples=[row for row in read_jsonl(args.data/'samples.jsonl') if row['split']==args.split or args.include_real_runtime and row['split']=='runtime_only']
    baseline_config=configuration();adaptive_config=fallback_configuration(baseline_config)
    if args.split=='final':
        if not args.development_run:raise ValueError('Final OCR evaluation requires a completed development run with the same frozen policy')
        previous=json.loads((args.development_run/'run.json').read_text());summary=json.loads((args.development_run/'summary.json').read_text())
        if previous['split']!='development' or previous['adaptiveConfiguration']!=adaptive_config or previous['datasetReadySha256']!=sha(args.data/'READY') or summary['state']!='OCR_RECOVERY_EVALUATION_COMPLETE':raise ValueError('Development policy/data not frozen or evaluation incomplete')
    config={'task':'PAIRED_CPU_OCR_RECOVERY','split':args.split,'includeRealRuntime':args.include_real_runtime,'sampleCount':len(samples),
            'datasetReadySha256':sha(args.data/'READY'),'samplesManifestSha256':hashes['samples.jsonl'],'evaluatorCodeSha256':sha(Path(__file__)),
            'baselineConfiguration':baseline_config,'adaptiveConfiguration':adaptive_config,'neuralGpuModelsLoaded':False}
    output.mkdir(parents=True,exist_ok=True);config_path=output/'run.json'
    if config_path.exists() and (not args.resume or json.loads(config_path.read_text())!=config):raise ValueError('Existing OCR run needs explicit resume with unchanged identities')
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8');(output/'evaluator-code.py').write_bytes(Path(__file__).read_bytes())
    (output/'fallback-code.py').write_bytes((ROOT/'app/python/campus_ocr/fallback.py').read_bytes())
    history=output/'predictions.jsonl';rows=list(read_jsonl(history)) if history.exists() else [];completed={row['sampleId'] for row in rows}
    if len(completed)!=len(rows) or not completed.issubset({row['sampleId'] for row in samples}):raise ValueError('Invalid OCR prediction identities')
    tick=time.perf_counter();pipeline,actual=load_pipeline();load_seconds=time.perf_counter()-tick
    if actual!=baseline_config:raise ValueError('OCR loaded configuration changed')
    with history.open('a',encoding='utf-8') as stream:
        for sample in samples:
            if sample['sampleId'] in completed:continue
            started=time.perf_counter()
            try:
                result=recognize_adaptive(pipeline,args.data/sample['path'],baseline_config);error=None
            except Exception as failure:
                empty={'combinedText':'','recognitionLines':[],'fallbackUsed':False,'processingCoverageStatus':'PARTIAL','qualityFlags':['OCR_FAILED'],'noReuseClaim':False}
                result={'baseline':empty,'adaptive':empty,'steps':[],'baselineElapsedMs':(time.perf_counter()-started)*1000};result['adaptive']={**empty,'elapsedMs':result['baselineElapsedMs']}
                error=type(failure).__name__+': '+str(failure)
            row={'sampleId':sample['sampleId'],'sourceFamilyId':sample['sourceFamilyId'],'split':sample['split'],'realOrSynthetic':sample['realOrSynthetic'],
                 'cerEligible':sample['cerEligible'],'transformation':sample.get('transformation'),'language':sample.get('language'),
                 'baseline':result['baseline'],'adaptive':result['adaptive'],'steps':result['steps'],'baselineElapsedMs':result['baselineElapsedMs'],
                 'adaptiveElapsedMs':result['adaptive']['elapsedMs'],'baselineMetrics':score_sample(sample,result['baseline']),
                 'adaptiveMetrics':score_sample(sample,result['adaptive']),'error':error}
            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();rows.append(row)
            (output/'status.json').write_text(json.dumps({'state':'RUNNING_CPU_OCR_RECOVERY','completedQueries':len(rows),'totalQueries':len(samples),'split':args.split,
                    'modelLoadSeconds':load_seconds,'hostRssBytes':psutil.Process().memory_info().rss,'productActivated':False}),encoding='utf-8')
    summary=summarize(rows);(output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'status.json').write_text(json.dumps({'state':summary['state'],'completedQueries':len(rows),'split':args.split,'qualityAccepted':False,'productActivated':False}),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
