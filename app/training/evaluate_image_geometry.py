"""CPU development probe on known-source geometric controls; no final inference."""
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
from campus_detection.image_geometry import verify_images,POLICY


def summarize(rows):
    groups=defaultdict(list);kinds=defaultdict(list)
    for row in rows:groups[row['imageFamilyId']].append(row);kinds[row['transformation']].append(row)
    rng=np.random.default_rng(20261026);values=list(groups.values());samples=[]
    for _ in range(1000):
        chosen=[row for index in rng.integers(0,len(values),len(values)) for row in values[index]] if values else []
        samples.append(sum(row['acceptedCorrespondence'] for row in chosen)/max(1,len(chosen)))
    return {'state':'DEVELOPMENT_KNOWN_SOURCE_GEOMETRY_PROBE_COMPLETE','queries':len(rows),'automaticImageFamilies':len(groups),
            'knownSourceAcceptance':sum(row['acceptedCorrespondence'] for row in rows)/max(1,len(rows)),
            'correctScopeFraction':sum(row['scopeCorrect'] for row in rows)/max(1,len(rows)),
            'failedQueries':sum(bool(row.get('error')) for row in rows),
            'familyBootstrap95':np.quantile(samples,[.025,.975]).tolist(),
            'latencyMs':{'median':float(np.median([row['elapsedMs'] for row in rows])) if rows else None,'p95':float(np.quantile([row['elapsedMs'] for row in rows],.95)) if rows else None},
            'byTransformation':{kind:{'queries':len(items),'acceptedKnownSource':sum(item['acceptedCorrespondence'] for item in items),'correctScope':sum(item['scopeCorrect'] for item in items)} for kind,items in sorted(kinds.items())},
            'realHardNegativeTruthCount':0,'DinoRetrievalEvaluated':False,'finalQueriesEvaluated':0,'qualityAccepted':False,'productActivated':False,
            'scope':'Known-source pair verification only; not end-to-end source retrieval, natural negative accuracy or final acceptance. Failed/insufficient queries stay in denominators. Bootstrap resamples automatic image families.'}


def main():
    import cv2
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'runtime/datasets/campus-image-protocol-v1')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/experiments/final-training-20261026/image-geometry-development-v1');parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/experiments').resolve()):raise ValueError('Use project experiment output')
    hashes=verify_ready(args.data);references={row['imageId']:row for row in read_jsonl(args.data/'references.jsonl')}
    queries=[row for row in read_jsonl(args.data/'queries.jsonl') if row['split']=='development']
    if not queries or any(references[row['sourceImageId']]['split']!='development' for row in queries):raise ValueError('Invalid development source partition')
    source_code=ROOT/'app/python/campus_detection/image_geometry.py'
    config={'task':'DEVELOPMENT_KNOWN_SOURCE_GEOMETRY_PROBE','split':'development','datasetReadySha256':hashlib.sha256((args.data/'READY').read_bytes()).hexdigest(),
            'queriesManifestSha256':hashes['queries.jsonl'],'referenceManifestSha256':hashes['references.jsonl'],
            'geometryCodeSha256':hashlib.sha256(source_code.read_bytes()).hexdigest(),'policy':POLICY,'opencvVersion':cv2.__version__,'queryCount':len(queries),'neuralModelsLoaded':False}
    output.mkdir(parents=True,exist_ok=True);config_path=output/'run.json'
    if config_path.exists():
        if not args.resume or json.loads(config_path.read_text())!=config:raise ValueError('Existing probe requires explicit resume and unchanged identities')
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8');(output/'image-geometry-code.py').write_bytes(source_code.read_bytes())
    history=output/'predictions.jsonl';rows=list(read_jsonl(history)) if history.exists() else [];finished={row['queryId'] for row in rows}
    if len(finished)!=len(rows) or not finished.issubset({row['queryId'] for row in queries}):raise ValueError('Invalid saved prediction identities')
    cv2.setNumThreads(2)
    with history.open('a',encoding='utf-8') as stream:
        for query in queries:
            if query['queryId'] in finished:continue
            source=references[query['sourceImageId']];started=time.perf_counter()
            try:
                result=verify_images((args.data/query['path']).read_bytes(),(args.data/source['path']).read_bytes());error=None
            except Exception as failure:
                result={'acceptedCorrespondence':False,'scope':'UNRESOLVED','status':'FAILED','qualityFlags':['PROBE_FAILED']};error=type(failure).__name__+': '+str(failure)
            row={'queryId':query['queryId'],'sourceImageId':query['sourceImageId'],'imageFamilyId':query['imageFamilyId'],'transformation':query['transformation'],
                 'acceptedCorrespondence':bool(result['acceptedCorrespondence']),'scopeCorrect':bool(result['acceptedCorrespondence'] and result['scope']==query['groundTruthScope']),
                 'elapsedMs':(time.perf_counter()-started)*1000,'error':error,'geometry':result}
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();rows.append(row)
            (output/'status.json').write_text(json.dumps({'state':'RUNNING_DEVELOPMENT_GEOMETRY_PROBE','completedQueries':len(rows),'totalQueries':len(queries),'finalQueriesEvaluated':0}),encoding='utf-8')
    result=summarize(rows);(output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8');(output/'status.json').write_text(json.dumps({'state':result['state'],'completedQueries':len(rows),'finalQueriesEvaluated':0,'qualityAccepted':False}),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
