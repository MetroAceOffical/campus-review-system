"""Score frozen real predictions; incomplete protocols cannot become final grades.

This script never runs a model or manufactures predictions. Prediction export
and product inference remain separate steps with their own frozen identities.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from construct_correspondence import verify_ready
from corpus import read_jsonl
from text_evaluation import score_predictions

ROOT=Path(__file__).resolve().parents[2]
CONTROLS={'EXACT_COPY_CONTROL','SENTENCE_REORDER_CONTROL','NATURAL_NORMALIZED_EXACT_CONTENT'}
VARIANTS={'frozen-v2','untrained-dense','trained-dense-unadapted-reranker','full-v3','semantic-disabled'}


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def split_digest(rows):
    return hashlib.sha256(json.dumps(sorted(rows,key=lambda r:r['queryId']),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_evaluation_scale(split,count,diagnostic_controls=False):
    if split not in {'dev','final'} or count<1 or not diagnostic_controls and count!={'dev':400,'final':1200}[split]:raise ValueError('Formal evaluation requires 400 dev or 1200 final queries; do not relabel tiny controls')


def select_protocol_queries(manifest,queries,split,diagnostic_controls=False):
    if split not in {'dev','final'}:raise ValueError('Only dev/final evaluation is supported; calibration is not a test split')
    selected=[row for row in queries if row['split']==split]
    if diagnostic_controls:
        selected=[row for row in selected if row.get('transformationKind') in CONTROLS]
        if not selected:raise ValueError('No constructed diagnostic controls')
        return selected
    counts=manifest['splitCounts'][split];targets=manifest['targetsBySplit'][split]
    if counts['pending'] or counts['constructed']!=sum(targets.values()) or Counter(row['category'] for row in selected)!=Counter(targets):raise ValueError('Requested protocol split is incomplete; construction plans/READY are not a complete evaluation set')
    if any(row.get('constructionStatus','CONSTRUCTED')!='CONSTRUCTED' or row.get('truthScope')=='unknown_negative_scope' for row in selected):raise ValueError('Pending construction/truth cannot enter formal evaluation')
    return selected


def validate_development_evidence(run,summary,dev_queries_sha256,reference_sha256,method_config_id,expected_queries):
    if run.get('split')!='dev' or run.get('diagnosticControls') is not False or summary.get('diagnosticControls') is not False or summary.get('evaluationScope')!='FORMAL_PROTOCOL':raise ValueError('Final requires full development evidence, not diagnostic controls')
    if run.get('splitQueriesSha256')!=dev_queries_sha256 or run.get('referenceManifestSha256')!=reference_sha256 or run.get('methodConfigId')!=method_config_id:raise ValueError('Development queries/reference/method differ from frozen final working point')
    if summary.get('queries')!=expected_queries or summary.get('missingPredictions')!=0:raise ValueError('Development prediction export is incomplete')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--protocol',type=Path,default=ROOT/'runtime/datasets/text-evaluation-protocol-v1')
    parser.add_argument('--predictions',type=Path,required=True,help='Frozen folder containing run.json, predictions.jsonl and READY')
    parser.add_argument('--method-config-id',required=True);parser.add_argument('--split',choices=['dev','final'],default='dev')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--development-run',type=Path)
    parser.add_argument('--diagnostic-controls',action='store_true');args=parser.parse_args()
    if args.split=='final' and args.diagnostic_controls:raise ValueError('Do not inspect final controls during development; final scoring requires the full frozen protocol')
    protocol_hashes=verify_ready(args.protocol);manifest=json.loads((args.protocol/'manifest.json').read_text(encoding='utf-8'))
    all_queries=list(read_jsonl(args.protocol/'queries.jsonl'))
    queries=select_protocol_queries(manifest,all_queries,args.split,args.diagnostic_controls)
    validate_evaluation_scale(args.split,len(queries),args.diagnostic_controls)
    prediction_hashes=verify_ready(args.predictions);prediction_run=json.loads((args.predictions/'run.json').read_text(encoding='utf-8'))
    protocol_sha=sha(args.protocol/'READY');queries_sha=split_digest(queries);reference_sha=protocol_hashes['references.jsonl']
    expected={'protocolReadySha256':protocol_sha,'splitQueriesSha256':queries_sha,'referenceManifestSha256':reference_sha,
              'methodConfigId':args.method_config_id,'split':args.split,'diagnosticControls':args.diagnostic_controls}
    if any(prediction_run.get(key)!=value for key,value in expected.items()):raise ValueError('Prediction export protocol/split/method identities differ')
    if prediction_run.get('variant') not in VARIANTS:raise ValueError('Declare the actual ablation variant')
    if prediction_run['variant']=='full-v3' and not all(prediction_run.get(key) is True for key in ['campusRetrieverTrainingComplete','correspondenceTrainingComplete','formalCalibrationFrozen']):raise ValueError('Untrained or uncalibrated models cannot be called full v3')
    development_sha=None
    if args.split=='final':
        if args.development_run is None or prediction_run.get('operatingPointFrozen') is not True:raise ValueError('Final requires completed development evidence and a frozen working point')
        verify_ready(args.development_run)
        dev_run=json.loads((args.development_run/'run.json').read_text(encoding='utf-8'))
        dev_summary=json.loads((args.development_run/'summary.json').read_text(encoding='utf-8'))
        development_queries=select_protocol_queries(manifest,all_queries,'dev',False)
        validate_development_evidence(dev_run,dev_summary,split_digest(development_queries),reference_sha,args.method_config_id,len(development_queries))
        development_sha=sha(args.development_run/'READY')
        if prediction_run.get('developmentEvidenceSha256')!=development_sha:raise ValueError('Final predictions were not bound to this development evidence')
    references=list(read_jsonl(args.protocol/'references.jsonl'))
    predictions=list(read_jsonl(args.predictions/'predictions.jsonl'))
    result=score_predictions(queries,predictions,references,args.method_config_id,reference_sha256=reference_sha)
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/experiments').resolve()) or output.exists():raise ValueError('Use a new project evaluation output')
    run={**expected,'variant':prediction_run['variant'],'predictionReadySha256':sha(args.predictions/'READY'),
         'predictionFiles':prediction_hashes,'developmentEvidenceSha256':development_sha,
         'evaluatorCodeSha256':sha(Path(__file__)),'metricsCodeSha256':sha(ROOT/'app/training/text_evaluation.py')}
    rows=result.pop('queryResults')
    summary={**result,'state':'DIAGNOSTIC_TEXT_CONTROLS_SCORED' if args.diagnostic_controls else 'FORMAL_TEXT_PREDICTIONS_SCORED',
             'evaluationScope':'DIAGNOSTIC_CONTROLS' if args.diagnostic_controls else 'FORMAL_PROTOCOL',
             'diagnosticControls':args.diagnostic_controls,'split':args.split,
             'finalProtocolExecuted':args.split=='final' and not args.diagnostic_controls and result['missingPredictions']==0,
             'modelInferencePerformedByThisScript':False,'productActivated':False}
    output.mkdir(parents=True,exist_ok=False)
    (output/'run.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (output/'query-results.jsonl').open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    (output/'READY').write_text(json.dumps({name:sha(output/name) for name in ['run.json','summary.json','query-results.jsonl']},indent=2),encoding='utf-8')
    print(json.dumps({key:summary[key] for key in ['state','queries','missingPredictions','failedQueries','invalidEvidence','qualityAccepted','finalProtocolExecuted']}),flush=True)


if __name__=='__main__':main()
