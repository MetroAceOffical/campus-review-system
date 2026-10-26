import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_ocr_materials as materials


class OcrMaterialsTests(unittest.TestCase):
    def test_every_known_line_is_rendered_inside_the_original_and_scaled_bounds(self):
        font=Path('C:/Windows/Fonts/msyh.ttc')
        self.assertTrue(font.is_file())
        for index in [0,4,29]:
            image,lines=materials.render_notice(index,font)
            try:
                self.assertGreaterEqual(len(lines),15)
                for kind in ['original','downscale_jpeg','blur','low_contrast']:
                    query,truth=materials.transform_notice(image,lines,kind)
                    try:
                        self.assertEqual([row['text'] for row in truth],[row['text'] for row in lines])
                        for row in truth:
                            for x,y in row['polygon']:self.assertTrue(0<=x<=query.width and 0<=y<=query.height)
                        self.assertTrue(any('合成' in row['text'] for row in truth))
                    finally:query.close()
            finally:image.close()


if __name__=='__main__':unittest.main()
