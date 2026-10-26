import unittest
from campus_detection.semantic import sentence_units, semantic_summary


class CharacterTokenizer:
    def __call__(self, text, **kwargs):
        return {'input_ids': list(range(len(text))),
                'offset_mapping': [(i, i + 1) for i in range(len(text))]}


class SemanticTextTest(unittest.TestCase):
    def test_new_method_keeps_literal_feature_space_and_distinct_legacy_identity(self):
        from campus_detection.models import configurations
        current, _ = configurations()
        legacy, _ = configurations(legacy=True)
        self.assertEqual(current['featureSpaceId'], legacy['featureSpaceId'])
        self.assertEqual(current['baseConfigId'], legacy['configId'])
        self.assertNotEqual(current['configId'], legacy['configId'])

    def test_sentence_and_clause_units_keep_unicode_offsets_and_pair_budget(self):
        text = 'A😀中文完整句子。' + '甲' * 25 + '，' + '乙' * 25 + '，' + '丙' * 25 + '。'
        units = sentence_units(text, CharacterTokenizer(), 60, minimum=4)
        self.assertEqual(units[0]['text'], 'A😀中文完整句子。')
        self.assertTrue(all(text[u['start']:u['end']] == u['text'] for u in units))
        self.assertTrue(all(len(u['text']) <= 60 for u in units))
        self.assertEqual(''.join(u['text'] for u in units), text)
        self.assertIn('，' + '乙', units[1]['text'])

    def test_one_high_score_or_repeated_source_does_not_establish_semantic_reuse(self):
        first = dict(queryStart=0, queryEnd=40, sourceStart=0, sourceEnd=40, score=.9, tfidfScore=.4)
        self.assertFalse(semantic_summary([first], {})['suspectedReuse'])
        duplicate = dict(first, queryStart=45, queryEnd=85)
        self.assertFalse(semantic_summary([first, duplicate], {})['suspectedReuse'])
        second = dict(first, queryStart=45, queryEnd=85, sourceStart=45, sourceEnd=85)
        summary = semantic_summary([first, second], {})
        self.assertTrue(summary['suspectedReuse'])
        self.assertEqual(summary['matchedQueryCharacters'], 80)
        self.assertFalse(semantic_summary([dict(first, tfidfScore=.1), second], {})['suspectedReuse'])


if __name__ == '__main__':
    unittest.main()
