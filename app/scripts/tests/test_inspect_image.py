import importlib.util
from pathlib import Path
import tempfile
import unittest
from PIL import Image

class ImageValidationTest(unittest.TestCase):
    def test_decoded_type_static_frames_and_limits(self):
        spec=importlib.util.spec_from_file_location('inspect_image',Path(__file__).parents[1]/'inspect_image.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        temporary=Path(__file__).resolve().parents[3]/'runtime/test-tmp'
        temporary.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            root=Path(folder)
            image=root/'fake.jpg'
            image.write_text('<svg></svg>')
            with self.assertRaises(ValueError): module.inspect(image)
            Image.new('RGB',(20,10)).save(image,format='WEBP')
            self.assertEqual(module.inspect(image)['mimeType'],'image/webp')
            self.assertEqual(module.inspect(image)['width'],20)
            Image.new('RGB',(8001,1)).save(image,format='PNG')
            with self.assertRaises(ValueError): module.inspect(image)
            Image.new('RGB',(10,10),'red').save(image,format='WEBP',save_all=True,append_images=[Image.new('RGB',(10,10),'blue')],duration=100,loop=0)
            with self.assertRaises(ValueError): module.inspect(image)

if __name__=='__main__': unittest.main()
