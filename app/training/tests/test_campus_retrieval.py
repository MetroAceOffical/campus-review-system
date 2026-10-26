import sys
import unittest
from pathlib import Path
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_campus_retrieval as campus


class CampusRetrievalTests(unittest.TestCase):
    def setUp(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        self.original={'documentId':'a','eventClusterId':'event-a','sourceClusterId':'cluster-a','institutionName':'甲校',
                       'title':'专家团队调研社区发展并参观公共文化服务设施','publishedAt':None,
                       'text':'专家团队走访城乡社区开展调研，并参观当地公共文化服务设施，围绕数字文化资源配置记录居民需求与服务过程。'}
        self.positive={'target':1,'query':self.original['text'],'source':self.original['text'],'sourceIds':['a'],
                       'sourceOffsets':{'start':0,'end':len(self.original['text'])},'transformationKind':'COPY_CONTROL'}
        texts=[('招生公告与考试报名流程和录取组织工作安排','招生部门组织考试报名，完成招生宣传与录取审核，面向考生说明报名材料、资格要求及考试流程。'),
               ('教师课程改革与专业教学设计培训项目','培训中心组织教师参加培训，围绕授课方法与教学设计研讨课程改革，并安排后续学习班实践。'),
               ('科研团队揭示新型材料结构与实验结果','科研团队开展材料研究与实验，通过多项实验测量分析晶体结构变化，论文报告研究结果与课题发现。'),
               ('技术中心设备故障检修与维护采购安排','技术中心组织设备故障检修，完成维护与维修记录，核对采购清单并安排后续检修任务和设备维护。')]
        self.candidates=[{'sourceId':str(i),'eventClusterId':'event-'+str(i),'sourceClusterId':'cluster-'+str(i),
                          'institutionName':'乙校','title':title,'text':text,'start':0,'end':len(text),'publishedAt':None} for i,(title,text) in enumerate(texts)]

    def test_four_negatives_are_rechecked_against_the_actual_query_and_distinct_sources(self):
        group=campus.supported_group(self.positive,self.original,self.candidates,self.tokenizer)
        self.assertIsNotNone(group)
        self.assertEqual(len(group['negatives']),4)
        self.assertTrue(all(row['basis']['supported'] for row in group['negatives']))
        duplicated=[self.candidates[0]]*4
        self.assertIsNone(campus.supported_group(self.positive,self.original,duplicated,self.tokenizer))
        duplicate_text=[{**self.candidates[0],'sourceId':str(i),'eventClusterId':'other-'+str(i),'sourceClusterId':'other-'+str(i)} for i in range(4)]
        self.assertIsNone(campus.supported_group(self.positive,self.original,duplicate_text,self.tokenizer))

    def test_an_oversized_source_is_not_silently_truncated_to_create_a_training_group(self):
        oversized={**self.positive,'source':' '.join(['longword']*513)}
        self.assertIsNone(campus.supported_group(oversized,self.original,self.candidates,self.tokenizer))


if __name__=='__main__':unittest.main()
