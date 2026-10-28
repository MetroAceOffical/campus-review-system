import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys


class WorkbenchDatasetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.find_spec('campus_workbench')
        self.assertIsNotNone(spec, '批量数据处理内核尚未实现')
        from campus_workbench import datasets
        self.api = datasets

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        return path

    def pairs(self, rows):
        return self.api.read_dataset(self.write('pairs.jsonl', '\n'.join(
            json.dumps(row, ensure_ascii=False) for row in rows)), 'PAIRS')

    def test_bom_multiline_csv_aliases_and_original_bytes(self):
        path = self.root / 'news.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['编号', '标题', '正文', '来源学校', '来源网址', '发布日期', '部门'])
            writer.writerow(['n1', '课程新闻', '第一段，含逗号\n第二段"引号"', '其他高校',
                             'https://example.edu/news/1', '2026-10-20', '校新闻中心'])
        before = path.read_bytes()
        data = self.api.read_dataset(path, 'NEWS')
        self.assertEqual(data['totalRows'], 1)
        self.assertEqual(data['rows'][0]['text'], '第一段，含逗号\n第二段"引号"')
        self.assertEqual(data['rows'][0]['source_institution'], '其他高校')
        self.assertEqual(data['rows'][0]['department'], '校新闻中心')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(data['sourceSha256'], hashlib.sha256(before).hexdigest())

    def test_mapping_and_ambiguous_columns_need_explicit_selection(self):
        path = self.write('custom.csv', 'headline,body,content\n标题,原正文,另一个正文\n')
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS_COLUMN'):
            self.api.read_dataset(path, 'NEWS')
        data = self.api.read_dataset(path, 'NEWS', mapping={'title': 'headline', 'text': 'content'})
        self.assertEqual(data['rows'][0]['title'], '标题')
        self.assertEqual(data['rows'][0]['text'], '另一个正文')
        with self.assertRaisesRegex(ValueError, 'MAPPING'):
            self.api.read_dataset(path, 'NEWS', mapping={'text': 'missing'})

    def test_bad_json_lines_and_wrong_types_are_counted_not_dropped(self):
        path = self.write('bad.jsonl', '\n'.join([
            '{"text":"可用正文","published_at":"2026-10-20"}', '{bad', '[]',
            '{"text":"","published_at":"not-a-date"}', '{"text":{"nested":"bad"}}']))
        data = self.api.read_dataset(path, 'NEWS')
        report = self.api.audit_dataset(data)
        self.assertEqual(report['totalRows'], 5)
        self.assertEqual(report['validRows'], 1)
        self.assertEqual(report['invalidRows'], 4)
        self.assertEqual(len(data['issues']), 2)
        self.assertEqual([x['lineNumber'] for x in data['issues']], [2, 3])
        self.assertEqual(report['missing']['text'], 4)
        self.assertEqual(report['dateDistribution'], {'2026-10': 1})
        cleaned = self.api.clean_dataset(data)
        self.assertEqual(len(cleaned['quarantine']), 4)
        self.assertEqual(cleaned['rows'][0]['text'], '可用正文')

    def test_encoding_limits_missing_headers_and_malformed_csv_fail_explicitly(self):
        cases = [('no.csv', 'title\n新闻\n', 'MISSING_COLUMN'),
                 ('duplicate.csv', 'text,正文\na,b\n', 'AMBIGUOUS_COLUMN'),
                 ('broken.csv', 'text\n"没有关闭\n正文', 'INVALID_CSV')]
        for name, content, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                self.api.read_dataset(self.write(name, content), 'NEWS')
        path = self.write('limit.jsonl', '{"text":"一"}\n{"text":"二"}')
        with self.assertRaisesRegex(ValueError, 'ROW_LIMIT'):
            self.api.read_dataset(path, 'NEWS', max_rows=1)
        with self.assertRaisesRegex(ValueError, 'BYTE_LIMIT'):
            self.api.read_dataset(path, 'NEWS', max_bytes=1)
        path.write_bytes(b'\xff\xfe\x81')
        with self.assertRaisesRegex(ValueError, 'ENCODING'):
            self.api.read_dataset(path, 'NEWS')

    def test_reverse_pair_conflict_self_negative_and_invalid_label_quarantine(self):
        data = self.pairs([
            {'sentence1': '甲内容', 'sentence2': '乙内容', 'label': 1},
            {'sentence1': '乙内容', 'sentence2': '甲内容', 'label': 0},
            {'sentence1': '同一句', 'sentence2': '同一句', 'label': 0},
            {'sentence1': '内容1', 'sentence2': '内容2', 'label': True},
            {'sentence1': '校新闻', 'sentence2': '新闻稿', 'label': 1, 'label_origin': 'human_verified'},
        ])
        report = self.api.audit_dataset(data)
        self.assertEqual(report['issueCounts']['LABEL_CONFLICT'], 2)
        self.assertEqual(report['issueCounts']['SELF_NEGATIVE'], 1)
        self.assertEqual(report['issueCounts']['INVALID_LABEL'], 1)
        result = self.api.clean_dataset(data)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['label'], 1)
        self.assertEqual(result['rows'][0]['label_origin'], 'human_verified')
        self.assertEqual(len(result['quarantine']), 4)
        self.assertEqual(result['after']['classDistribution'], {'1': 1})

    def test_html_extracts_once_and_duplicate_merge_preserves_origins(self):
        path = self.write('news.jsonl', '\n'.join(json.dumps(row, ensure_ascii=False) for row in [
            {'id': 'a', 'text': '<div><p>开学 &amp; 活动</p><div><p>第二段</p></div></div><script>危险</script>',
             'url': 'https://a.edu/1', 'source_institution': '甲校'},
            {'id': 'b', 'text': '开学 & 活动\n第二段', 'url': 'https://b.edu/2', 'source_institution': '乙校'},
            {'id': 'c', 'text': '数量 1 < 2，保留比较符号'},
            {'id': 'd', 'text': '   '},
        ]))
        events = []
        result = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'), on_event=events.append)
        self.assertEqual(len(result['rows']), 2)
        self.assertEqual(result['rows'][0]['text'], '开学 & 活动\n第二段')
        self.assertEqual(result['rows'][1]['text'], '数量 1 < 2，保留比较符号')
        origins = result['rows'][0]['_provenance']
        self.assertEqual({x['url'] for x in origins}, {'https://a.edu/1', 'https://b.edu/2'})
        self.assertEqual({x['source_institution'] for x in origins}, {'甲校', '乙校'})
        self.assertEqual(result['duplicateRows'], 1)
        self.assertEqual(len(result['quarantine']), 1)
        self.assertEqual(result['inputRows'], result['outputRows'] + result['duplicateRows'] + len(result['quarantine']))
        self.assertEqual(events[-1]['processed'], 4)
        self.assertEqual(events[-1]['total'], 4)
        self.assertEqual([e['processed'] for e in events], sorted(e['processed'] for e in events))

    def test_duplicate_ids_with_different_content_are_not_overwritten(self):
        path = self.write('ids.jsonl', '{"id":"same","text":"第一篇"}\n{"id":"same","text":"另一篇"}')
        result = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'))
        self.assertEqual(result['rows'], [])
        self.assertEqual(len(result['quarantine']), 2)
        self.assertTrue(all('ID_CONFLICT' in row['reasons'] for row in result['quarantine']))

    def test_quality_metrics_use_all_rows_as_denominator_and_lengths_in_codepoints(self):
        data = self.api.read_dataset(self.write('metrics.jsonl',
            '{"text":"中😀文","title":"标题","department":"新闻中心","source_institution":"南传"}\n'
            '{"text":"","title":"","department":"","source_institution":""}'), 'NEWS')
        audit = self.api.audit_dataset(data)
        self.assertEqual(audit['missing']['text'], 1)
        self.assertEqual(audit['completeness']['text'], .5)
        self.assertEqual(audit['lengths']['text']['max'], 3)
        self.assertEqual(audit['departmentDistribution']['新闻中心'], 1)
        self.assertEqual(audit['sourceDistribution']['南传'], 1)

    def test_versions_are_reproducible_immutable_and_hash_verifiable(self):
        path = self.write('source.jsonl', '{"text":"真实正文","url":"https://news.edu/1"}\n{broken')
        before = path.read_bytes()
        first = self.api.write_dataset_version(path, self.root / 'v1', 'NEWS')
        second = self.api.write_dataset_version(path, self.root / 'v2', 'NEWS')
        self.assertEqual(first['artifacts'], second['artifacts'])
        self.assertEqual(first['inputSha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(first['outputRows'], 1)
        self.assertEqual(first['quarantineRows'], 1)
        self.assertEqual(first['status'], 'COMPLETED')
        for name, digest in first['artifacts'].items():
            self.assertEqual(hashlib.sha256((self.root / 'v1' / name).read_bytes()).hexdigest(), digest)
        with self.assertRaises(FileExistsError):
            self.api.write_dataset_version(path, self.root / 'v1', 'NEWS')
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'OPTION'):
            self.api.write_dataset_version(path, self.root / 'bad', 'NEWS', options={'remove_all': True})
        self.assertFalse((self.root / 'bad' / 'manifest.json').exists())

    def test_original_partition_and_source_cluster_metadata_survive_cleaning(self):
        path = self.write('frozen.jsonl', json.dumps({'id': 's1', 'text': '历史冻结正文',
            'split': 'final', 'sourceClusterId': 'source-1', 'eventClusterId': 'event-1'}))
        row = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'))['rows'][0]
        self.assertEqual(row['split'], 'final')
        self.assertEqual(row['source_cluster_id'], 'source-1')
        self.assertEqual(row['event_cluster_id'], 'event-1')

    def test_cross_partition_duplicates_are_quarantined_not_merged_into_training(self):
        path = self.write('leakage.jsonl', '\n'.join(json.dumps(row, ensure_ascii=False) for row in [
            {'id': 'train-1', 'text': '相同原作', 'split': 'train'},
            {'id': 'test-1', 'text': '相同原作', 'split': 'final'},
        ]))
        result = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'))
        self.assertEqual(result['rows'], [])
        self.assertTrue(all('PARTITION_CONFLICT' in row['reasons'] for row in result['quarantine']))

    def test_collected_news_identity_and_institution_aliases_are_preserved(self):
        path = self.write('collected.jsonl', json.dumps({'documentId': 'campus:abc',
            'text': '公开新闻正文', 'institutionName': '其他高校', 'publishedAt': '2026-10-20'}))
        row = self.api.read_dataset(path, 'NEWS')['rows'][0]
        self.assertEqual(row['id'], 'campus:abc')
        self.assertEqual(row['source_institution'], '其他高校')

    def test_unicode_separators_inside_json_text_are_not_record_boundaries(self):
        content = '新闻第一段\u2028第二段\u2029第三段\u0085末段'
        path = self.write('unicode.jsonl', json.dumps({'text': content}, ensure_ascii=False) + '\n')
        data = self.api.read_dataset(path, 'NEWS')
        self.assertEqual(data['totalRows'], 1)
        self.assertEqual(data['issues'], [])
        self.assertEqual(data['rows'][0]['text'], content)

    def test_failed_manifest_write_never_emits_completed(self):
        path = self.write('write-error.jsonl', '{"text":"有效正文"}')
        actual_write = Path.write_bytes
        events = []
        def fail_manifest(target, content):
            if target.name == 'manifest.json':
                raise OSError('simulated disk failure')
            return actual_write(target, content)
        with patch.object(Path, 'write_bytes', fail_manifest), self.assertRaises(OSError):
            self.api.write_dataset_version(path, self.root / 'incomplete', 'NEWS', on_event=events.append)
        self.assertNotIn('COMPLETED', [e['stage'] for e in events])

    def test_cli_processes_real_file_and_returns_machine_readable_events(self):
        path = self.write('cli.csv', '正文\n批量导入正文\n')
        cli = Path(__file__).resolve().parents[2] / 'scripts' / 'workbench.py'
        self.assertTrue(cli.exists(), '缺少Web任务可调用的CLI')
        result = subprocess.run([sys.executable, '-B', str(cli), 'clean', '--input', str(path),
            '--output', str(self.root / 'cli-version'), '--kind', 'NEWS'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(lines[-1]['type'], 'result')
        self.assertEqual(lines[-1]['data']['outputRows'], 1)
        self.assertEqual(lines[-2]['data']['stage'], 'COMPLETED')
        self.assertEqual([row['data']['sequence'] for row in lines[:-1]], list(range(1, len(lines))))

    def test_cli_mapping_error_returns_columns_for_recovery(self):
        path = self.write('custom-column.csv', '新闻内容\n可供用户映射的正文\n')
        cli = Path(__file__).resolve().parents[2] / 'scripts' / 'workbench.py'
        result = subprocess.run([sys.executable, '-B', str(cli), 'audit', '--input', str(path),
            '--kind', 'NEWS'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        error = json.loads(result.stdout)['data']
        self.assertEqual(error.get('details', {}).get('columns'), ['新闻内容'])

    def test_cli_config_file_supports_unicode_mapping_and_spaces(self):
        path = self.write('mapped.csv', '新闻内容\n通过文件传递映射的正文\n')
        config = self.write('config with spaces.json', json.dumps({'mapping': {'text': '新闻内容'}, 'options': {}}, ensure_ascii=False))
        cli = Path(__file__).resolve().parents[2] / 'scripts' / 'workbench.py'
        result = subprocess.run([sys.executable, '-B', str(cli), 'audit', '--input', str(path),
            '--kind', 'NEWS', '--config-file', str(config)], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['audit']['validRows'], 1)

    def test_exact_dedup_preserves_word_boundaries(self):
        path = self.write('spaces.jsonl', '{"id":"one","text":"a b"}\n{"id":"two","text":"ab"}')
        result = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'))
        self.assertEqual([row['text'] for row in result['rows']], ['a b', 'ab'])
        self.assertEqual(result['duplicateRows'], 0)

    def test_internal_reclean_preserves_all_origins_without_copying_full_bodies(self):
        path = self.write('origins.jsonl', '\n'.join(json.dumps(row) for row in [
            {'id': 'one', 'text': '共同来源正文', 'url': 'https://a.example'},
            {'id': 'two', 'text': '共同来源正文', 'url': 'https://b.example'}]))
        self.api.write_dataset_version(path, self.root / 'original-clean', 'NEWS')
        data = self.api.read_dataset(self.root / 'original-clean/corpus.jsonl', 'NEWS', internal=True)
        result = self.api.clean_dataset(data)
        origins = result['rows'][0]['_provenance']
        self.assertEqual({row['url'] for row in origins}, {'https://a.example', 'https://b.example'})
        self.assertTrue(all('text' not in row for row in origins))

    def test_duplicate_inherits_consistent_partition_metadata_regardless_of_order(self):
        rows = [{'id': 'one', 'text': '相同原作'}, {'id': 'two', 'text': '相同原作',
            'split': 'final', 'sourceClusterId': 'original', 'eventClusterId': 'event'}]
        for index, records in enumerate([rows, list(reversed(rows))]):
            path = self.write(f'inherit-{index}.jsonl', '\n'.join(json.dumps(row) for row in records))
            output = self.api.clean_dataset(self.api.read_dataset(path, 'NEWS'))['rows'][0]
            self.assertEqual(output['split'], 'final')
            self.assertEqual(output['source_cluster_id'], 'original')
            self.assertEqual(output['event_cluster_id'], 'event')

    def test_internal_read_has_a_separate_bounded_budget(self):
        path = self.write('internal.jsonl', json.dumps({'text': '有效正文' * 40}))
        with patch.object(self.api, 'MAX_BYTES', 100), patch.object(self.api, 'MAX_INTERNAL_BYTES', 10000):
            with self.assertRaisesRegex(ValueError, 'BYTE_LIMIT'):
                self.api.read_dataset(path, 'NEWS')
            data = self.api.read_dataset(path, 'NEWS', internal=True)
            self.assertEqual(data['totalRows'], 1)

    def test_raw_missing_id_is_counted_before_generated_identity(self):
        path = self.write('no-id.jsonl', '{"text":"需要生成编号的正文"}')
        data = self.api.read_dataset(path, 'NEWS')
        self.assertEqual(self.api.audit_dataset(data)['missing']['id'], 1)
        self.assertTrue(data['rows'][0]['id'])

    def test_empty_internal_clean_version_can_be_audited_again(self):
        path = self.write('empty-after-clean.jsonl', '{"text":""}')
        self.api.write_dataset_version(path, self.root / 'empty-version', 'NEWS')
        result = self.api.read_dataset(self.root / 'empty-version/corpus.jsonl', 'NEWS', internal=True)
        self.assertEqual(self.api.audit_dataset(result)['totalRows'], 0)


if __name__ == '__main__':
    unittest.main()
