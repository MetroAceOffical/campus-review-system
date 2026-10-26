import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_image_protocol as protocol


class ImageProtocolTests(unittest.TestCase):
    def test_event_and_near_image_transitive_family_never_crosses_splits(self):
        rows=[{'imageId':'a','eventClusterId':'event1','pixelSha256':'p1','phash':'0000000000000000'},
              {'imageId':'b','eventClusterId':'event2','pixelSha256':'p2','phash':'0000000000000001'},
              {'imageId':'c','eventClusterId':'event2','pixelSha256':'p3','phash':'ffffffffffffffff'},
              {'imageId':'d','eventClusterId':'event3','pixelSha256':'p4','phash':'aaaaaaaaaaaaaaaa'}]
        families=protocol.image_families(rows)
        self.assertEqual(families['a'],families['c'])
        self.assertNotEqual(families['a'],families['d'])
        partitions=protocol.family_splits(families)
        self.assertEqual(partitions['a'],partitions['c'])
        self.assertEqual(set(partitions.values()),{'development','final'})

    def test_crop_and_resize_have_known_original_pixel_transforms(self):
        image=Image.new('RGB',(600,400),'blue');before=image.tobytes()
        variants={kind:(query,mapping) for kind,query,mapping in protocol.controlled_variants(image)}
        self.assertEqual(len(variants),6)
        crop,mapping=variants['crop']
        self.assertEqual(crop.size,(360,240))
        self.assertEqual(mapping,[[1.,0.,120.],[0.,1.,80.],[0.,0.,1.]])
        resized,mapping=variants['resize']
        self.assertEqual(resized.size,(360,240))
        self.assertAlmostEqual(mapping[0][0],600/360)
        self.assertAlmostEqual(mapping[0][2],.5*(600/360)-.5)
        self.assertEqual(image.tobytes(),before)


if __name__=='__main__':unittest.main()
