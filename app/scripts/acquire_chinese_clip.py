"""User-approved, pinned official Chinese-CLIP download; no package installs."""
import hashlib
import json
from pathlib import Path
import sys
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/training'))
from download_assets import download_ranges

REVISION = '36e679e65c2a2fead755ae21162091293ad37834'
REPO = 'OFA-Sys/chinese-clip-vit-base-patch16'


def main():
    response = requests.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true', timeout=40)
    response.raise_for_status(); meta = response.json()
    if meta['sha'] != REVISION:
        raise ValueError('Official revision mismatch')
    folder = ROOT / 'runtime/models/final/chinese-clip-vit-base-patch16' / REVISION
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for name in ('README.md', 'config.json', 'preprocessor_config.json', 'vocab.txt', 'pytorch_model.bin'):
        item = next(row for row in meta['siblings'] if row['rfilename'] == name)
        path = folder / name; url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
        if item.get('lfs'):
            download_ranges(url, path, item['size'], item['lfs']['sha256'])
        elif not path.exists():
            r = requests.get(url, timeout=60); r.raise_for_status(); path.write_bytes(r.content)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != item['size']:
            raise ValueError('Official file size mismatch')
        files.append({'file': name, 'sha256': digest, 'bytes': item['size']})
        print(name, 'verified', flush=True)
    (folder / 'acquisition.json').write_text(json.dumps({'repo': REPO, 'revision': REVISION, 'status': 'download_verified_not_evaluated', 'files': files, 'licenseReference': 'Official model card README.md; no SPDX in hub metadata'}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':main()
