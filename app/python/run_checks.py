"""Select checks before importing them, keeping Paddle and PyTorch in separate interpreters."""
import argparse
from pathlib import Path
import sys
import unittest

parser=argparse.ArgumentParser();parser.add_argument('group',choices=['main','ocr']);args=parser.parse_args()
folder=Path(__file__).parent/'tests';sys.path.insert(0,str(folder))
suite=unittest.TestSuite()
for path in sorted(folder.glob('test_*.py')):
    if path.stem.startswith('test_ocr') == (args.group=='ocr'):suite.addTests(unittest.defaultTestLoader.loadTestsFromName(path.stem))
result=unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
