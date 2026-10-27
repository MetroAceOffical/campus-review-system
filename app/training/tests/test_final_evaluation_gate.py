import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evaluate_final as evaluation


class FinalEvaluationGateTests(unittest.TestCase):
    def test_formal_cli_scale_cannot_be_reduced_by_relabeling_a_tiny_manifest(self):
        evaluation.validate_evaluation_scale('dev',400,False)
        evaluation.validate_evaluation_scale('final',1200,False)
        evaluation.validate_evaluation_scale('dev',1,True)
        with self.assertRaises(ValueError):evaluation.validate_evaluation_scale('dev',399,False)
        with self.assertRaises(ValueError):evaluation.validate_evaluation_scale('final',1199,False)

    def setUp(self):
        self.manifest={'targetsBySplit':{'dev':{'copy_control':1,'local':1},'final':{'copy_control':1}},
                       'splitCounts':{'dev':{'constructed':1,'pending':1},'final':{'constructed':1,'pending':0}},'fullQuerySetReady':False}
        self.queries=[{'queryId':'d','split':'dev','category':'copy_control','transformationKind':'EXACT_COPY_CONTROL'},
                      {'queryId':'f','split':'final','category':'copy_control','transformationKind':'EXACT_COPY_CONTROL'}]

    def test_incomplete_material_refuses_formal_scoring_but_explicit_controls_are_separate(self):
        with self.assertRaises(ValueError):evaluation.select_protocol_queries(self.manifest,self.queries,'dev',False)
        selected=evaluation.select_protocol_queries(self.manifest,self.queries,'dev',True)
        self.assertEqual([q['queryId'] for q in selected],['d'])
        selected=evaluation.select_protocol_queries(self.manifest,self.queries,'final',False)
        self.assertEqual([q['queryId'] for q in selected],['f'])

    def test_wrong_category_counts_and_partial_ready_flags_cannot_be_relabeled_complete(self):
        manifest={**self.manifest,'splitCounts':{**self.manifest['splitCounts'],'dev':{'constructed':2,'pending':0}}}
        with self.assertRaises(ValueError):evaluation.select_protocol_queries(manifest,self.queries,'dev',False)
        with self.assertRaises(ValueError):evaluation.select_protocol_queries(manifest,self.queries,'train',False)

    def test_final_evidence_requires_full_compatible_development_and_method(self):
        run={'split':'dev','diagnosticControls':False,'splitQueriesSha256':'d'*64,'referenceManifestSha256':'r'*64,'methodConfigId':'method1'}
        summary={'queries':2,'diagnosticControls':False,'missingPredictions':0,'evaluationScope':'FORMAL_PROTOCOL'}
        evaluation.validate_development_evidence(run,summary,'d'*64,'r'*64,'method1',2)
        for changed in [{**run,'diagnosticControls':True},{**run,'splitQueriesSha256':'other'},{**run,'methodConfigId':'other'}]:
            with self.assertRaises(ValueError):evaluation.validate_development_evidence(changed,summary,'d'*64,'r'*64,'method1',2)


if __name__=='__main__':unittest.main()
