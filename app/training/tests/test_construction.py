import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import construct_correspondence as construction
from construct_correspondence import source_segments, rewrite_checks, generation_prompt


class ConstructionTests(unittest.TestCase):
    def test_prompt_v3_enforces_absolute_length_and_conservative_sampling(self):
        prompt=generation_prompt('2026年安排200名同学参加调研。',[],version='3')
        self.assertIn('字数下限',prompt)
        self.assertIn('不要续写',prompt)
        self.assertEqual(construction.generation_options('3',0)['temperature'],.25)
        self.assertEqual(construction.generation_options('2',0)['temperature'],.7)

    def test_reuse_keeps_inherited_results_without_local_attempt_rows(self):
        import tempfile,sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'generation.sqlite';db=sqlite3.connect(path)
            db.executescript('CREATE TABLE segments(id TEXT,parent_id TEXT,start INT,end INT,result TEXT,checks TEXT); CREATE TABLE attempts(segment_id TEXT,attempt_no INT,output TEXT,checks TEXT);')
            db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?)',('inherited','parent',0,5,'valid inherited result','{}'));db.commit();db.close()
            rows=construction.reusable_attempts(Path(folder))
            self.assertEqual(rows,[('inherited','parent',0,5,0,'valid inherited result')])

    def test_reuse_rejects_an_output_cut_off_at_the_token_budget(self):
        import tempfile,sqlite3,json
        with tempfile.TemporaryDirectory() as folder:
            db=sqlite3.connect(Path(folder)/'generation.sqlite')
            db.executescript('CREATE TABLE segments(id TEXT,parent_id TEXT,start INT,end INT,result TEXT,checks TEXT); CREATE TABLE attempts(segment_id TEXT,attempt_no INT,output TEXT,checks TEXT);')
            checks=json.dumps({'reasons':['OUTPUT_TOKEN_BUDGET']})
            db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?)',('cutoff','parent',0,5,'unfinished',checks))
            db.execute('INSERT INTO attempts VALUES(?,?,?,?)',('cutoff',1,'unfinished',checks));db.commit();db.close()
            self.assertEqual(construction.reusable_attempts(Path(folder)),[])

    def test_segment_copy_is_a_copy_control_and_does_not_make_the_whole_a_paraphrase(self):
        text='2026年10月12日，南京传媒学院组织200名学生参与乡村志愿服务，团队整理调研记录并反馈成果。'
        segment=rewrite_checks(text,text,[],require_rewording=False)
        self.assertTrue(segment['accepted'])
        self.assertEqual(segment['transformationKind'],'COPY_CONTROL')
        self.assertFalse(rewrite_checks(text,text,[])['accepted'])
        self.assertFalse(rewrite_checks(text,text.replace('200','300'),[],require_rewording=False)['accepted'])

    def test_prompt_lists_every_number_and_explicit_name_as_required_facts(self):
        prompt=generation_prompt('2026年组织200名学生完成调研。',['南京传媒学院'],version='2')
        self.assertIn('2026',prompt)
        self.assertIn('200',prompt)
        self.assertIn('必须逐项保留',prompt)

    def test_segmentation_preserves_every_original_codepoint_and_offset(self):
        text='第一段包含emoji🙂与数字2026。\n第二段\u2028保持原始字符。'+('另一段较长的事实陈述。'*20)
        pieces=source_segments(text,48)
        self.assertEqual(''.join(text[p['sourceStart']:p['sourceEnd']] for p in pieces),text)
        self.assertEqual(pieces[0]['sourceStart'],0)
        self.assertEqual(pieces[-1]['sourceEnd'],len(text))
        self.assertTrue(all(p['sourceEnd']-p['sourceStart']<=48 for p in pieces))
        self.assertTrue(all(a['sourceEnd']==b['sourceStart'] for a,b in zip(pieces,pieces[1:])))

    def test_copied_text_missing_numbers_and_length_failure_are_quarantined(self):
        text='2026年10月12日，南京传媒学院组织200名学生参与乡村志愿服务，团队围绕社区教育开展调研，整理访谈记录并向当地居民反馈成果。'
        self.assertIn('INSUFFICIENT_REWORDING',rewrite_checks(text,text,['南京传媒学院'])['reasons'])
        changed='南京传媒学院于2026年10月12日开展乡村志愿行动。学子先访谈社区居民，再整理调查资料，最后把教育服务的研究发现反馈给居民。'
        self.assertIn('NUMBER_SET_CHANGED',rewrite_checks(text,changed,['南京传媒学院'])['reasons'])
        self.assertIn('LENGTH_RATIO',rewrite_checks(text,'志愿活动',[])['reasons'])
