"""Bounded batch imports and reproducible cleaning; never edits the input file.

Department values in a file describe provenance, not authorization. The caller
must bind dataset ownership to its authenticated workspace.
"""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import unicodedata


MAX_BYTES = 50 * 1024 * 1024
MAX_INTERNAL_BYTES = 512 * 1024 * 1024
MAX_ROWS = 100000
ALIASES = {
    'id': ('id', 'documentId', '编号', '文章编号'),
    'title': ('title', 'headline', '标题'),
    'text': ('text', 'body', 'content', '正文', '内容'),
    'department': ('department', '部门', '来源部门'),
    'url': ('url', 'source_url', '来源网址', '网址'),
    'published_at': ('published_at', 'publishedAt', '发布日期', '发布时间'),
    'source_institution': ('source_institution', 'institution', 'institutionName', '来源学校', '学校'),
    'sentence1': ('sentence1', 'text1', '句子1', '原句', '原文'),
    'sentence2': ('sentence2', 'text2', '句子2', '改写句', '改写'),
    'label': ('label', '标签'),
    'source_id': ('source_id', 'sourceId', '来源编号'),
    'group_id': ('group_id', 'groupId', '分组编号'),
    'label_origin': ('label_origin', 'labelOrigin', '标签来源'),
    'split': ('split', '数据分区'),
    'source_cluster_id': ('source_cluster_id', 'sourceClusterId'),
    'event_cluster_id': ('event_cluster_id', 'eventClusterId'),
}
PARTITION_FIELDS = ('split', 'source_cluster_id', 'event_cluster_id')
FIELDS = {
    'NEWS': ('id', 'title', 'text', 'department', 'url', 'published_at', 'source_institution', 'group_id') + PARTITION_FIELDS,
    'PAIRS': ('id', 'sentence1', 'sentence2', 'label', 'source_id', 'group_id', 'label_origin') + PARTITION_FIELDS,
}
REQUIRED = {'NEWS': ('text',), 'PAIRS': ('sentence1', 'sentence2', 'label')}
DEFAULT_OPTIONS = {'strip_html': True, 'normalize_whitespace': True,
                   'remove_duplicates': True, 'min_text_length': 1, 'max_text_length': 1000000}


