import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'app/python'))

class TrainingTelemetryTest(unittest.TestCase):
    def test_sampling_and_epoch_evaluation_preserve_parameters_and_random_state(self):
        import torch
        from campus_workbench.training_telemetry import Telemetry,evaluate_split
        model=torch.nn.Linear(2,2);before={k:v.clone() for k,v in model.state_dict().items()};rng=torch.get_rng_state().clone()
        rows=[{'label':0},{'label':1}];logits=torch.tensor([[3.,1.],[1.,3.]])
        result=evaluate_split(model,rows,lambda start,end:logits[start:end],2)
        self.assertEqual(result['accuracy'],1.);self.assertGreater(result['loss'],0)
        self.assertTrue(torch.equal(rng,torch.get_rng_state()))
        for k,v in model.state_dict().items():self.assertTrue(torch.equal(before[k],v))
        monitor=Telemetry('cpu');sample=monitor.sample(2,1.)
        self.assertGreater(sample['hostRssBytes'],0);self.assertTrue(math.isfinite(sample['cpuPercent']));self.assertGreater(sample['samplesPerSecond'],0)
        self.assertNotIn('cudaAllocatedBytes',sample)
        self.assertIsNone(monitor.sample(2,0)['samplesPerSecond'])

if __name__=='__main__':unittest.main()
