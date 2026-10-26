"""Bounded HTTP ranges avoid buffering multi-GiB responses in network intermediaries."""
import hashlib
import time
from pathlib import Path
import requests


def download_ranges(url, target, size, expected_sha, chunk_size=32*1024*1024):
    target = Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        candidate = target
    else:
        candidate = target.with_suffix(target.suffix+'.part')
        candidate.touch(exist_ok=True)
        if candidate.stat().st_size > size:
            raise ValueError('Partial download larger than source')
        with requests.Session() as session:
            while candidate.stat().st_size < size:
                start = candidate.stat().st_size
                end = min(start+chunk_size,size)-1
                for attempt in range(3):
                    try:
                        with session.get(url,headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=(20,90)) as response:
                            response.raise_for_status()
                            if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                                raise ValueError('Server did not honor exact bounded byte range')
                            data = response.content
                            if len(data) != end-start+1:
                                raise ValueError('Incomplete bounded range')
                        with candidate.open('ab') as output:
                            output.write(data)
                        break
                    except requests.RequestException:
                        if attempt == 2:
                            raise
                        time.sleep(2**(attempt+1))
    with candidate.open('rb') as stream:
        sha = hashlib.file_digest(stream,'sha256').hexdigest()
    if candidate.stat().st_size != size or sha != expected_sha:
        raise ValueError('Downloaded asset size/SHA does not match immutable source')
    if candidate != target:
        candidate.replace(target)
