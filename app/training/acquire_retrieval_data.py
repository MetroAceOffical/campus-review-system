"""Fetch only the three required T2Ranking training files, pinned and hash-checked."""
import hashlib
import json
import time
from pathlib import Path
import requests
from download_assets import download_ranges

ROOT = Path(__file__).resolve().parents[2]
REVISION = '2a369a430a70979223f1b9a41b1919774d46b432'


def main():
    meta = json.loads((ROOT/'runtime/experiments/final-design-20261026/t2ranking-source.json').read_text(encoding='utf-8'))
    if meta['sha'] != REVISION:
        raise ValueError('Dataset revision changed')
    folder = ROOT/'runtime/datasets/public/t2ranking'/REVISION
    folder.mkdir(parents=True,exist_ok=True)
    manifest = {'repo':'THUIR/T2Ranking','revision':REVISION,'license':'Apache-2.0 per official repository README',
                'taskType':'RETRIEVAL_RELEVANCE','status':'downloading_not_training','files':[]}
    for name in ['README.md','data/queries.train.tsv','data/qrels.train.tsv','data/collection.tsv']:
        item = next(row for row in meta['siblings'] if row['rfilename']==name)
        path = folder/Path(name).name
        partial = path.with_suffix(path.suffix+'.part')
        if item['size'] > 100*1024*1024 and item.get('lfs'):
            download_ranges(f'https://huggingface.co/datasets/THUIR/T2Ranking/resolve/{REVISION}/{name}?download=true',path,item['size'],item['lfs']['sha256'])
        if not path.exists():
            for attempt in range(3):
                offset = partial.stat().st_size if partial.exists() else 0
                headers = {'Range':f'bytes={offset}-'} if offset else {}
                try:
                    with requests.get(f'https://huggingface.co/datasets/THUIR/T2Ranking/resolve/{REVISION}/{name}',headers=headers,stream=True,timeout=(20,120)) as response:
                        response.raise_for_status()
                        resume = offset and response.status_code == 206 and response.headers.get('Content-Range','').startswith(f'bytes {offset}-')
                        with partial.open('ab' if resume else 'wb') as out:
                            for chunk in response.iter_content(2**20):
                                out.write(chunk)
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(2**(attempt+1))
            if partial.stat().st_size != item['size']:
                raise ValueError('Data size mismatch')
            with partial.open('rb') as stream:
                sha = hashlib.file_digest(stream,'sha256').hexdigest()
            expected = item.get('lfs',{}).get('sha256') if item.get('lfs') else None
            if expected and sha != expected:
                raise ValueError('Official data SHA mismatch')
            partial.replace(path)
        with path.open('rb') as stream:
            sha = hashlib.file_digest(stream,'sha256').hexdigest()
        expected = item.get('lfs',{}).get('sha256') if item.get('lfs') else None
        if path.stat().st_size != item['size'] or expected and sha != expected:
            raise ValueError('Existing downloaded data changed')
        manifest['files'].append({'file':path.name,'bytes':path.stat().st_size,'sha256':sha,'officialSha256':expected})
        (folder/'acquisition.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(manifest['files'][-1]),flush=True)
    manifest['status'] = 'download_verified_not_trained'
    (folder/'acquisition.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
