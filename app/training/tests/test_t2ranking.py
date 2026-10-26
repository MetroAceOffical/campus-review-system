import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_t2ranking import prepare


class T2RankingTests(unittest.TestCase):
    def test_only_zero_grade_is_negative_and_five_distinct_pairs_are_prepared(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source';source.mkdir()
            files = {'queries.train.tsv':'qid\tquery\nq1\t校园活动查询\n',
                     'qrels.train.tsv':'qid\tunused\tpid\trel\nq1\t0\tp1\t3\nq1\t0\tp2\t0\nq1\t0\tp3\t0\nq1\t0\tp4\t0\nq1\t0\tp5\t0\nq1\t0\tp6\t1\n',
                     'collection.tsv':'pid\tpassage\n'+''.join(f'p{i}\t第{i}个公开段落\n' for i in range(1,7))}
            metadata=[]
            for name,text in files.items():
                path=source/name;path.write_text(text,encoding='utf-8')
                metadata.append({'file':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            (source/'acquisition.json').write_text(json.dumps({'status':'download_verified_not_trained','revision':'fixture','files':metadata}),encoding='utf-8')
            output=Path(folder)/'prepared'
            prepare(source,output,query_count=1)
            db = sqlite3.connect(output/'auxiliary.sqlite')
            try:
                self.assertEqual(db.execute('select count(*) from pairs').fetchone()[0],5)
                self.assertEqual(db.execute('select count(*) from pairs where target=0').fetchone()[0],4)
                self.assertEqual(db.execute("select count(*) from documents where id='t2p:p6'").fetchone()[0],0)
            finally:
                db.close()
            with self.assertRaises(RuntimeError):
                prepare(source,output,query_count=1)
