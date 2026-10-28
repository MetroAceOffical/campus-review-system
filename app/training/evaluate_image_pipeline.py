"""Frozen, resumable CPU evaluation of the complete image development partition."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/python'))
from campus_shared.contracts import controlled_file, digest_json, file_sha256

COUNTERS = ('dinoTop10Retrieved', 'dinoTop20Retrieved', 'baselineAccepted',
            'top20Accepted', 'enhancedAccepted', 'scopeCorrect')


def counts(rows):
    return {'queries': len(rows), 'failedQueries': sum(bool(r.get('error')) for r in rows),
            'partialQueries': sum(r.get('coverageStatus') == 'PARTIAL' for r in rows),
            'unknownAcceptedSources': sum(r['unknownAcceptedSources'] for r in rows),
            **{key: sum(bool(r.get(key)) if key not in ('dinoTop10Retrieved', 'dinoTop20Retrieved')
                        else r['sourceRank'] is not None and r['sourceRank'] <= (10 if key == 'dinoTop10Retrieved' else 20)
                        for r in rows) for key in COUNTERS}}


def summarize(rows):
    from collections import defaultdict
    result = counts(rows)
    families, kinds = defaultdict(list), defaultdict(list)
    for row in rows:
        families[row['imageFamilyId']].append(row)
        kinds[row['transformation']].append(row)
    result.update(automaticImageFamilies=len(families),
                  rates={key: result[key]/len(rows) if rows else None for key in COUNTERS},
                  byTransformation={key: counts(items) for key, items in sorted(kinds.items())},
                  realHardNegativeTruthCount=0, falsePositiveRate=None,
                  finalQueriesEvaluated=0, qualityAccepted=False, productActivated=False,
                  truthBasis='CONTROLLED_TRANSFORMATIONS_AUTOMATIC_IMAGE_FAMILIES',
                  latencyMs={'median': float(np.median([r['elapsedMs'] for r in rows])) if rows else None,
                             'p95': float(np.quantile([r['elapsedMs'] for r in rows], .95)) if rows else None})
    values = list(families.values())
    rng = np.random.default_rng(20261026)
    # Resample families, never treat seven related transformations as seven originals.
    samples = {key: [] for key in COUNTERS}
    for _ in range(1000 if values else 0):
        selected = [r for i in rng.integers(0, len(values), len(values)) for r in values[i]]
        score = counts(selected)
        for key in COUNTERS:
            samples[key].append(score[key]/len(selected))
    result['familyBootstrap95'] = {key: np.quantile(items, [.025, .975]).tolist() if items else None
                                   for key, items in samples.items()}
    return result


def validate_saved(rows, queries, run_id):
    if len(rows) > len(queries):
        raise ValueError('Saved predictions exceed frozen query set')
    for row, query in zip(rows, queries):
        if (row.get('queryId'), row.get('querySha256'), row.get('runId')) != (query['queryId'], query['sha256'], run_id):
            raise ValueError('Saved prediction order or identity changed')


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


@contextmanager
def output_lock(output):
    import msvcrt
    with (output / 'run.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def verify_code(hashes):
    for name, expected in hashes.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError('Evaluation code changed: ' + name)


def evaluate(query, data, library, models, baseline, config, run_id):
    from campus_detection.image import encode_images, detect_image
    started = time.perf_counter()
    row = {key: query[key] for key in ('queryId', 'sourceImageId', 'imageFamilyId', 'transformation')}
    row.update(querySha256=query['sha256'], runId=run_id, sourceRank=None,
               baselineAccepted=False, top20Accepted=False, enhancedAccepted=False,
               scopeCorrect=False, unknownAcceptedSources=0, error=None)
    try:
        path = controlled_file(data / query['path'], query['sha256'], [data])
        vector = encode_images([path], models)[0]
        scores = np.asarray([r['vector'] for r in library['images']], dtype=np.float32) @ vector
        order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), str(library['images'][i]['sourceRevisionId']), str(library['images'][i]['fileId'])))
        source = next(i for i, r in enumerate(library['images']) if r['fileId'] == query['sourceImageId'])
        rank = order.index(source) + 1
        row.update(sourceRank=rank, sourceScore=float(scores[source]),
                   baselineAccepted=bool(rank <= 10 and scores[source] >= baseline['threshold']),
                   top20Accepted=bool(rank <= 20 and scores[source] >= baseline['threshold']))
        request = dict(taskId=query['queryId'], attemptId=query['queryId'], scene='EXTERNAL',
                       inputSnapshotKey=query['queryId'], inputSha256=query['sha256'],
                       libraryGenerationId=library['generationId'], configId=config['configId'],
                       path=str(path), fileId=query['queryId'], fileSha256=query['sha256'])
        result = detect_image(request, library, models)
        correct = next((r for r in result['evidence'] if r['sourceFileId'] == query['sourceImageId']), None)
        accepted = bool(correct and correct['acceptedCandidate'])
        row.update(enhancedAccepted=accepted,
                   scopeCorrect=bool(accepted and correct['geometry']['scope'] == query['groundTruthScope']),
                   geometry=correct['geometry'] if correct else None,
                   candidateRoutes=correct['candidateRoutes'] if correct else [],
                   unknownAcceptedSources=sum(bool(r['acceptedCandidate']) for r in result['evidence'] if r['sourceFileId'] != query['sourceImageId']),
                   coverageStatus=result['coverageStatus'], qualityFlags=result['qualityFlags'],
                   verifiedCandidates=result['verifiedCandidates'], enhancedElapsedMs=result['elapsedMs'])
    except Exception as failure:
        row['error'] = type(failure).__name__ + ': ' + str(failure)
    row['elapsedMs'] = (time.perf_counter() - started) * 1000
    return row


def run(args):
    import cv2
    import PIL
    import torch
    import transformers
    from campus_detection.models import configurations, load_image_models
    from campus_detection.image import encode_images
    from campus_detection.image_enhanced import configuration, attach_sources
    torch.set_num_threads(2); torch.set_num_interop_threads(2); cv2.setNumThreads(2)
    data, output = args.data.resolve(), args.output.resolve()
    if not data.is_relative_to((ROOT / 'runtime/datasets').resolve()):
        raise ValueError('Use project dataset root')
    hashes = verify_ready(data)
    references = [r for r in read_jsonl(data / 'references.jsonl') if r['split'] == 'development']
    queries = [r for r in read_jsonl(data / 'queries.jsonl') if r['split'] == 'development']
    source_ids = {r['imageId'] for r in references}
    # This CLI intentionally has no --limit or final-split option.
    if len(references) != 152 or len(queries) != 1064 or len(source_ids) != len(references):
        raise ValueError('Complete frozen development partition required')
    if any(q['sourceImageId'] not in source_ids or q['target'] != 1 for q in queries):
        raise ValueError('Development query/source partition mismatch')
    _, baseline = configurations()
    config = configuration(baseline)
    files = ['app/training/evaluate_image_pipeline.py', 'app/training/corpus.py',
             'app/training/construct_correspondence.py', 'app/python/campus_detection/models.py',
             'app/python/campus_detection/image.py', 'app/python/campus_detection/image_enhanced.py',
             'app/python/campus_detection/image_geometry.py', 'app/python/campus_shared/contracts.py']
    identity = dict(schemaVersion='image-development-pipeline-v1', split='development', device='cpu',
                    threads=2, references=len(references), queries=len(queries),
                    datasetReadySha256=file_sha256(data / 'READY'), datasetHashes=hashes,
                    algorithms={name: file_sha256(ROOT / name) for name in files},
                    baseline=baseline, enhanced=config,
                    software=dict(torch=torch.__version__, transformers=transformers.__version__,
                                  numpy=np.__version__, opencv=cv2.__version__, Pillow=PIL.__version__),
                    realHardNegativeTruthCount=0, finalQueriesEvaluated=0)
    run_id = digest_json(identity)
    run_path = output / 'run.json'
    if run_path.exists():
        if not args.resume or json.loads(run_path.read_text(encoding='utf-8')) != identity:
            raise ValueError('Existing run requires explicit resume and unchanged identities')
    elif any(output.iterdir()):
        if set(p.name for p in output.iterdir()) != {'run.lock'}:
            raise ValueError('Nonempty output has no immutable run identity')
    atomic_json(run_path, identity)
    history = output / 'predictions.jsonl'
    rows = list(read_jsonl(history)) if history.exists() else []
    validate_saved(rows, queries, run_id)
    previous_elapsed = json.loads((output / 'status.json').read_text(encoding='utf-8')).get('elapsedSeconds', 0) if (output / 'status.json').exists() else 0
    started = time.perf_counter()

    def status(state):
        elapsed = previous_elapsed + time.perf_counter() - started
        value = dict(state=state, processed=len(rows), total=len(queries), runId=run_id,
                     elapsedSeconds=elapsed, **counts(rows), finalQueriesEvaluated=0,
                     realHardNegativeTruthCount=0, qualityAccepted=False, productActivated=False)
        if rows:
            value['estimatedRemainingSeconds'] = (len(queries)-len(rows))*elapsed/len(rows)
        atomic_json(output / 'status.json', value)
    status('LOADING_IMAGE_EVALUATION')
    models = load_image_models(device='cpu', enhanced=True)
    if models['imageConfig'] != config:
        raise ValueError('Loaded model configuration changed')
    entries, sources = [], []
    for source in references:
        verify_code(identity['algorithms'])
        path = controlled_file(data / source['path'], source['sha256'], [data])
        common = dict(fileId=source['imageId'], sourceRevisionId=source['imageId'],
                      sourceWorkId=source['sourceId'], title=source['imageId'], fileSha256=source['sha256'])
        entries.append(dict(**common, featureSpaceId=baseline['featureSpaceId'], vector=encode_images([path], models)[0].tolist()))
        sources.append(dict(**common, path=str(path)))
    manifest = {'images': sources}
    atomic_json(output / 'input-manifest.json', manifest)
    library = dict(generationId=run_id, images=entries, inputManifestHash=digest_json(manifest))
    attach_sources(library, output)
    atomic_json(output / 'library.json', library | {'_imageSources': None})
    status('RUNNING_IMAGE_DEVELOPMENT_EVALUATION')
    with history.open('a', encoding='utf-8') as stream:
        for query in queries[len(rows):]:
            verify_code(identity['algorithms'])
            row = evaluate(query, data, library, models, baseline, config, run_id)
            verify_code(identity['algorithms'])
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush(); os.fsync(stream.fileno())
            rows.append(row)
            status('RUNNING_IMAGE_DEVELOPMENT_EVALUATION')
    verify_ready(data); verify_code(identity['algorithms'])
    summary = summarize(rows)
    summary.update(runId=run_id, state='IMAGE_DEVELOPMENT_EVALUATION_COMPLETE')
    atomic_json(output / 'summary.json', summary)
    status(summary['state'])
    print(json.dumps({'state': summary['state'], 'queries': len(rows), 'runId': run_id}), flush=True)


def main():
    os.environ.update(CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT / 'runtime/datasets/campus-image-protocol-v1')
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/experiments/final-training-20261028/image-development-pipeline-v1')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'runtime/experiments').resolve()):
        raise ValueError('Use project experiment output')
    output.mkdir(parents=True, exist_ok=True)
    with output_lock(output):
        try:
            run(args)
        except Exception as error:
            failure = {'state': 'IMAGE_EVALUATION_STOPPED', 'error': type(error).__name__ + ': ' + str(error)}
            atomic_json(output / 'failure.json', failure)
            previous = json.loads((output / 'status.json').read_text(encoding='utf-8')) if (output / 'status.json').exists() else {}
            atomic_json(output / 'status.json', previous | failure)
            raise


if __name__ == '__main__':
    main()
