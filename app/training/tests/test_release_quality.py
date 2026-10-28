"""Synthetic protocol fixtures verify publication guards, never model quality."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'));sys.path.insert(0,str(ROOT/'app/training'))
from campus_detection import release_quality
from campus_detection.retrieval import _digest,_sha
from evaluate_final import split_digest
from text_evaluation import score_predictions

TARGETS={'whole_synonym':250,'whole_reordered':250,'local':200,'multi_source':100,
         'copy_control':100,'same_event_negative':200,'template_normal':100}

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
def freeze(folder):write(folder/'READY',{p.name:_sha(p) for p in folder.iterdir() if p.name!='READY'})
def lines(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')


class ReleaseQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.protocol=self.folder/'protocol';self.protocol.mkdir()
        refs=[{'sourceRevisionId':key,'sourceKey':'BODY','text':'甲乙'} for key in ('a','b')]
        lines(self.protocol/'references.jsonl',refs);refsha=_sha(self.protocol/'references.jsonl')
        queries=[]
        for split,targets in [('dev',{'copy_control':400}),('final',TARGETS)]:
            number=0
            for category,count in targets.items():
                for _ in range(count):
                    normal=category in {'same_event_negative','template_normal'}
                    expected=[] if normal else ['a','b'] if category=='multi_source' else ['a']
                    queries.append({'queryId':split+str(number),'query':'甲乙','querySha256':hashlib.sha256('甲乙'.encode()).hexdigest(),
                        'split':split,'category':category,'homePrimary':number<720,'eventClusterIds':[split+str(number)],
                        'expectedSourceIds':expected,'truthScope':'closed_reference_set' if normal else 'known_positive_sources_only',
                        'labelConfidence':'known','sourceMappings':[{'sourceRevisionId':key,'sourceKey':'BODY','queryStart':0,'queryEnd':2,
                            'sourceStart':0,'sourceEnd':2,'mappingType':'EXACT_SEGMENT'} for key in expected],
                        'negativeScope':{'auditVerified':True,'referenceManifestSha256':refsha,'excludedSourceRevisionIds':[],
                            'supportedNegativeSources':['a','b']} if normal else {}})
                    number+=1
        lines(self.protocol/'queries.jsonl',queries)
        write(self.protocol/'manifest.json',{'targetsBySplit':{'dev':{'copy_control':400},'final':TARGETS},
            'splitCounts':{'dev':{'pending':0,'constructed':400},'final':{'pending':0,'constructed':1200}}})
        freeze(self.protocol)
        self.calibration={'featureConfig':{},'calibrator':{},'referenceManifestSha256':refsha,'thresholds':{},'policy':None,'operatingPointFrozen':True}
        calibration_identity=_digest({k:self.calibration[k] for k in ('featureConfig','calibrator','referenceManifestSha256','thresholds','policy')})
        def export(name,split,variant,method,development=None):
            predictions=self.folder/name;predictions.mkdir();evaluation=self.folder/(name+'-metrics');evaluation.mkdir()
            selected=[r for r in queries if r['split']==split]
            rows=[{'queryId':r['queryId'],'querySha256':r['querySha256'],'methodConfigId':method,'referenceManifestSha256':refsha,
                'coverageStatus':'COMPLETE','candidateSources':[{'sourceRevisionId':key} for key in r['expectedSourceIds']],
                'sourceDecisions':[{'sourceRevisionId':key,'sourceKey':'BODY','acceptedCandidate':True} for key in r['expectedSourceIds']],
                'pairs':[{'sourceRevisionId':key,'sourceKey':'BODY','queryStart':0,'queryEnd':2,'sourceStart':0,'sourceEnd':2,
                    'queryText':'甲乙','sourceText':'甲乙','evidenceKind':'LITERAL_EXACT'} for key in r['expectedSourceIds']]} for r in selected]
            run={'protocolReadySha256':_sha(self.protocol/'READY'),'splitQueriesSha256':split_digest(selected),'referenceManifestSha256':refsha,
                'methodConfigId':method,'split':split,'diagnosticControls':False,'variant':variant,'operatingPointFrozen':True,
                'developmentEvidenceSha256':_sha(development/'READY') if development else None,
                'calibrationIdentity':calibration_identity,'featureConfig':{},'campusRetrieverTrainingComplete':variant=='full-v3',
                'correspondenceTrainingComplete':variant=='full-v3','formalCalibrationFrozen':variant=='full-v3','semanticEnabled':variant=='frozen-v2'}
            code=['app/training/v3_workflow.py','app/training/evaluate_final.py','app/training/text_evaluation.py',
                'app/python/campus_detection/v3_pipeline.py','app/python/campus_detection/v3_runtime.py',
                'app/python/campus_detection/retrieval_model.py','app/python/campus_detection/task_model.py']
            if variant=='frozen-v2':code.append('app/training/export_legacy_evaluation.py')
            run['implementation']={name:_sha(ROOT/name) for name in code}
            write(predictions/'run.json',run);lines(predictions/'predictions.jsonl',rows);freeze(predictions)
            summary=score_predictions(selected,rows,refs,method,reference_sha256=refsha,bootstrap_resamples=1)
            details=summary.pop('queryResults');summary.update({'evaluationScope':'FORMAL_PROTOCOL','diagnosticControls':False,'split':split,'finalProtocolExecuted':split=='final'})
            write(evaluation/'summary.json',summary);lines(evaluation/'query-results.jsonl',details)
            write(evaluation/'run.json',{**run,'predictionReadySha256':_sha(predictions/'READY'),
                'predictionFiles':json.loads((predictions/'READY').read_text()),
                'evaluatorCodeSha256':_sha(ROOT/'app/training/evaluate_final.py'),
                'metricsCodeSha256':_sha(ROOT/'app/training/text_evaluation.py')});freeze(evaluation)
            return evaluation,predictions
        dev,dev_predictions=export('dev-v3','dev','full-v3','v3')
        self.calibration.update({'developmentRun':str(dev),'developmentPredictions':str(dev_predictions),
            'developmentEvidenceSha256':_sha(dev/'READY'),'developmentMethodConfigId':'v3'})
        self.evaluation,self.predictions=export('final-v3','final','full-v3','v3',dev)
        baseline_dev,_=export('dev-v2','dev','frozen-v2','v2')
        self.baseline,self.baseline_predictions=export('final-v2','final','frozen-v2','v2',baseline_dev)

    def verify(self):
        return release_quality.verify_quality(self.protocol,self.evaluation,self.predictions,self.baseline,self.baseline_predictions,self.calibration)

    def test_full_frozen_chain_is_rescored_without_loading_models(self):
        result=self.verify()
        self.assertTrue(result['metrics']['qualityAccepted'])
        self.assertEqual(result['metrics']['homeQueries'],720)
        self.assertEqual(result['metrics']['recallAt20'],1.)
        self.assertIn((self.predictions/'predictions.jsonl').relative_to(ROOT).as_posix(),result['verifiedFiles'])
        self.assertNotIn('torch',sys.modules)

    def test_changed_summary_and_actual_home_shortfall_are_rejected(self):
        path=self.evaluation/'summary.json';summary=json.loads(path.read_text(encoding='utf-8'))
        summary['rates']['correctSourceRecallAt20']['value']=.99;write(path,summary);freeze(self.evaluation)
        with self.assertRaisesRegex(ValueError,'summary|Summary'):self.verify()
        rows=[json.loads(line) for line in (self.protocol/'queries.jsonl').read_text(encoding='utf-8').splitlines()]
        for row in rows:row['homePrimary']=False
        lines(self.protocol/'queries.jsonl',rows);freeze(self.protocol)
        with self.assertRaisesRegex(ValueError,'720|home|Home'):self.verify()


if __name__=='__main__':unittest.main()
