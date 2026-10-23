import unittest
from campus_ocr.recognizer import normalize_result
from campus_shared.contracts import ContractError

class OcrContractTest(unittest.TestCase):
    def test_empty_ocr_is_not_no_reuse(self):
        result=normalize_result({'rec_texts':[],'rec_scores':[],'rec_polys':[]},100,80)
        self.assertEqual(result['textSearchStatus'],'NOT_RUN')
        self.assertFalse(result['noReuseClaim'])
        self.assertIn('EMPTY_OCR',result['qualityFlags'])
    def test_scaled_coordinates_return_to_original_pixels(self):
        result=normalize_result({'rec_texts':['测试'],'rec_scores':[.7],'rec_polys':[[[5,10],[20,10],[20,20],[5,20]]]},100,80,{'scaleX':.5,'scaleY':.5,'offsetX':0,'offsetY':0})
        self.assertEqual(result['recognitionLines'][0]['polygon'],[[10.,20.],[40.,20.],[40.,40.],[10.,40.]])
        self.assertEqual(result['lowConfidenceLineIds'],['line-1'])
        self.assertIn('LOW_CONFIDENCE',result['qualityFlags'])
    def test_mismatched_lines_and_out_of_bounds_are_rejected(self):
        with self.assertRaises(ContractError):normalize_result({'rec_texts':['a'],'rec_scores':[],'rec_polys':[]},100,80)
        with self.assertRaises(ContractError):normalize_result({'rec_texts':['a'],'rec_scores':[.9],'rec_polys':[[[0,0],[101,0],[101,1],[0,1]]]},100,80)

if __name__=='__main__':unittest.main()
