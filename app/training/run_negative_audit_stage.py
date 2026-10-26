"""Audit the expanded offline candidate pool when its immutable export becomes ready."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runtime/experiments/final-training-20261026/expanded-negative-audit'
SOURCE=ROOT/'runtime/datasets/campus-correspondence-candidates-v2'
OUTPUT=ROOT/'runtime/datasets/campus-supported-negatives-v4'


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+6*3600
    while not (SOURCE/'READY').exists():
        (RUN/'status.json').write_text(json.dumps({'state':'WAITING_FROZEN_CANDIDATES','trainingLabelsCreated':False}),encoding='utf-8')
        if time.monotonic()>deadline:raise RuntimeError('Expanded candidate job not ready within six hours')
        time.sleep(15)
    if not (OUTPUT/'READY').exists():
        (RUN/'status.json').write_text(json.dumps({'state':'AUDITING_CONTENT_EVIDENCE','ruleLabelsAreNotHumanGold':True}),encoding='utf-8')
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'app/training/audit_negative_candidates.py'),'--source',str(SOURCE),'--output',str(OUTPUT)],cwd=ROOT,check=True)
    manifest=json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8'))
    (RUN/'status.json').write_text(json.dumps({'state':'RULE_AUDIT_COMPLETE','statistics':manifest['statistics'],'M3TrainingStarted':False},indent=2),encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception as error:
        RUN.mkdir(parents=True,exist_ok=True)
        (RUN/'status.json').write_text(json.dumps({'state':'FAILED','error':type(error).__name__+': '+str(error),'M3TrainingStarted':False}),encoding='utf-8')
        raise
