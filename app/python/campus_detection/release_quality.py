"""CPU-only publication gate over immutable real final predictions.

This verifies existing predictions; it never trains, infers, or writes evidence.
The caller separately verifies model/index artifacts and the calibration package.
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from campus_detection.retrieval import _digest, _sha

ROOT=Path(__file__).resolve().parents[3]
TRAINING=ROOT/'app/training'
if str(TRAINING) not in sys.path:sys.path.insert(0,str(TRAINING))
from corpus import read_jsonl
from evaluate_final import select_protocol_queries,split_digest,validate_development_evidence
from text_evaluation import score_predictions

FINAL_TARGETS={'whole_synonym':250,'whole_reordered':250,'local':200,'multi_source':100,
               'copy_control':100,'same_event_negative':200,'template_normal':100}
SUMMARY_FIELDS=('queries','predictionsProvided','missingPredictions','failedQueries','partialQueries',
    'unscoredNormalQueries','invalidEvidence','knownWrongSourceAcceptances','unknownExtraSourceAcceptances',
    'rates','byCategory','methodConfigId','referenceManifestSha256')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _path(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'runtime'):raise ValueError('Quality evidence must stay inside project runtime')
    return path


def _folder(folder,required,verified):
    folder=_path(folder);manifest=_read(folder/'READY')
    if not isinstance(manifest,dict) or not set(required)<=manifest.keys():raise ValueError('Quality evidence READY is incomplete')
    for name,expected in manifest.items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected) or _sha(path)!=expected:
            raise ValueError('Frozen quality evidence changed: '+name)
        verified[path.relative_to(ROOT).as_posix()]=expected
    verified[(folder/'READY').relative_to(ROOT).as_posix()]=_sha(folder/'READY')
    return folder,manifest


def _implementation(run,verified):
    declared=run.get('implementation')
    if not isinstance(declared,dict) or not declared:raise ValueError('Prediction implementation identities are missing')
    for name,expected in declared.items():
        path=(ROOT/name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(ROOT/'app') or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected) or _sha(path)!=expected:
            raise ValueError('Prediction implementation changed: '+name)
        verified[path.relative_to(ROOT).as_posix()]=expected
    return declared


def _score(evaluation,predictions,variant,protocol_sha,queries,reference_sha,references,verified):
    evaluation,_=_folder(evaluation,{'run.json','summary.json','query-results.jsonl'},verified)
    predictions,prediction_files=_folder(predictions,{'run.json','predictions.jsonl'},verified)
    run=_read(evaluation/'run.json');prediction_run=_read(predictions/'run.json');summary=_read(evaluation/'summary.json')
    method=prediction_run.get('methodConfigId')
    if not isinstance(method,str) or not method:raise ValueError('Final method identity is missing')
    expected={'protocolReadySha256':protocol_sha,'splitQueriesSha256':split_digest(queries),
        'referenceManifestSha256':reference_sha,'methodConfigId':method,'split':'final','diagnosticControls':False,'variant':variant}
    if any(run.get(key)!=value or prediction_run.get(key)!=value for key,value in expected.items()):
        raise ValueError('Final protocol/query/reference/method identities differ')
    if run.get('predictionReadySha256')!=_sha(predictions/'READY') or run.get('predictionFiles')!=prediction_files:
        raise ValueError('Final evaluation belongs to another prediction export')
    _implementation(prediction_run,verified)
    development=run.get('developmentEvidenceSha256')
    if not isinstance(development,str) or not re.fullmatch('[0-9a-f]{64}',development) or prediction_run.get('developmentEvidenceSha256')!=development or prediction_run.get('operatingPointFrozen') is not True:
        raise ValueError('Final predictions lack matching frozen development evidence')
    for key,name in [('evaluatorCodeSha256','evaluate_final.py'),('metricsCodeSha256','text_evaluation.py')]:
        path=TRAINING/name;actual=_sha(path)
        if run.get(key)!=actual:raise ValueError('Final scoring code changed; rescore the frozen predictions')
        verified[path.relative_to(ROOT).as_posix()]=actual
    if variant=='full-v3' and not all(prediction_run.get(key) is True for key in ('campusRetrieverTrainingComplete','correspondenceTrainingComplete','formalCalibrationFrozen')):
        raise ValueError('Final v3 training/calibration is incomplete')
    if variant=='frozen-v2' and prediction_run.get('semanticEnabled') is not True:
        raise ValueError('Baseline must be actual frozen v2 with semantics enabled')
    if summary.get('evaluationScope')!='FORMAL_PROTOCOL' or summary.get('diagnosticControls') is not False or summary.get('split')!='final' or summary.get('finalProtocolExecuted') is not True:
        raise ValueError('Final summary is not a complete formal evaluation')
    rescored=score_predictions(queries,list(read_jsonl(predictions/'predictions.jsonl')),references,method,
        reference_sha256=reference_sha,bootstrap_resamples=1)
    if any(summary.get(key)!=rescored.get(key) for key in SUMMARY_FIELDS):
        raise ValueError('Final summary differs from CPU-rescored predictions')
    if rescored['queries']!=1200 or any(rescored[key]!=0 for key in ('missingPredictions','failedQueries','unscoredNormalQueries','invalidEvidence')):
        raise ValueError('Publication requires all1200 predictions, scored normal truth and valid evidence')
    return rescored,prediction_run


def _rate(summary,name,category=None,denominator=None):
    record=(summary['byCategory'][category]['rates'] if category else summary['rates'])[name]
    value=record.get('value')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or record.get('denominator',0)<=0:
        raise ValueError('Publication metric has no measured denominator: '+name)
    if denominator is not None and record['denominator']!=denominator:raise ValueError('Publication metric denominator differs: '+name)
    return value


def verify_quality(protocol,evaluation,predictions,baseline,baseline_predictions,calibration):
    """Return {metrics, verifiedFiles}, or fail without producing a READY package.

    Five arguments are project runtime directory Paths; calibration is the caller's
    already verified calibration.json dict. verifiedFiles uses project-relative
    POSIX keys and actual SHA256. A successful gate is not product activation.
    """
    verified={};protocol,_=_folder(protocol,{'manifest.json','queries.jsonl','references.jsonl'},verified)
    manifest=_read(protocol/'manifest.json');all_queries=list(read_jsonl(protocol/'queries.jsonl'))
    queries=select_protocol_queries(manifest,all_queries,'final')
    if len(queries)!=1200 or Counter(row['category'] for row in queries)!=Counter(FINAL_TARGETS):
        raise ValueError('Publication requires the unchanged1200 final category allocation')
    home=sum(row.get('homePrimary') is True for row in queries)
    if home<720:raise ValueError('Final actual home coverage requires at least720 of1200 queries')
    if len({event for row in queries for event in row['eventClusterIds']})<400:
        raise ValueError('Final evaluation requires at least400 source event clusters')
    reference_sha=_sha(protocol/'references.jsonl');protocol_sha=_sha(protocol/'READY')
    if calibration.get('referenceManifestSha256')!=reference_sha or calibration.get('operatingPointFrozen') is not True:
        raise ValueError('Final protocol and frozen calibration reference bank differ')
    references=list(read_jsonl(protocol/'references.jsonl'))
    current,run=_score(evaluation,predictions,'full-v3',protocol_sha,queries,reference_sha,references,verified)
    old,old_run=_score(baseline,baseline_predictions,'frozen-v2',protocol_sha,queries,reference_sha,references,verified)
    identity=_digest({key:calibration[key] for key in ('featureConfig','calibrator','referenceManifestSha256','thresholds','policy')})
    if run.get('calibrationIdentity')!=identity or run.get('featureConfig')!=calibration['featureConfig'] or run['methodConfigId']!=calibration.get('developmentMethodConfigId'):
        raise ValueError('Final method/working point differs from profile calibration')
    development,_=_folder(calibration['developmentRun'],{'run.json','summary.json'},verified)
    dev_predictions,dev_files=_folder(calibration['developmentPredictions'],{'run.json','predictions.jsonl'},verified)
    dev_run=_read(development/'run.json');dev_summary=_read(development/'summary.json');dev_prediction_run=_read(dev_predictions/'run.json')
    dev_sha=_sha(development/'READY');dev_queries=select_protocol_queries(manifest,all_queries,'dev')
    if len(dev_queries)!=400:raise ValueError('Profile development evidence requires400 queries')
    validate_development_evidence(dev_run,dev_summary,split_digest(dev_queries),reference_sha,run['methodConfigId'],400)
    if calibration.get('developmentEvidenceSha256')!=dev_sha or run.get('developmentEvidenceSha256')!=dev_sha:
        raise ValueError('Final and calibration development evidence differ')
    if dev_run.get('protocolReadySha256')!=protocol_sha or dev_run.get('predictionReadySha256')!=_sha(dev_predictions/'READY') or dev_run.get('predictionFiles')!=dev_files:
        raise ValueError('Development evidence protocol/prediction identity differs')
    expected_dev={'protocolReadySha256':protocol_sha,'splitQueriesSha256':split_digest(dev_queries),'referenceManifestSha256':reference_sha,
        'methodConfigId':run['methodConfigId'],'split':'dev','diagnosticControls':False,'variant':'full-v3','calibrationIdentity':identity,
        'featureConfig':calibration['featureConfig']}
    if any(dev_prediction_run.get(key)!=value for key,value in expected_dev.items()):
        raise ValueError('Development predictions use another profile/working point')
    if _implementation(dev_prediction_run,verified)!=run['implementation']:
        raise ValueError('Development and final predictions use different implementations')
    recall=_rate(current,'correctSourceRecallAt20',denominator=900)
    whole={key:_rate(current,'correctSourceEvidenceRate',key,250) for key in ('whole_synonym','whole_reordered')}
    false_prompt=_rate(current,'normalAnySourceFalsePromptRate',denominator=300)
    worst_case=_rate(current,'normalFalsePromptWorstCaseRate',denominator=300)
    offsets=_rate(current,'validEvidenceOffsets')
    comparisons={key:{'v3':_rate(current,'correctSourceEvidenceRate',key,count),
        'v2':_rate(old,'correctSourceEvidenceRate',key,count)} for key,count in [('local',200),('multi_source',100)]}
    if recall<.95 or any(value<.85 for value in whole.values()) or false_prompt>.05 or worst_case>.05 or offsets!=1:
        raise ValueError('Final quality targets not met; retain the current production model')
    if any(value['v3']+1e-12<value['v2']-.03 for value in comparisons.values()):
        raise ValueError('Final local/multi-source performance drops more than3 percentage points')
    verified[Path(__file__).relative_to(ROOT).as_posix()]=_sha(Path(__file__))
    return {'metrics':{'schemaVersion':'campus-release-quality-v1','qualityAccepted':True,'productActivated':False,
        'queries':1200,'homeQueries':home,'referenceManifestSha256':reference_sha,'methodConfigId':run['methodConfigId'],
        'baselineMethodConfigId':old_run['methodConfigId'],'recallAt20':recall,'wholeEvidenceRates':whole,
        'normalFalsePromptRate':false_prompt,'normalFalsePromptWorstCaseRate':worst_case,'validEvidenceOffsets':offsets,
        'localAndMultiComparisons':comparisons,'multiSourceAllFoundRate':_rate(current,'multiSourceAllFoundRate',denominator=100),
        'multiSourceMicroRecallAt20':_rate(current,'sourceMicroRecallAt20','multi_source'),
        'partialQueries':current['partialQueries'],'unknownExtraSourceAcceptances':current['unknownExtraSourceAcceptances'],
        'knownWrongSourceAcceptances':current['knownWrongSourceAcceptances'],'cpuRescored':True},'verifiedFiles':verified}
