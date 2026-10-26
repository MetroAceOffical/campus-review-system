"""Small frozen rewrite comparison using existing models; never train or tune on holdout."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/python'))
from campus_detection.models import load_models
from campus_detection.text import detect_text


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(split, freeze=False):
    import joblib
    folder = ROOT / 'runtime/experiments/rewrite-20261024'
    protocol = read(folder / 'protocol.json')
    for name, checksum in protocol['splits'].items():
        if sha(folder / (name + '.json')) != checksum:
            raise ValueError('Frozen sample file changed: ' + name)
    models = load_models()
    lock_path = folder / 'candidate-lock.json'
    identity = {'textConfig':models['textConfig'], 'sampleHashes':protocol['splits'],
                'libraryManifestSha256':sha(ROOT / 'runtime/indexes/7/manifest.json')}
    if split == 'holdout' and (not lock_path.is_file() or read(lock_path) != identity):
        raise ValueError('Freeze the candidate before holdout; do not retune on holdout output')
    destination = folder / (split + '-comparison.json')
    if destination.exists():
        raise ValueError('Comparison already exists; preserve it instead of overwriting results')
    library = read(ROOT / 'runtime/indexes/7/manifest.json')
    library['_textIndex'] = joblib.load(ROOT / 'runtime/indexes/7/text-index.joblib')
    results = []
    for sample in read(folder / (split + '.json')):
        outcomes = {}
        for method, config in [('baseline',models['legacyTextConfig']), ('sentence',models['textConfig'])]:
            request = {'taskId':sample['id'], 'attemptId':sample['id'] + '-' + method, 'scene':'PRECHECK',
                'inputSnapshotKey':sample['id'], 'inputSha256':hashlib.sha256(sample['text'].encode()).hexdigest(),
                'libraryGenerationId':'7', 'configId':config['configId'], 'text':sample['text'], 'excludeManuscriptId':None}
            started = time.perf_counter()
            report = detect_text(request, library, models)
            candidates = report['evidence']
            def alerted(item):
                return item['acceptedCandidate'] or item.get('semanticSummary', {}).get('suspectedReuse', False)
            target = [e for e in candidates if e['sourceUrl'] == sample['sourceUrl']]
            outcomes[method] = {'expectedSourceRecalled':bool(target),
                'expectedSourceAlert':any(alerted(e) for e in target),
                'anyAlert':any(alerted(e) for e in candidates),
                'wrongSourceAlerts':[e['sourceWorkId'] for e in candidates if alerted(e) and e['sourceUrl'] != sample['sourceUrl']],
                'literalExpected':any(e['acceptedCandidate'] for e in target),
                'semanticExpected':any(e.get('semanticSummary', {}).get('suspectedReuse') for e in target),
                'seconds':time.perf_counter() - started, 'report':report}
        row = {'id':sample['id'], 'kind':sample['kind'], 'positive':sample['positive'], 'outcomes':outcomes}
        results.append(row)
        print(json.dumps({'id':sample['id'], 'positive':sample['positive'], **{
            method:{k:v for k,v in value.items() if k != 'report'} for method,value in outcomes.items()}}, ensure_ascii=False), flush=True)
    counts = {}
    for method in ('baseline','sentence'):
        counts[method] = {}
        for kind in sorted({s['kind'] for s in results}):
            group = [r for r in results if r['kind'] == kind]
            counts[method][kind] = {'n':len(group), 'expectedSourceAlerts':sum(r['outcomes'][method]['expectedSourceAlert'] for r in group),
                'anyAlerts':sum(r['outcomes'][method]['anyAlert'] for r in group),
                'wrongSourceAlertCases':sum(bool(r['outcomes'][method]['wrongSourceAlerts']) for r in group)}
    result = {'split':split, 'identity':identity, 'counts':counts, 'results':results,
        'scope':'Four original articles, assistant-authored synthetic cases; not campus-wide accuracy or independent human gold.'}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if freeze:
        if split != 'development' or lock_path.exists():
            raise ValueError('Only a new development candidate can be frozen')
        lock_path.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['development','holdout'], required=True)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    evaluate(args.split, args.freeze)
