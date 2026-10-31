import unittest
from unittest.mock import patch
from copy import deepcopy
from campus_detection.six_model_bundle import fit_threshold,decision_scores,recommend

class SixModelBundleTest(unittest.TestCase):
    def test_cross_device_reload_requires_bounded_scores_same_decision_and_exact_cpu_repeat(self):
        from campus_detection.six_model_bundle import verify_member_reload
        gpu={'family':'cnn','parameters':{'device':'cuda'}}
        saved=[{'score':.2876206338405609}];actual=[{'score':.28740209341049194}]
        checked=verify_member_reload(gpu,saved,actual,actual)
        self.assertAlmostEqual(.00021854043006896973,checked['maxScoreDifference'])
        self.assertEqual(0.0,checked['cpuRepeatMaxDifference']);self.assertEqual(.001,checked['tolerance'])
        for manifest,expected,observed,repeat in [
            ({'family':'cnn','parameters':{'device':'cpu'}},saved,actual,None),
            ({'family':'bert','parameters':{'device':'cuda'}},saved,actual,None),
            (gpu,saved,[{'score':.28}],[{'score':.28}]),
            (gpu,[{'score':.5001}],[{'score':.4999}],[{'score':.4999}]),
            (gpu,saved,actual,[{'score':.2875}]),
            (gpu,saved,[{'score':float('nan')}],actual),
        ]:
            with self.assertRaises(ValueError):verify_member_reload(manifest,expected,observed,repeat)
    def test_release_metrics_are_an_object_and_inference_sources_are_pinned(self):
        from campus_detection.six_model_bundle import calibrated_metrics,inference_dependencies
        rows=[dict(label=0,score=.1),dict(label=1,score=.9)]
        fit=fit_threshold([0,1],[.1,.9],'lr');metrics=calibrated_metrics(rows,fit)
        self.assertEqual(1.0,metrics['f1']);self.assertEqual(2,metrics['rows'])
        files=inference_dependencies()
        self.assertIn('app/python/campus_workbench/training.py',files)
        self.assertIn('validation/text/round2.py',files)
    def test_one_alignment_is_independently_scored_by_each_model(self):
        from campus_detection.six_model_bundle import detect,FAMILIES
        from campus_shared.contracts import file_sha256
        members=[dict(family=f,modelId=f,modelFolder=f,modelManifestSha256='hash',calibration=dict(threshold=.5,scoreType='probability',scale=.2)) for f in FAMILIES]
        pairs=[dict(sentence1='原稿甲'*12,sentence2='来源甲'*12),dict(sentence1='原稿乙'*12,sentence2='来源乙'*12)]
        template=dict(status='COMPLETED',actualConfig=dict(contextPolicy={}),evidence=[dict(evidenceId='same-candidate',sourceWorkId='source',acceptedCandidate=False,semanticWindows=[dict(queryStart=i*40,queryEnd=i*40+36,sourceStart=i*40,sourceEnd=i*40+36,queryText=p['sentence1'],sourceText=p['sentence2'],tfidfScore=.8,score=0) for i,p in enumerate(pairs)])])
        def align(request,library,models):models['predictBert'](pairs);return deepcopy(template)
        calls=[]
        def score(folder,rows,emit,device_override=None):calls.append((folder.name,deepcopy(rows)));return [dict(score=.9 if folder.name=='bert' else .1) for row in rows]
        models={'sixModelBundles':{'config':dict(members=members,textConfig=dict(sixModelBundle=dict(bundleId='group',primaryFamily='bert')))}}
        with patch('campus_detection.contextual_text.detect',side_effect=align) as plan,patch('campus_workbench.training.predict',side_effect=score),patch('campus_detection.six_model_bundle.file_sha256',return_value='hash'),patch('campus_detection.text_refinement.refine',side_effect=lambda result,*args:result),patch('campus_detection.mutual_text.apply_guard',side_effect=lambda result:result):
            result=detect({'configId':'config','text':'原稿'}, {},models)
        self.assertEqual(1,plan.call_count);self.assertEqual(list(FAMILIES),[f for f,_ in calls]);self.assertTrue(all(rows==pairs for _,rows in calls))
        self.assertEqual(6,len(result['bundleResults']));self.assertEqual('bert',result['primaryFamily'])
        self.assertTrue(result['bundleResults'][-1]['suspectedReuse']);self.assertFalse(result['bundleResults'][0]['suspectedReuse'])
        self.assertEqual(result['evidence'],result['bundleResults'][-1]['result']['evidence'])
    def test_native_margin_uses_own_validation_threshold(self):
        fit=fit_threshold([0,0,1,1],[-4,-2,-1,3],'svm')
        scores=decision_scores([-4,-2,-1,3],fit)
        self.assertEqual([False,False,True,True],[s>=.5 for s in scores]);self.assertEqual(1,fit['macroF1'])
        self.assertEqual('margin',fit['scoreType'])
    def test_primary_is_validation_choice_not_biggest_raw_score(self):
        members=[{'family':'lr','calibration':fit_threshold([0,0,1,1],[.9,.85,.95,.8],'lr')},{'family':'bert','calibration':fit_threshold([0,0,1,1],[.01,.02,.1,.2],'bert')}]
        self.assertEqual('bert',recommend(members))
        fit=members[1]['calibration'];self.assertEqual([False,False,True,True],[s>=.5 for s in decision_scores([.01,.02,.1,.2],fit)])
