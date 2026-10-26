import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_ocr import fallback


class OcrFallbackTests(unittest.TestCase):
    def test_verified_images_with_extensionless_storage_names_use_the_original_decoded_pixels(self):
        import tempfile,io
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            payload=io.BytesIO();Image.new('RGB',(80,60),(10,20,30)).save(payload,format='PNG')
            path=Path(folder)/'stored.img';path.write_bytes(payload.getvalue())
            value=fallback.decoder_input(path)
            self.assertIsInstance(value,np.ndarray)
            self.assertEqual(value.shape,(60,80,3))
            self.assertEqual(value[0,0].tolist(),[30,20,10])
            supported=Path(folder)/'supported.png';supported.write_bytes(payload.getvalue())
            self.assertTrue(np.array_equal(fallback.decoder_input(supported),value))

    def test_decoded_exif_orientation_and_processing_profile_have_distinct_identities(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rotated.img';image=Image.new('RGB',(80,40),'white');exif=Image.Exif();exif[274]=6
            image.save(path,format='JPEG',exif=exif);image.close()
            self.assertEqual(fallback.decoder_input(path).shape[:2],(80,40))
        config=fallback.fallback_configuration({'configId':'baseline','modelFiles':{}})
        changed=fallback.fallback_configuration({'configId':'baseline','modelFiles':{}},{'maxTiles':4})
        self.assertNotEqual(config['featureSpaceId'],changed['featureSpaceId'])
        self.assertNotEqual(config['configId'],changed['configId'])

    def line(self,text='活动通知',score=.95,y=10,stage='mobile960'):
        return {'lineId':'line-1','text':text,'confidence':score,'polygon':[[10,y],[110,y],[110,y+20],[10,y+20]],'stage':stage}

    def test_small_text_and_empty_output_trigger_recovery_but_unverified_coverage_alone_does_not(self):
        normal={'recognitionLines':[self.line()],'combinedText':'活动通知','qualityFlags':['COVERAGE_UNVERIFIED']}
        self.assertEqual(fallback.fallback_reasons(normal,800,800),[])
        self.assertIn('SMALL_TEXT',fallback.fallback_reasons(normal,2000,2000))
        self.assertIn('EMPTY_OCR',fallback.fallback_reasons({'recognitionLines':[],'combinedText':''},800,800))

    def test_tile_budget_keeps_both_ends_and_reports_partial_processing(self):
        plan=fallback.plan_tiles(3000,2500,tile_size=1024,overlap=128,max_tiles=4)
        self.assertEqual(len(plan['tiles']),4)
        self.assertEqual(plan['coverageStatus'],'PARTIAL')
        self.assertEqual(plan['tiles'][0],[0,0,1024,1024])
        self.assertEqual(plan['tiles'][-1][-2:],[3000,2500])

    def test_overlap_duplicates_merge_but_the_same_text_at_other_locations_remains(self):
        base=self.line(score=.8);higher=self.line(score=.95,stage='mobile1600');other=self.line(y=80,stage='tile-1')
        result=fallback.merge_lines([base,higher,other])
        self.assertEqual(len(result['lines']),2)
        self.assertEqual(result['lines'][0]['confidence'],.95)
        self.assertEqual(set(result['lines'][0]['observedInStages']),{'mobile960','mobile1600'})
        conflict=fallback.merge_lines([base,self.line(text='活动通告',score=.96,stage='mobile1600')])
        self.assertEqual(len(conflict['lines']),1)
        self.assertEqual(len(conflict['conflicts']),1)

    def test_tile_coordinates_return_to_original_pixels(self):
        raw={'rec_texts':['活动'],'rec_scores':[.9],'rec_polys':[[[5,10],[50,10],[50,30],[5,30]]]}
        result=fallback.map_tile_result(raw,3000,2500,896,896)
        self.assertEqual(result['recognitionLines'][0]['polygon'][0],[901.,906.])
        self.assertFalse(result['noReuseClaim'])


if __name__=='__main__':unittest.main()
