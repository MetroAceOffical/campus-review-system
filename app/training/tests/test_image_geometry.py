import io
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from campus_detection import image_geometry as geometry


def photo(seed,size=(640,480)):
    rng=np.random.default_rng(seed)
    image=Image.fromarray(rng.integers(30,225,(*size[::-1],3),dtype=np.uint8),'RGB')
    draw=ImageDraw.Draw(image)
    for i in range(170):
        x,y=map(int,rng.integers([0,0],[size[0]-30,size[1]-30]))
        draw.rectangle((x,y,x+int(rng.integers(10,35)),y+int(rng.integers(10,35))),outline=tuple(map(int,rng.integers(0,256,3))),width=3)
        draw.text((x,y),str(i),fill='white')
    return image


def encoded(image,kind='PNG',**options):
    stream=io.BytesIO();image.save(stream,format=kind,**options);return stream.getvalue()


class ImageGeometryTests(unittest.TestCase):
    def test_rescaled_homography_maps_original_pixel_centers(self):
        matrix=geometry.original_homography(np.eye(3),(.5,.5),(1.,1.))
        mapped=matrix@np.array([100.,100.,1.])
        self.assertTrue(np.allclose(mapped,[49.75,49.75,1.]))

    def test_compressed_resized_photo_has_bilateral_spatial_support(self):
        image=photo(12);query=image.resize((480,360))
        result=geometry.verify_images(encoded(query,'JPEG',quality=82),encoded(image))
        self.assertTrue(result['acceptedCorrespondence'])
        self.assertEqual(result['scope'],'WHOLE_IMAGE')
        self.assertGreater(result['querySpatialCoverage'],.35)
        self.assertGreater(result['sourceSpatialCoverage'],.35)
        self.assertGreaterEqual(result['inliers'],10)

    def test_crop_reports_local_source_region_in_original_pixel_coordinates(self):
        image=photo(41);query=image.crop((170,120,390,300))
        result=geometry.verify_images(encoded(query),encoded(image))
        self.assertTrue(result['acceptedCorrespondence'])
        self.assertEqual(result['scope'],'LOCAL_REGION')
        self.assertLess(result['sourceSpatialCoverage'],.35)
        for x,y in result['sourceRegion']:
            self.assertTrue(160<=x<=400 and 110<=y<=310)

    def test_a_large_crop_still_cannot_claim_the_whole_source_image(self):
        image=photo(19);query=image.crop((80,60,560,420))
        result=geometry.verify_images(encoded(query),encoded(image))
        self.assertTrue(result['acceptedCorrespondence'])
        self.assertEqual(result['scope'],'LOCAL_REGION')

    def test_shared_corner_logo_does_not_accept_different_full_images(self):
        left,right=photo(1),photo(2);logo=photo(33,(90,90))
        left.paste(logo,(5,5));right.paste(logo,(5,5))
        result=geometry.verify_images(encoded(left),encoded(right))
        self.assertFalse(result['acceptedCorrespondence'])
        self.assertNotEqual(result['scope'],'WHOLE_IMAGE')

    def test_low_texture_is_insufficient_and_perceptual_hash_alone_cannot_accept(self):
        left=encoded(Image.new('RGB',(200,200),'white'))
        right=encoded(Image.new('RGB',(200,200),'gray'))
        result=geometry.verify_images(left,right)
        self.assertFalse(result['acceptedCorrespondence'])
        self.assertEqual(result['status'],'INSUFFICIENT_EVIDENCE')
        self.assertIn('LOW_TEXTURE',result['qualityFlags'])
        same=geometry.verify_images(left,left)
        self.assertEqual(same['identityBasis'],'FILE_SHA256')
        self.assertTrue(same['acceptedCorrespondence'])


if __name__=='__main__':unittest.main()
