import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from tokenizers import Tokenizer,models,pre_tokenizers
from transformers import PreTrainedTokenizerFast

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import retrieval


class DenseRetrievalTests(unittest.TestCase):
    def setUp(self):
        backend=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        self.identity={'weightSha256':'a'*64,'tokenizerSha256':'b'*64,'pooling':'CLS','normalization':'L2','precision':'FP32'}

    def encode(self,texts):
        result=np.zeros((len(texts),768),dtype=np.float32)
        for index,text in enumerate(texts):result[index,int(hashlib.sha256(text.encode()).hexdigest()[:6],16)%768]=1.
        return result

    def test_token_blocks_keep_codepoint_offsets_and_reach_the_end(self):
        text='  first words 🙂 here. middle words stay here. final important fact  '
        blocks=retrieval.token_blocks(text,self.tokenizer,tokens=5,overlap=1)
        self.assertEqual(blocks[0]['start'],0)
        self.assertEqual(blocks[-1]['end'],len(text))
        self.assertTrue(all(block['text']==text[block['start']:block['end']] for block in blocks))
        self.assertTrue(all(len(self.tokenizer(block['text'],add_special_tokens=False)['input_ids'])<=5 for block in blocks))
        self.assertTrue(all(a['end']>=b['start'] for a,b in zip(blocks,blocks[1:])))

    def test_retokenizing_a_wordpiece_suffix_cannot_exceed_the_chunk_budget(self):
        vocabulary={word:index for index,word in enumerate(['[UNK]','very','##long','l','##o','##n','##g'])}
        backend=Tokenizer(models.WordPiece(vocabulary,unk_token='[UNK]'));backend.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=backend,unk_token='[UNK]')
        text='verylong verylong'
        blocks=retrieval.token_blocks(text,tokenizer,tokens=2,overlap=1)
        self.assertTrue(all(len(tokenizer(block['text'],add_special_tokens=False)['input_ids'])<=2 for block in blocks))
        self.assertEqual(blocks[-1]['end'],len(text))

    def test_frozen_memmap_search_checks_identity_hashes_and_excludes_own_manuscript(self):
        documents=[{'sourceWorkId':'w1','sourceRevisionId':'r1','sourceKey':'BODY','manuscriptId':'m1','text':'alpha source text'},
                   {'sourceWorkId':'w2','sourceRevisionId':'r2','sourceKey':'BODY','manuscriptId':'m2','text':'later source facts'}]
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'new-index'
            retrieval.build_dense_index(documents,self.tokenizer,self.encode,target,self.identity)
            index=retrieval.load_dense_index(target,self.identity)
            hits=retrieval.search_dense(index,self.encode(['alpha source text']),top_k=2,scan_rows=1)
            self.assertEqual(hits[0][0]['sourceRevisionId'],'r1')
            excluded=retrieval.search_dense(index,self.encode(['alpha source text']),top_k=2,exclude_manuscript_id='m1')
            self.assertEqual([row['sourceRevisionId'] for row in excluded[0]],['r2'])
            index['vectors']._mmap.close()
            with self.assertRaises(ValueError):retrieval.load_dense_index(target,{**self.identity,'weightSha256':'c'*64})
            with self.assertRaises(ValueError):retrieval.build_dense_index(documents,self.tokenizer,self.encode,target,self.identity)
            path=target/'vectors.f32'
            with path.open('r+b') as stream:stream.write(b'bad!')
            with self.assertRaises(ValueError):retrieval.load_dense_index(target,self.identity)

    def test_invalid_encoder_output_never_creates_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'invalid'
            with self.assertRaises(ValueError):retrieval.build_dense_index([{'sourceWorkId':'w','sourceRevisionId':'r','text':'original text'}],self.tokenizer,lambda texts:np.zeros((len(texts),768)),target,self.identity)
            self.assertFalse((target/'READY').exists())

    def test_hybrid_candidates_keep_semantic_only_sources_without_duplicate_rank_inflation(self):
        literal=[{'sourceRevisionId':'literal'}]
        dense=[{'sourceRevisionId':'semantic','score':.9}]*20+[{'sourceRevisionId':'other','score':.8}]
        result=retrieval.hybrid_sources(literal,dense,maximum=3)
        once=retrieval.hybrid_sources(literal,[dense[0],dense[-1]],maximum=3)
        self.assertEqual(result,once)
        self.assertEqual({row['sourceRevisionId'] for row in result},{'literal','semantic','other'})

    def test_source_pool_and_distinct_sources_apply_before_topk_across_scan_batches(self):
        blocks=[];vectors=[]
        for i,(revision,score) in enumerate([('self',1.),('a',.99),('a',.98),('b',.6),('c',.3)]):
            blocks.append({'sourceRevisionId':revision,'sourceWorkId':revision,'sourceKey':'BODY',
                           'manuscriptId':'own' if revision=='self' else revision,'start':i,'end':i+1,
                           'text':'x','blockId':str(i)})
            vector=np.zeros(768,dtype=np.float32);vector[0]=score;vector[1]=np.sqrt(1-score*score);vectors.append(vector)
        index={'blocks':blocks,'vectors':np.asarray(vectors),'manifest':{'featureSpaceId':'test'}}
        query=np.zeros((1,768),dtype=np.float32);query[0,0]=1.
        rows=retrieval.search_dense(index,query,top_k=3,scan_rows=1,exclude_manuscript_id='own',
                                    allowed_source_revision_ids={'a','b','c'},distinct_sources=True)[0]
        self.assertEqual([row['sourceRevisionId'] for row in rows],['a','b','c'])
        self.assertEqual(rows[0]['start'],1)
        restricted=retrieval.search_dense(index,query,top_k=1,scan_rows=2,allowed_source_revision_ids={'c'})[0]
        self.assertEqual(restricted[0]['sourceRevisionId'],'c')
        self.assertEqual(retrieval.search_dense(index,query,allowed_source_revision_ids=set()),[[]])


if __name__=='__main__':unittest.main()
