import io
import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_images as collection


class ImageCollectionTests(unittest.TestCase):
    def test_public_school_images_are_deduplicated_and_capped_by_event(self):
        row={'documentId':'a','eventClusterId':'event','sourceClusterId':'source','institutionName':'school','url':'https://news.school.edu.cn/a.html',
             'images':['https://news.school.edu.cn/a.jpg','https://news.school.edu.cn/b.jpg','https://news.school.edu.cn/c.jpg',
                       'https://news.school.edu.cn.evil.example/private.jpg','http://127.0.0.1/local.jpg','https://user:pass@news.school.edu.cn/private.jpg']}
        rows=collection.choose_candidates([row,{**row,'documentId':'b'}],per_event=2)
        self.assertEqual(len(rows),2)
        self.assertEqual(len({item['imageUrl'] for item in rows}),2)
        self.assertTrue(all(item['eventClusterId']=='event' for item in rows))

    def test_small_decorations_are_not_counted_as_full_source_images(self):
        def payload(size):
            stream=io.BytesIO();Image.new('RGB',size,'white').save(stream,format='PNG');return stream.getvalue()
        with self.assertRaises(ValueError):collection.image_metadata(payload((40,40)))
        metadata=collection.image_metadata(payload((640,480)))
        self.assertEqual(metadata['width'],640)
        self.assertEqual(len(metadata['pixelSha256']),64)


if __name__=='__main__':unittest.main()
