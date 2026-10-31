import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection.web_bert import calibration,decision_scores,select_models,verify_descriptor

class WebBertTest(unittest.TestCase):
    def test_calibration_is_monotone_and_dispatch_keeps_historical_model(self):
        fit=calibration([0,0,1,1],[.1,.3,.7,.9])
        scores=decision_scores([.1,fit['threshold'],.9],fit)
        self.assertLess(scores[0],.5);self.assertEqual(.5,scores[1]);self.assertGreater(scores[2],.5)
        old=lambda rows:[.1]*len(rows);new=lambda rows:[.9]*len(rows)
        models={'textConfigs':{'old':{},'new':{'webBert':{}}},'predictBert':old,'webBertModels':{'new':{'predictBert':new,'tokenizer':'compatible'}}}
        self.assertIs(old,select_models(models,'old')['predictBert'])
        self.assertIs(new,select_models(models,'new')['predictBert'])
        self.assertIs(old,models['predictBert'])
        broken=copy.copy(models);broken['webBertModels']={}
        with self.assertRaises(ValueError):select_models(broken,'new')
        with self.assertRaises(ValueError):verify_descriptor(ROOT/'docs/当前进度.md','0'*64)

if __name__=='__main__':unittest.main()
