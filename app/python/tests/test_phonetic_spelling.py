import unittest
from campus_workbench.phonetic_spelling import spelling_edits,guided_edits
from campus_workbench.inspection import _corrected_edits


class PhoneticSpellingTest(unittest.TestCase):
    def test_requires_unseen_bigram_homophone_context_and_unique_candidate(self):
        counts={'采访':25,'访提':1,'采访提':10,'提高':15,'高采访':5,'访提纲':8}
        text='采访提冈'
        # A spelling candidate is supplied by corpus statistics, never a typo-answer table.
        counts.update({'提纲':20,'访提纲':8})
        changes=spelling_edits(text,counts)
        self.assertEqual([(3,4,'冈','纲')],[(e['start'],e['end'],e['original'],e['replacement']) for e in changes])
        self.assertEqual([],spelling_edits('采访提纲',counts))
        self.assertEqual([],spelling_edits(text,dict(counts,提冈=1)))
        self.assertEqual([],spelling_edits('僻冈',{'僻纲':20})) # no independently attested surrounding context
        self.assertEqual([],spelling_edits(text,dict(counts,提刚=20,访提刚=8))) # ambiguous homophones
        corrected,_,recovered=guided_edits(text,'{"corrected":"采访"}',_corrected_edits,counts)
        self.assertEqual('采访提纲',corrected);self.assertEqual({3},recovered)
        corrected,_,recovered=guided_edits(text,'{"corrected":"采访提目"}',_corrected_edits,counts)
        self.assertEqual('采访提纲',corrected);self.assertEqual({3},recovered)
        self.assertEqual((text,[],set()),guided_edits(text,'{"corrected":"采访提冈"}',_corrected_edits,counts))


if __name__=='__main__':unittest.main()