def _key(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def _identity_text(value):
    # Exact identity after the explicitly selected cleaning rules. Removing all
    # whitespace would conflate meaningful word boundaries such as "a b"/"ab".
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _mapping(columns, kind, mapping):
    mapping = mapping or {}
    if not isinstance(mapping, dict) or set(mapping) - set(FIELDS[kind]):
        raise ValueError('INVALID_MAPPING: 字段映射包含不支持的标准字段')
    by_key = defaultdict(list)
    for name in columns:
        by_key[_key(name)].append(name)
    if any(len(names) > 1 for names in by_key.values()):
        raise ValueError('AMBIGUOUS_COLUMN: 存在同名列')
    result = {}
    for field in FIELDS[kind]:
        if field in mapping:
            column = mapping[field]
            if not isinstance(column, str) or column not in columns:
                raise ValueError(f'INVALID_MAPPING: {field}对应的列不存在')
            result[field] = column
            continue
        matches = [name for name in columns if _key(name) in {_key(a) for a in ALIASES[field]}]
        if len(matches) > 1:
            raise ValueError(f'AMBIGUOUS_COLUMN: 请为{field}选择一列')
        if matches:
            result[field] = matches[0]
    if len(set(result.values())) != len(result):
        raise ValueError('INVALID_MAPPING: 同一列不能映射为多个字段')
    for field in REQUIRED[kind]:
        if field not in result:
            raise ValueError(f'MISSING_COLUMN: 缺少{field}列')
    return result


def read_dataset(path, kind, mapping=None, max_bytes=None, max_rows=MAX_ROWS, internal=False):
    """Return mapped rows, recoverable parse issues, source identity and columns.

    Row numbers count nonblank records; lineNumber is the physical starting line.
    Malformed CSV cannot reliably recover record boundaries and fails the batch.
    """
    if kind not in FIELDS:
        raise ValueError('INVALID_KIND: 数据类型仅支持NEWS或PAIRS')
    if type(internal) is not bool:
        raise ValueError('INVALID_INTERNAL: 内部版本标记无效')
    if max_bytes is None:
        max_bytes = MAX_INTERNAL_BYTES if internal else MAX_BYTES
    if type(max_bytes) is not int or type(max_rows) is not int or max_bytes <= 0 or max_rows <= 0:
        raise ValueError('INVALID_LIMIT: 上限必须为正整数')
    path = Path(path)
    if path.suffix.lower() not in {'.csv', '.jsonl'}:
        raise ValueError('INVALID_FORMAT: 请上传CSV或JSONL')
    with path.open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('BYTE_LIMIT: 文件超过上传大小上限')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('ENCODING: 请使用UTF-8编码') from error
    entries, issues, columns = [], [], []
    total = 0

    def next_record():
        nonlocal total
        total += 1
        if total > max_rows:
            raise ValueError('ROW_LIMIT: 记录数超过导入上限')
        return total

    if path.suffix.lower() == '.csv':
        # A dedicated CLI process owns this temporary csv parser limit.
        old_limit = csv.field_size_limit()
        csv.field_size_limit(max_bytes)
        try:
            reader = csv.reader(io.StringIO(text, newline=''), strict=True)
            columns = next(reader, [])
            if not columns or any(not column.strip() for column in columns):
                raise ValueError('MISSING_COLUMN: CSV表头为空')
            previous_line = reader.line_num
            for values in reader:
                line = previous_line + 1
                previous_line = reader.line_num
                if not values:
                    continue
                row_number = next_record()
                if len(values) != len(columns):
                    issues.append({'rowNumber': row_number, 'lineNumber': line, 'code': 'COLUMN_COUNT'})
                else:
                    entries.append((row_number, line, dict(zip(columns, values))))
        except csv.Error as error:
            raise ValueError('INVALID_CSV: CSV引号或记录结构错误') from error
        finally:
            csv.field_size_limit(old_limit)
    else:
        # JSON strings can legally contain U+2028/U+2029/U+0085. Only physical
        # LF/CRLF delimits JSONL records; str.splitlines() would corrupt them.
        for line, value in enumerate(text.split('\n'), 1):
            if not value.strip():
                continue
            row_number = next_record()
            try:
                item = json.loads(value)
                if not isinstance(item, dict):
                    raise ValueError('记录须为对象')
            except (ValueError, RecursionError):
                issues.append({'rowNumber': row_number, 'lineNumber': line, 'code': 'INVALID_JSON_ROW'})
                continue
            for field in item:
                if field not in columns:
                    columns.append(field)
            entries.append((row_number, line, item))
    try:
        resolved = _mapping(columns, kind, mapping) if columns else {}
    except ValueError as error:
        error.details = {'columns': columns}
        raise
    if not columns and not issues and not internal:
        raise ValueError('EMPTY_DATASET: 文件没有记录或表头')
    rows = []
    for number, line, item in entries:
        row = {'_rowNumber': number, '_lineNumber': line}
        invalid = []
        for field in FIELDS[kind]:
            value = item.get(resolved.get(field), '')
            if isinstance(value, (dict, list, bool)):
                invalid.append(field)
                value = ''
            row[field] = '' if value is None else str(value)
        if not row['id'].strip():
            row['_missingFields'] = ['id']
        row['id'] = row['id'].strip() or f'row-{number}'
        if internal and '_provenance' in item:
            origins = item['_provenance']
            if not isinstance(origins, list) or len(origins) > MAX_ROWS or any(not isinstance(value, dict) for value in origins):
                invalid.append('_provenance')
            else:
                row['_provenance'] = [_compact_origin(value) for value in origins]
        if invalid:
            row['_invalidFields'] = invalid
        rows.append(row)
    return {'kind': kind, 'format': path.suffix.lower()[1:], 'sourceSha256': _digest(raw),
            'totalRows': total, 'columns': columns, 'mapping': resolved, 'rows': rows, 'issues': issues}


def _content_key(row, kind):
    if kind == 'NEWS':
        return (_identity_text(row['text']),)
    return tuple(sorted((_identity_text(row['sentence1']), _identity_text(row['sentence2']))))


def _compact_origin(origin):
    # The immutable source file and row reference retain original bodies. Do not
    # duplicate entire bodies at every cleaning generation.
    allowed = (set(ALIASES) - {'text', 'sentence1', 'sentence2'}) | {'rowNumber', 'lineNumber', 'inputSha256', 'generatedId'}
    return {key: value for key, value in origin.items() if key in allowed and
            (value is None or isinstance(value, (str, int, float, bool)))}


def _inherit_metadata(rows, kind):
    groups = defaultdict(list)
    for row in rows:
        groups[_content_key(row, kind)].append(row)
    conflicts = defaultdict(list)
    for members in groups.values():
        for field in PARTITION_FIELDS + ('group_id',):
            values = {row[field].strip() for row in members if row[field].strip()}
            if len(values) > 1:
                for row in members:
                    conflicts[row['_rowNumber']].append('PARTITION_CONFLICT' if field == 'split' else 'GROUP_CONFLICT')
            elif values:
                value = next(iter(values))
                for row in members:
                    row[field] = value
    return conflicts


def _diagnose(dataset):
    kind, rows = dataset['kind'], dataset['rows']
    reasons = {row['_rowNumber']: [] for row in rows}
    id_contents, pair_labels, partitions = defaultdict(set), defaultdict(set), defaultdict(set)
    for row in rows:
        out = reasons[row['_rowNumber']]
        if row.get('_invalidFields'):
            out.append('INVALID_VALUE')
        text_fields = ('text',) if kind == 'NEWS' else ('sentence1', 'sentence2')
        if any(not row[field].strip() for field in text_fields):
            out.append('EMPTY_TEXT')
        key = _content_key(row, kind)
        id_contents[row['id']].add(key)
        if row['split'].strip():
            partitions[key].add(row['split'].strip())
        if kind == 'PAIRS':
            if row['label'] not in {'0', '1', 0, 1}:
                out.append('INVALID_LABEL')
            else:
                pair_labels[key].add(str(row['label']))
                if str(row['label']) == '0' and key[0] == key[1]:
                    out.append('SELF_NEGATIVE')
    for row in rows:
        if len(id_contents[row['id']]) > 1:
            reasons[row['_rowNumber']].append('ID_CONFLICT')
        if kind == 'PAIRS' and len(pair_labels[_content_key(row, kind)]) > 1:
            reasons[row['_rowNumber']].append('LABEL_CONFLICT')
        if len(partitions[_content_key(row, kind)]) > 1:
            reasons[row['_rowNumber']].append('PARTITION_CONFLICT')
    return reasons


def _lengths(values):
    counts = Counter(values)
    ordered = sorted(values)
    n = len(ordered)
    def quantile(fraction):
        return ordered[round((n - 1) * fraction)] if n else None
    return {'count': n, 'min': min(values) if n else None, 'max': max(values) if n else None,
            'mean': sum(values) / n if n else None, 'p25': quantile(.25),
            'median': quantile(.5), 'p75': quantile(.75), 'p95': quantile(.95),
            'histogram': [{'length': length, 'count': counts[length]} for length in sorted(counts)]}


def audit_dataset(dataset):
    kind, rows, total = dataset['kind'], dataset['rows'], dataset['totalRows']
    reasons = _diagnose(dataset)
    parse_count = len(dataset['issues'])
    missing = {field: parse_count + sum(field in row.get('_missingFields', []) or (not row[field].strip() if isinstance(row[field], str)
                                      else row[field] is None) for row in rows) for field in FIELDS[kind]}
    counts = Counter(issue['code'] for issue in dataset['issues'])
    for values in reasons.values():
        counts.update(values)
    valid = [row for row in rows if not reasons[row['_rowNumber']]]
    duplicates = Counter(_content_key(row, kind) for row in valid)
    dates = Counter()
    for row in rows:
        value = row.get('published_at', '').strip()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            dates[parsed.strftime('%Y-%m')] += 1
        except ValueError:
            counts['INVALID_DATE'] += 1
    text_fields = ('title', 'text') if kind == 'NEWS' else ('sentence1', 'sentence2')
    return {'totalRows': total, 'parsedRows': len(rows), 'validRows': len(valid),
            'invalidRows': total - len(valid), 'missing': missing,
            'completeness': {field: (total - value) / total if total else None for field, value in missing.items()},
            'issueCounts': dict(sorted(counts.items())),
            'duplicateRows': sum(value - 1 for value in duplicates.values()),
            'duplicateClusterSizes': dict(sorted(Counter(duplicates.values()).items())),
            'lengths': {field: _lengths([len(row[field]) for row in rows]) for field in text_fields},
            'departmentDistribution': dict(sorted(Counter(row.get('department', '').strip() or '未填写' for row in rows).items())),
            'sourceDistribution': dict(sorted(Counter(row.get('source_institution', '').strip() or '未填写' for row in rows).items())),
            'dateDistribution': dict(sorted(dates.items())),
            'classDistribution': dict(sorted(Counter(str(row['label']) for row in valid).items())) if kind == 'PAIRS' else {},
            'labelOriginDistribution': dict(sorted(Counter(row.get('label_origin', '').strip() or '未填写' for row in rows).items())) if kind == 'PAIRS' else {}}


class _PlainText(HTMLParser):
    BLOCKS = {'p', 'div', 'li', 'br', 'section', 'article', 'h1', 'h2', 'h3', 'tr', 'blockquote'}
    HIDDEN = {'script', 'style', 'noscript'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _options(options):
    options = options or {}
    if not isinstance(options, dict) or set(options) - set(DEFAULT_OPTIONS):
        raise ValueError('INVALID_OPTION: 存在不支持的清洗参数')
    result = DEFAULT_OPTIONS | options
    for name in ('strip_html', 'normalize_whitespace', 'remove_duplicates'):
        if type(result[name]) is not bool:
            raise ValueError(f'INVALID_OPTION: {name}须为布尔值')
    lo, hi = result['min_text_length'], result['max_text_length']
    if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi <= 1000000:
        raise ValueError('INVALID_OPTION: 正文长度范围无效')
    return result


def _clean_text(value, options):
    if options['strip_html'] and re.search(r'</?[a-zA-Z][^>]*>', value):
        parser = _PlainText()
        parser.feed(value)
        parser.close()
        value = ''.join(parser.parts)
    if options['normalize_whitespace']:
        value = value.replace('\r\n', '\n').replace('\r', '\n')
        value = '\n'.join(line for line in (re.sub(r'[^\S\n]+', ' ', line).strip()
                                           for line in value.split('\n')) if line)
    return value


def clean_dataset(dataset, options=None, on_event=None):
    options = _options(options)
    kind, total = dataset['kind'], dataset['totalRows']
    rows, changes = [], []
    fields = ('title', 'text') if kind == 'NEWS' else ('sentence1', 'sentence2')
    for original in dataset['rows']:
        row = dict(original)
        for field in fields:
            row[field] = _clean_text(row[field], options)
        rows.append(row)
    metadata_conflicts = _inherit_metadata(rows, kind)
    prepared = dict(dataset, rows=rows)
    reasons = _diagnose(prepared)
    quarantine = [{'rowNumber': issue['rowNumber'], 'lineNumber': issue['lineNumber'],
                   'reasons': [issue['code']], 'record': None} for issue in dataset['issues']]
    kept, seen, origin_keys = [], {}, {}
    duplicates, processed = 0, len(quarantine)
    def emit():
        if on_event:
            on_event({'stage': 'CLEANING', 'processed': processed, 'total': total,
                      'retained': len(kept), 'quarantined': len(quarantine), 'duplicates': duplicates})
    emit()
    for original, row in zip(dataset['rows'], rows):
        problems = list(reasons[row['_rowNumber']]) + metadata_conflicts[row['_rowNumber']]
        lengths = [len(row[field]) for field in (('text',) if kind == 'NEWS' else fields)]
        if any(length < options['min_text_length'] or length > options['max_text_length'] for length in lengths):
            problems.append('TEXT_LENGTH')
        identity = {'rowNumber': row['_rowNumber'], 'lineNumber': row['_lineNumber']}
        if problems:
            quarantine.append(dict(identity, reasons=sorted(set(problems)), record=original))
        else:
            if kind == 'PAIRS':
                row['label'] = int(row['label'])
            provenance = _compact_origin({**{key: original[key] for key in original if not key.startswith('_')},
                **identity, 'inputSha256': dataset['sourceSha256'], 'generatedId': 'id' in original.get('_missingFields', [])})
            row['_provenance'] = [dict(value) for value in original.get('_provenance') or [provenance]]
            row.pop('_missingFields', None)
            key = _content_key(row, kind)
            if options['remove_duplicates'] and key in seen:
                target = kept[seen[key]]['_provenance']
                known = origin_keys[seen[key]]
                for origin in row['_provenance']:
                    if _json(origin) not in known:
                        target.append(origin);known.add(_json(origin))
                duplicates += 1
                changes.append(dict(identity, action='DUPLICATE', retainedId=kept[seen[key]]['id']))
            else:
                seen[key] = len(kept)
                origin_keys[len(kept)] = {_json(value) for value in row['_provenance']}
                kept.append(row)
                changed = [field for field in fields if original[field] != row[field]]
                changes.append(dict(identity, action='RETAINED', changedFields=changed, retainedId=row['id']))
        processed += 1
        if processed % max(1, total // 100) == 0 or processed == total:
            emit()
    after = audit_dataset(dict(dataset, rows=kept, issues=[], totalRows=len(kept)))
    return {'kind': kind, 'options': options, 'inputRows': total, 'outputRows': len(kept),
            'duplicateRows': duplicates, 'rows': kept, 'quarantine': quarantine,
            'changes': changes, 'before': audit_dataset(dataset), 'after': after}


def write_dataset_version(input_path, output_dir, kind, options=None, mapping=None, on_event=None, internal=False):
    """Create an exclusive version directory; manifest is written last.

    A failed/interrupted directory is retained without a COMPLETED manifest.
    Callers retry with a new version identity, never overwrite an old run.
    """
    options = _options(options)
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError('VERSION_EXISTS: 版本目录已存在')
    data = read_dataset(input_path, kind, mapping=mapping, internal=internal)
    events = []
    def event(value):
        value = dict(value, sequence=len(events) + 1)
        events.append(value)
        if on_event:
            on_event(value)
    event({'stage': 'PARSED', 'processed': data['totalRows'], 'total': data['totalRows'],
           'parseErrors': len(data['issues'])})
    cleaned = clean_dataset(data, options, on_event=event)
    output.mkdir(parents=True, exist_ok=False)
    payloads = {
        'corpus.jsonl': ''.join(_json(row) + '\n' for row in cleaned['rows']),
        'quarantine.jsonl': ''.join(_json(row) + '\n' for row in cleaned['quarantine']),
        'changes.jsonl': ''.join(_json(row) + '\n' for row in cleaned['changes']),
        'audit.json': _json(cleaned['before']) + '\n',
        'cleaning.json': _json({key: value for key, value in cleaned.items()
                                if key not in {'rows', 'quarantine', 'changes'}}) + '\n',
    }
    event({'stage': 'SAVING', 'processed': data['totalRows'], 'total': data['totalRows']})
    # COMPLETED means this data version is saved; it never means model training.
    for name, content in payloads.items():
        (output / name).write_bytes(content.encode('utf-8'))
    completed = {'stage': 'COMPLETED', 'processed': data['totalRows'], 'total': data['totalRows'],
                 'outputRows': cleaned['outputRows'], 'sequence': len(events) + 1}
    events.append(completed)
    payloads['events.jsonl'] = ''.join(_json(value) + '\n' for value in events)
    (output / 'events.jsonl').write_bytes(payloads['events.jsonl'].encode('utf-8'))
    manifest = {'schemaVersion': 1, 'processorVersion': '2', 'taskType': 'DATASET_CLEANING', 'status': 'COMPLETED', 'kind': kind,
                'inputSha256': data['sourceSha256'], 'inputRows': data['totalRows'],
                'outputRows': cleaned['outputRows'], 'quarantineRows': len(cleaned['quarantine']),
                'duplicateRows': cleaned['duplicateRows'], 'mapping': data['mapping'], 'options': options,
                'artifacts': {name: _digest(content.encode('utf-8')) for name, content in payloads.items()}}
    (output / 'manifest.json').write_bytes((_json(manifest) + '\n').encode('utf-8'))
    if on_event:
        on_event(completed)
    return manifest
