import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from heldout_queries import materialize,assert_heldout_sources,substantive_mix

class HeldoutQueryTests(unittest.TestCase):
    def test_multisource_query_preserves_both_original_ranges(self):
        refs={'a':{'text':'前甲乙后','sourceSplit':'dev'},'b':{'text':'首丙丁尾','sourceSplit':'dev'}}
        plan={'queryId':'q','split':'dev','category':'multi_source','expectedSourceIds':['a','b'],'segmentIds':['x','y']}
        parts={'x':{'sourceId':'a','start':1,'end':3,'result':'改写甲乙','kind':'PARAPHRASE'},'y':{'sourceId':'b','start':1,'end':3,'result':'改写丙丁','kind':'PARAPHRASE'}}
        row=materialize(plan,parts,refs)
        self.assertEqual(row['query'],'改写甲乙\n改写丙丁')
        for mapping in row['sourceMappings']:
            self.assertEqual(row['query'][mapping['queryStart']:mapping['queryEnd']],parts['x' if mapping['sourceRevisionId']=='a' else 'y']['result'])
    def test_local_context_is_real_excluded_and_offsets_remain_codepoints(self):
        refs={'a':{'text':'甲乙','sourceSplit':'calibration'},'context':{'text':'😀校园活动。另一段报道。','sourceSplit':'calibration'}}
        plan={'queryId':'q','split':'calibration','category':'local','expectedSourceIds':['a'],'segmentIds':['x'],'contextSourceId':'context','contextEnd':len(refs['context']['text'])}
        row=materialize(plan,{'x':{'sourceId':'a','start':0,'end':2,'result':'调整表述','kind':'PARAPHRASE'}},refs)
        span=row['sourceMappings'][0]
        self.assertEqual(row['query'][span['queryStart']:span['queryEnd']],'调整表述')
        self.assertEqual(row['negativeScope']['excludedSourceRevisionIds'],['context'])
        self.assertEqual(row['contextProvenance']['text'],refs['context']['text'])
    def test_training_or_foreign_partition_is_never_a_construction_parent(self):
        refs={'a':{'sourceSplit':'train'},'b':{'sourceSplit':'final'}}
        for key in refs:
            with self.assertRaises(ValueError):assert_heldout_sources({'split':'dev','constructionParents':[key]},refs)
    def test_legacy_pair_with_failed_lexical_support_cannot_count_as_correspondence(self):
        from export_legacy_evaluation import convert
        from text_evaluation import _supported
        query={'queryId':'q','querySha256':'h'}
        result={'actualConfig':{'semanticPolicy':{'scoreThreshold':.5,'lexicalFloor':.25}},'elapsedMs':1,
            'evidence':[{'sourceRevisionId':'a','sourceKey':'BODY','acceptedCandidate':False,'matches':[],
                         'semanticSummary':{'suspectedReuse':True},'semanticWindows':[{'score':.9,'tfidfScore':.1}]}]}
        record=convert(query,result,'method','reference',True)
        self.assertEqual(len(record['pairs']),1)
        self.assertFalse(_supported(record['pairs'][0],record))
        self.assertEqual(record['decisionScore'],.9)
    def test_rigid_fields_can_remain_but_cannot_fill_paraphrase_quotas(self):
        refs={'a':{'text':'甲乙丙丁'}}
        parts={'x':{'sourceId':'a','start':0,'end':2,'checks':{'accepted':True,'transformationKind':'PARAPHRASE'}},'y':{'sourceId':'a','start':2,'end':4,'checks':{'accepted':True,'transformationKind':'COPY_CONTROL'}}}
        self.assertTrue(substantive_mix({'category':'whole_synonym','segmentIds':['x','y']},parts,refs))
        self.assertFalse(substantive_mix({'category':'local','segmentIds':['x','y']},parts,refs))
        self.assertFalse(substantive_mix({'category':'whole_synonym','segmentIds':['y']},parts,refs))

if __name__=='__main__':unittest.main()
