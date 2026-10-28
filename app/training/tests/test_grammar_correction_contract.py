import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_workbench.inspection import _corrected_edits

class GrammarCorrectionTests(unittest.TestCase):
    def test_numbers_are_preserved_including_occurrences_and_edits_are_minimal(self):
        value,edits=_corrected_edits('同学们积极响映号召。','{"corrected":"同学们积极响应号召。"}')
        self.assertEqual(value,'同学们积极响应号召。');self.assertEqual(len(edits),1)
        with self.assertRaises(ValueError):_corrected_edits('第2组参加。','{"corrected":"第2组和第2组参加。"}')
        with self.assertRaises(ValueError):_corrected_edits('师生到场。','{"corrected":"全体师生将在明日到达指定地点。"}')

if __name__=='__main__':unittest.main()
