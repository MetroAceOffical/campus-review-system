import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_document_evaluation import resource_budget

class DocumentResourceTests(unittest.TestCase):
    def test_cuda_uses_gpu_budget_and_cpu_preserves_existing_host_budget(self):
        gib=1024**3
        self.assertEqual(resource_budget('grammar-model','cpu'),(10*gib,0))
        self.assertEqual(resource_budget('image-text','cpu'),(4*gib,0))
        self.assertEqual(resource_budget('grammar-model','cuda'),(int(1.5*gib),int(6.5*gib)))
        self.assertEqual(resource_budget('image-text','cuda'),(int(1.5*gib),2*gib))
        self.assertEqual(resource_budget('grammar-rules','cuda'),(0,0))

if __name__=='__main__':unittest.main()
