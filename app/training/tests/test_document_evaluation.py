import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import document_evaluation as evaluation
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_workbench.inspection import compare_fields
from run_document_evaluation import aggregate


class DocumentEvaluationTests(unittest.TestCase):
    def test_missing_context_rank_remains_in_known_denominator(self):
        result=aggregate([dict(contextEligible=True,contextRank=None,error='model failed'),
                          dict(contextEligible=False,contextRank=None,realOrSynthetic='real',error=None)])
        self.assertEqual(result['knownContextQueries'],1)
        self.assertEqual(result['relatedTop1'],0)
        self.assertEqual(result['failedQueries'],1)
    def test_exact_edit_identity_and_failed_samples_stay_in_recall(self):
        sample = {'text':'已经已经开展活动。', 'expected':[{'start':0,'end':4,'original':'已经已经','replacement':'已经'}]}
        correct = {'field':'BODY','start':0,'end':4,'original':'已经已经','replacement':'已经'}
        self.assertEqual(evaluation.edit_score(sample,[correct]), {'truePositive':1,'falsePositive':0,'falseNegative':0,'invalidSuggestions':0})
        wrong = dict(correct,start=1)
        self.assertEqual(evaluation.edit_score(sample,[wrong])['truePositive'],0)
        self.assertEqual(evaluation.edit_score(sample,[wrong])['invalidSuggestions'],1)
        self.assertEqual(evaluation.edit_score(sample,[])['falseNegative'],1)

    def test_material_counts_and_field_truth_do_not_use_extractor(self):
        rows=evaluation.grammar_material()
        self.assertEqual(len(rows),500)
        self.assertEqual(len({r['sampleId'] for r in rows}),500)
        for row in rows:
            for edit in row['expected']:
                self.assertEqual(row['text'][edit['start']:edit['end']],edit['original'])
        sample={'sampleId':'ocr-synthetic:026:original','transformation':'original','groundTruthText':'原渲染文字'}
        context,truth=evaluation.fact_material(sample)
        self.assertIn('2026年11月27日',context)
        self.assertIn('Media Lab A226',context)
        self.assertEqual(truth,{'日期':'MATCH','地点':'MATCH','主办单位':'INSUFFICIENT'})
        sample['transformation']='downscale_jpeg'
        self.assertEqual(evaluation.fact_material(sample)[1]['日期'],'CONFLICT')

    def test_field_comparison_normalizes_layout_and_validates_dates(self):
        rows=compare_fields('Date / 日期: ２０２６-１１-２７\n地点: MediaLabA226',
                            '日期：2026年11月27日。\n地点：Media Lab A226。')
        self.assertEqual({r['field']:r['status'] for r in rows},{'日期':'MATCH','地点':'MATCH','主办单位':'INSUFFICIENT'})
        self.assertEqual(compare_fields('2026/11/27','2026年11月28日')[0]['status'],'CONFLICT')
        self.assertEqual(compare_fields('2026-02-30','2026年2月28日')[0]['status'],'INSUFFICIENT')
        self.assertEqual(compare_fields('地点：综合实验楼 A201室','地点：综合实验楼A202室')[1]['status'],'CONFLICT')
        self.assertEqual(compare_fields('2026-11-27及2026-11-28','2026年11月27日')[0]['status'],'INSUFFICIENT')


if __name__=='__main__':unittest.main()
