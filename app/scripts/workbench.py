"""Fixed CLI for dataset tasks. NDJSON stdout is the Java worker protocol."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/python'))
from campus_workbench.datasets import audit_dataset, read_dataset, write_dataset_version


def send(kind, value):
    print(json.dumps({'type': kind, 'data': value}, ensure_ascii=False, allow_nan=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='数据集质量评估与清洗')
    parser.add_argument('action', choices=('audit', 'clean'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--kind', choices=('NEWS', 'PAIRS'), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--mapping-json', default='{}')
    parser.add_argument('--options-json', default='{}')
    args = parser.parse_args(argv)
    if args.action == 'clean' and args.output is None:
        parser.error('clean需要--output新版本目录')
    mapping, options = json.loads(args.mapping_json), json.loads(args.options_json)
    if args.action == 'audit':
        data = read_dataset(args.input, args.kind, mapping=mapping)
        send('result', {'sourceSha256': data['sourceSha256'], 'columns': data['columns'],
                        'mapping': data['mapping'], 'audit': audit_dataset(data),
                        'preview': data['rows'][:20], 'issues': data['issues'][:100]})
    else:
        manifest = write_dataset_version(args.input, args.output, args.kind, options=options,
                                         mapping=mapping, on_event=lambda value: send('event', value))
        send('result', manifest)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        # No tracebacks or raw record contents in the machine protocol.
        send('error', {'code': 'DATASET_TASK_FAILED', 'message': str(error)})
        raise SystemExit(1)
