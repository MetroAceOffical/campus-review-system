import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('runtime_manager', Path(__file__).parents[1] / 'runtime_manager.py')

class RuntimeSafetyTest(unittest.TestCase):
    def test_refuses_foreign_runtime_and_system_mysql_port(self):
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        root = Path(__file__).resolve().parents[3]
        config = {'runtimeRoot': '../foreign', 'ports': {'mysql': 3308},
                  'database': 'campus_review_midterm', 'testDatabase': 'campus_review_midterm_test'}
        with self.assertRaises(ValueError):
            module.validate_config(root, config)
        config['runtimeRoot'] = 'runtime'
        config['ports']['mysql'] = 3306
        with self.assertRaises(ValueError):
            module.validate_config(root, config)

if __name__ == '__main__':
    unittest.main()
