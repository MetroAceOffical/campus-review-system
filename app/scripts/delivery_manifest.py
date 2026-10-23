"""Record or verify the candidate app sources, excluding private and generated files."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'docs/midterm/evidence/delivery-files.json'
EXCLUDED = {'node_modules', 'target', 'dist', '__pycache__', '.pytest_cache', '.vite'}


def inventory():
    entries = []
    for path in sorted((ROOT / 'app').rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or EXCLUDED.intersection(relative.parts):
            continue
        if relative.as_posix() == 'app/config/local.json' or relative.parts[:6] == ('app', 'backend', 'src', 'main', 'resources', 'static'):
            continue
        if path.suffix in {'.pyc', '.log'}:
            continue
        data = path.read_bytes()
        entries.append({'path': relative.as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    return entries


def main():
    entries = inventory()
    if sys.argv[1:] == ['--verify']:
        expected = json.loads(MANIFEST.read_text(encoding='utf-8'))['files']
        if entries != expected:
            old = {item['path']: item for item in expected}
            new = {item['path']: item for item in entries}
            changed = sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path))
            raise SystemExit('Candidate sources changed: ' + ', '.join(changed))
        print(f'Candidate app sources verified: {len(entries)} files')
    elif not sys.argv[1:]:
        MANIFEST.write_text(json.dumps({'schemaVersion': '1', 'scope': 'Candidate app source bytes; excludes local config, generated assets, environments and runtime data.', 'files': entries}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Candidate app manifest written: {len(entries)} files')
    else:
        raise SystemExit('Usage: delivery_manifest.py [--verify]')


if __name__ == '__main__':
    main()
