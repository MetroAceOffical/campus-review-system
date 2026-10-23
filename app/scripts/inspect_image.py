"""Decode a single upload with existing Pillow; no model load and no file mutations."""
import json
from pathlib import Path
import sys
from PIL import Image, UnidentifiedImageError

def inspect(path, max_bytes=10485760, max_pixels=20000000, max_side=8000):
    path=Path(path)
    if path.stat().st_size>max_bytes: raise ValueError('UPLOAD_TOO_LARGE')
    try:
        with Image.open(path) as image:
            if image.format not in ('JPEG','PNG','WEBP') or getattr(image,'n_frames',1)!=1:
                raise ValueError('UNSUPPORTED_IMAGE_TYPE')
            if image.width>max_side or image.height>max_side or image.width*image.height>max_pixels:
                raise ValueError('IMAGE_DIMENSIONS_TOO_LARGE')
            image.load()
            return {'mimeType':Image.MIME[image.format],'width':image.width,'height':image.height}
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise ValueError('UNSUPPORTED_IMAGE_TYPE') from error

if __name__=='__main__':
    try:
        result=inspect(sys.argv[1],*(int(value) for value in sys.argv[2:]))
        print(json.dumps(result))
    except ValueError as error:
        print(json.dumps({'error':str(error)}))
        sys.exit(1)
