import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_workbench.grammar_edits import correction_text

class GrammarEditTests(unittest.TestCase):
    def test_atomic_edits_are_exact_unambiguous_and_do_not_drop_words(self):
        text='活动取得圆满成攻，同学们积极响映号召。'
        raw='{"corrections":[{"original":"成攻","replacement":"成功"},{"original":"响映","replacement":"响应"}]}'
        self.assertEqual(correction_text(text,raw),'活动取得圆满成功，同学们积极响应号召。')
        self.assertEqual(correction_text(text,'{"corrections":[]}'),text)
        for bad in ['{"corrections":[{"original":"成攻","replacement":""}]}',
                    '{"corrections":[{"original":"不存在","replacement":"成功"}]}',
                    '{"corrections":[{"original":"成攻","replacement":"成功"},{"original":"成攻","replacement":"成功"}]}']:
            with self.assertRaises(ValueError):correction_text(text,bad)
        with self.assertRaises(ValueError):correction_text('成攻成攻','{"corrections":[{"original":"成攻","replacement":"成功"}]}')

if __name__=='__main__':unittest.main()
