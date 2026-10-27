import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_text_protocol as protocol


class TextProtocolTests(unittest.TestCase):
    def originals(self,split,count=12):
        return [{'documentId':split+str(i),'sourceClusterId':split+'-cluster'+str(i),'eventClusterId':split+'-event'+str(i),
                 'split':split,'institutionName':'南京传媒学院' if i<2 else '其他学校','title':'公开校园报道'+str(i),
                 'text':f'来源{split}{i}。'+('校园活动参与者记录了各项独立事实，按实际过程整理材料。'*9)+f'该篇报道的编号为{i}。'} for i in range(count)]

    def test_control_texts_reconstruct_frozen_sources_without_training_or_negative_fabrication(self):
        partitions={split:self.originals(split) for split in ['calibration','dev','final']}
        targets={split:{'copy_control':2,'whole_reordered':2,'local':1,'multi_source':1,'same_event_negative':1} for split in partitions}
        result=protocol.build_protocol(partitions,[],targets=targets)
        originals={r['documentId']:r for rows in partitions.values() for r in rows}
        self.assertEqual(len(result['plans']),21)
        self.assertEqual(len(result['queries']),9)
        self.assertFalse(result['summary']['fullQuerySetReady'])
        for query in result['queries']:
            self.assertIn(query['split'],partitions)
            self.assertNotEqual(query['queryManuscriptId'],'reference:'+query['expectedSourceIds'][0])
            self.assertEqual(query['truthScope'],'known_positive_sources_only')
            for mapping in query['sourceMappings']:
                source=originals[mapping['sourceRevisionId']]
                self.assertEqual(source['split'],query['split'])
                q=query['query'][mapping['queryStart']:mapping['queryEnd']]
                s=source['text'][mapping['sourceStart']:mapping['sourceEnd']]
                self.assertEqual(q,s)
        pending=[row for row in result['plans'] if row['category']=='same_event_negative']
        self.assertTrue(all(row['constructionStatus']=='NEEDS_SUPPORTED_NEGATIVE_SCOPE' for row in pending))

    def test_repeated_publications_of_one_natural_body_form_one_query_with_multiple_provenance_records(self):
        original=self.originals('final',1)[0]
        natural=[{'relationId':'r'+str(i),'split':'final','sourceIds':[original['documentId']],
                  'query':original['text'],'source':original['text'],'contentProof':{'accepted':True},
                  'queryUrl':'https://school.example/article'+str(i),'queryPageSha256':str(i)*64} for i in range(2)]
        result=protocol.build_protocol({'final':self.originals('final')},natural,targets={'final':{'copy_control':2}})
        queries=[row for row in result['queries'] if row['labelOrigin']=='traceable_correspondence']
        self.assertEqual(len(queries),1)
        self.assertEqual(len(queries[0]['naturalProvenance']),2)
        self.assertEqual(len(result['queries']),2)
        self.assertNotEqual(result['queries'][0]['queryId'],result['queries'][1]['queryId'])

    def test_parent_event_cap_and_shortfalls_are_explicit(self):
        rows=self.originals('final',1)
        result=protocol.build_protocol({'final':rows},[],targets={'final':{'copy_control':2,'whole_reordered':3}})
        self.assertTrue(any(row['constructionStatus']=='NEEDS_NEW_PARENTS' for row in result['plans']))
        self.assertLessEqual(result['summary']['maximumPlannedQueriesPerEvent'],2)
        self.assertFalse(result['summary']['fullQuerySetReady'])

    def test_split_mismatch_and_a_training_parent_cannot_enter_the_protocol(self):
        row=self.originals('dev',1)[0]
        with self.assertRaises(ValueError):protocol.build_protocol({'final':[row]},[],targets={'final':{'copy_control':1}})
        with self.assertRaises(ValueError):protocol.build_protocol({'train':[{**row,'split':'train'}]},[],targets={'train':{'copy_control':1}})


if __name__=='__main__':unittest.main()
