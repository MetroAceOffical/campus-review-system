"""Continue the approved auxiliary curriculum once verified data becomes available."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'runtime/experiments/final-training-20261026/retriever-t2-v1'


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    acquisition = ROOT/'runtime/datasets/public/t2ranking/2a369a430a70979223f1b9a41b1919774d46b432/acquisition.json'
    deadline = time.monotonic()+6*3600
    while True:
        try:
            ready = json.loads(acquisition.read_text(encoding='utf-8')).get('status') == 'download_verified_not_trained'
        except (FileNotFoundError,json.JSONDecodeError):
            ready = False
        if ready:
            break
        (RUN/'stage-status.json').write_text(json.dumps({'state':'WAITING_VERIFIED_DATA','trainingStarted':False}),encoding='utf-8')
        if time.monotonic()>deadline:
            raise RuntimeError('Verified T2Ranking data unavailable after six hours; no training started')
        time.sleep(10)
    data = ROOT/'runtime/datasets/t2ranking-training-v1'
    if not (data/'READY').exists():
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'app/training/prepare_t2ranking.py')],cwd=ROOT,check=True)
    previous = ROOT/'runtime/experiments/final-training-20261026/retriever-aux-v1'
    previous_state = json.loads((previous/'status.json').read_text(encoding='utf-8'))
    if previous_state['state'] != 'AUXILIARY_TRAINING_COMPLETE' or not previous_state['reloadVerified']:
        raise RuntimeError('Previous auxiliary stage is not verified')
    (RUN/'stage-status.json').write_text(json.dumps({'state':'LAUNCHING_REAL_TRAINING','data':str(data),'qualityAccepted':False}),encoding='utf-8')
    subprocess.run([sys.executable,'-u','-B',str(ROOT/'app/training/train_text_models.py'),
                    '--model',str(ROOT/'runtime/models/final/bge-base-zh-v1.5/f03589ceff5aac7111bd60cfc7d497ca17ecac65'),
                    '--initial-weights',str(previous/previous_state['checkpoint']/'model'),
                    '--data',str(data),'--output',str(RUN),'--directed-retrieval'],cwd=ROOT,check=True)
    (RUN/'stage-status.json').write_text(json.dumps({'state':'AUXILIARY_CURRICULUM_FINISHED','campusAdaptationComplete':False,'productActivated':False,'qualityAccepted':False}),encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        RUN.mkdir(parents=True,exist_ok=True)
        (RUN/'stage-status.json').write_text(json.dumps({'state':'FAILED','errorType':type(error).__name__,'message':str(error),'qualityAccepted':False}),encoding='utf-8')
        raise
