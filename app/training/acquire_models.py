"""Download pinned public model data; never execute repository code."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import requests
from download_assets import download_ranges

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', choices=['BAAI/bge-base-zh-v1.5','Qwen/Qwen2.5-3B-Instruct'])
    args = parser.parse_args()
    session = requests.Session()
    session.headers['User-Agent'] = 'campus-review-research/1.0'
    meta = session.get('https://huggingface.co/api/models/'+args.repo+'?blobs=true',timeout=45)
    meta.raise_for_status()
    meta = meta.json()
    folder = ROOT/'runtime/models/final'/args.repo.split('/')[-1]/meta['sha']
    folder.mkdir(parents=True,exist_ok=True)
    has_safe = any(item['rfilename'].endswith('.safetensors') for item in meta['siblings'])
    allow = {'config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','generation_config.json','merges.txt','vocab.json','model.safetensors.index.json','README.md','LICENSE','LICENSE.txt'}
    selected = [item for item in meta['siblings'] if item['rfilename'] in allow or item['rfilename'].endswith('.safetensors') or (not has_safe and item['rfilename']=='pytorch_model.bin')]
    manifest = {'repo':args.repo,'revision':meta['sha'],'status':'downloading','files':[]}
    destination = folder/'acquisition.json'
    destination.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for item in selected:
        name = item['rfilename']
        path = folder/name
        expected = item.get('lfs',{}).get('sha256')
        expected_bytes = item.get('size')
        if expected_bytes > 100*1024*1024 and expected:
            download_ranges(f'https://huggingface.co/{args.repo}/resolve/{meta["sha"]}/{name}?download=true',path,expected_bytes,expected)
        if path.is_file():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream,'sha256').hexdigest()
            if path.stat().st_size != expected_bytes or (expected and digest != expected):
                raise ValueError('Existing model asset changed: '+name)
        else:
            url = f'https://huggingface.co/{args.repo}/resolve/{meta["sha"]}/{name}'
            partial = path.with_suffix(path.suffix+'.part')
            for attempt in range(3):
                try:
                    with session.get(url,stream=True,timeout=(20,120)) as response, partial.open('wb') as out:
                        response.raise_for_status()
                        for chunk in response.iter_content(2**20):
                            out.write(chunk)
                    with partial.open('rb') as stream:
                        digest = hashlib.file_digest(stream,'sha256').hexdigest()
                    if partial.stat().st_size != expected_bytes or (expected and digest != expected):
                        raise ValueError('Downloaded model hash/size mismatch')
                    partial.replace(path)
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(2**(attempt+1))
        manifest['files'].append({'file':name,'bytes':path.stat().st_size,'sha256':digest,'officialSha256':expected})
        destination.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps({'repo':args.repo,'file':name,'bytes':path.stat().st_size,'verified':True}),flush=True)
    manifest['status'] = 'download_verified_not_trained'
    destination.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'modelPath':str(folder),'status':manifest['status']}),flush=True)


if __name__ == '__main__':
    main()
