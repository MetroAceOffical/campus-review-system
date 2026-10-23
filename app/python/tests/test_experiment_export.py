import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/scripts'))
from export_experiments import export_experiment

class ExperimentExportTest(unittest.TestCase):
    def test_frozen_metrics_confusions_histories_and_twenty_configs(self):
        parent=ROOT/'runtime/test-tmp';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            output=Path(temporary);manifest=export_experiment(ROOT/'validation/text/round2',output)
            index=json.loads((output/'catalog.json').read_text());folder=(output/index['experiments'][0]['manifest']).parent
            metrics=json.loads((folder/'metrics.json').read_text());search=json.loads((folder/'search.json').read_text());history=json.loads((folder/'history.json').read_text())
            self.assertEqual(len(manifest['models']),6);self.assertEqual(len(search['configurations']),20)
            self.assertAlmostEqual(metrics['sets']['official_test']['models']['bert']['macro_f1'],0.7369837959240795,places=12)
            self.assertAlmostEqual(metrics['sets']['test_no_val_overlap']['models']['bert']['macro_f1'],0.7239446804664196,places=12)
            with (ROOT/'validation/text/round2/test-summary.csv').open(encoding='utf-8-sig') as stream:
                for row in csv.DictReader(stream):self.assertEqual(metrics['sets'][row['set']]['models'][row['family']]['confusion_matrix'],json.loads(row['confusion_matrix']))
            for record in history['runs']:
                actual=json.loads((ROOT/f'validation/text/round2/search/{record["family"]}/config-{record["index"]}/history.json').read_text())
                self.assertEqual(len(record['epochs']),len(actual));self.assertEqual([e['epoch'] for e in record['epochs']],[e['epoch'] for e in actual])
            repeated=export_experiment(ROOT/'validation/text/round2',output);self.assertEqual(repeated['contentVersion'],manifest['contentVersion'])
            before=(output/'catalog.json').read_bytes();bad=output/'missing-source';bad.mkdir()
            with self.assertRaises((ValueError,FileNotFoundError)):export_experiment(bad,output)
            self.assertEqual(before,(output/'catalog.json').read_bytes())
            self.assertEqual(next(model for model in manifest['models'] if model['id']=='svm')['scoreType'],'decision_margin')

if __name__=='__main__':unittest.main()
