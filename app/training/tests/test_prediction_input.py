import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench.prediction_input import read_prediction_input


class PredictionInputTests(unittest.TestCase):
    def descriptor(self,runtime,raw,format='csv'):
        folder=runtime/'workbench/computations/input-test';folder.mkdir(parents=True,exist_ok=True)
        path=folder/('prediction-source.'+format);path.write_bytes(raw)
        return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'format':format,'name':'批量预测.'+format}

    def test_bom_multiline_csv_and_optional_labels_keep_original_text(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as directory:
            runtime=Path(directory)
            raw='\ufeff编号,原文,待比对文本,标签\r\na,"校园新闻，第一句\n第二句😀",校园报道,\r\nb,原稿,改写,1\r\n'.encode('utf-8')
            result=read_prediction_input(self.descriptor(runtime,raw),runtime)
            self.assertEqual(len(result),2);self.assertNotIn('label',result[0]);self.assertEqual(result[1]['label'],1)
            self.assertEqual(result[0]['sentence1'],'校园新闻，第一句\n第二句😀')
            raw=b'{"sentence1":"a","sentence2":"b"}\n{"sentence1":"c","sentence2":"d","label":0}\n'
            result=read_prediction_input(self.descriptor(runtime,raw,'jsonl'),runtime)
            self.assertEqual([row['id'] for row in result],['1','2']);self.assertEqual(result[1]['label'],0)

    def test_changed_file_invalid_label_duplicate_id_and_outside_path_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as directory:
            runtime=Path(directory);descriptor=self.descriptor(runtime,b'sentence1,sentence2\na,b\n')
            Path(descriptor['path']).write_bytes(b'sentence1,sentence2\nc,d\n')
            with self.assertRaisesRegex(ValueError,'校验'):read_prediction_input(descriptor,runtime)
            for records in ([{'sentence1':'a','sentence2':'b','label':True}],
                            [{'id':'same','sentence1':'a','sentence2':'b'},{'id':'same','sentence1':'c','sentence2':'d'}]):
                raw=('\n'.join(json.dumps(row) for row in records)+'\n').encode('utf-8')
                with self.assertRaises(ValueError):read_prediction_input(self.descriptor(runtime,raw,'jsonl'),runtime)
            with self.assertRaisesRegex(ValueError,'CSV'):
                read_prediction_input(self.descriptor(runtime,b'sentence1,sentence2\na,"unterminated'),runtime)
            descriptor['path']=str(runtime/'private-config/secret.csv')
            with self.assertRaisesRegex(ValueError,'任务目录'):read_prediction_input(descriptor,runtime)


if __name__=='__main__':unittest.main()
