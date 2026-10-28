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
    parser.add_argument('action', choices=('audit', 'clean','compose'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--kind', choices=('NEWS', 'PAIRS'), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--mapping-json', default='{}')
    parser.add_argument('--options-json', default='{}')
    parser.add_argument('--config-file', type=Path)
    args = parser.parse_args(argv)
    if args.action in ('clean','compose') and args.output is None:
        parser.error('clean需要--output新版本目录')
    mapping, options = json.loads(args.mapping_json), json.loads(args.options_json)
    internal = False
    if args.config_file:
        with args.config_file.open('rb') as stream:
            config_bytes = stream.read(20001)
        if len(config_bytes) > 20000:
            raise ValueError('INVALID_CONFIG: 任务配置过大')
        config = json.loads(config_bytes.decode('utf-8-sig'))
        if not isinstance(config, dict) or set(config) - {'mapping', 'options', 'internalVersion'}:
            raise ValueError('INVALID_CONFIG: 任务配置无效')
        mapping, options = config.get('mapping', {}), config.get('options', {})
        internal = config.get('internalVersion', False)
    if args.action == 'compose':
        from campus_workbench.composition import compose
        send('result',compose(args.input,args.output,args.kind,lambda value:send('event',value)))
    elif args.action == 'audit':
        data = read_dataset(args.input, args.kind, mapping=mapping, internal=internal)
        send('result', {'sourceSha256': data['sourceSha256'], 'columns': data['columns'],
                        'mapping': data['mapping'], 'audit': audit_dataset(data),
                        'preview': [{key: value[:1000] if isinstance(value, str) else value
                                     for key, value in row.items()} for row in data['rows'][:20]],
                        'issues': data['issues'][:100]})
    else:
        manifest = write_dataset_version(args.input, args.output, args.kind, options=options,
                                         mapping=mapping, on_event=lambda value: send('event', value), internal=internal)
        send('result', manifest)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        # No tracebacks or raw record contents in the machine protocol.
        send('error', {'code': 'DATASET_TASK_FAILED', 'message': str(error),
                       'details': getattr(error, 'details', {})})
        raise SystemExit(1)
