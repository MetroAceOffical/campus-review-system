import unittest
from campus_detection.mutual_text import apply_guard


def report(lengths,literal=False):
    windows=[];q=s=0
    for a,b in lengths:
        windows.append(dict(queryStart=q,queryEnd=q+a,sourceStart=s,sourceEnd=s+b,citationSupport=True,score=.8,tfidfScore=.4));q+=a;s+=b
    return dict(evidence=[dict(literalAcceptedCandidate=literal,acceptedCandidate=literal,
        semanticSummary=dict(suspectedReuse=True,supportingPairs=len(windows)),semanticWindows=windows)])


class MutualTextTest(unittest.TestCase):
    def test_short_source_cannot_inflate_long_query_support(self):
        value=report([(53,33),(13,13)],literal=True)
        apply_guard(value)
        item=value['evidence'][0]
        self.assertFalse(item['semanticSummary']['suspectedReuse'])
        self.assertTrue(item['literalAcceptedCandidate'])
        self.assertEqual(46,item['semanticSummary']['pairedCharacters'])
        self.assertFalse(any(w['citationSupport'] for w in item['semanticWindows']))

    def test_balanced_independent_rewrite_support_survives(self):
        value=report([(52,39),(30,40)])
        apply_guard(value)
        self.assertTrue(value['evidence'][0]['semanticSummary']['suspectedReuse'])
        self.assertEqual(69,value['evidence'][0]['semanticSummary']['pairedCharacters'])


if __name__=='__main__':unittest.main()
