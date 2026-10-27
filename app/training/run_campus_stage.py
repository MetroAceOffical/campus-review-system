"""Finite approved campus training continuation; never activates production.

Wait for a fully frozen formal shard, then serialize GPU consumers. Existing
unfinished neural runs are preserved for explicit checkpoint recovery rather
than restarted. This is not an OS-startup job or recurring automation.
"""
import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from construct_correspondence import verify_ready

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'runtime/experiments/final-training-20261026'
PAIRS=ROOT/'runtime/datasets/campus-correspondence-training-v1'
RETRIEVAL_DATA=ROOT/'runtime/datasets/campus-retrieval-training-v1'
RETRIEVER=BASE/'retriever-campus-v1'
CORRESPONDENCE=BASE/'correspondence-campus-v1'
EXPORT=ROOT/'runtime/models/final/correspondence-campus-v1'
OUTPUT_LOCATION=None
TRAINING_SCRIPTS=('run_campus_stage.py','prepare_campus_retrieval.py','train_text_models.py','train_correspondence.py',
                  'export_correspondence.py','corpus.py','construct_correspondence.py','negative_basis.py')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def implementation_identity(root=ROOT):
    scripts={name:hashlib.sha256((root/'app/training'/name).read_bytes()).hexdigest() for name in TRAINING_SCRIPTS}
    return {'python':sys.version,'scripts':scripts,
            'packages':{name:importlib.metadata.version(name) for name in ['torch','transformers','peft','accelerate','tokenizers','numpy','psutil']}}


def assert_identity(expected,root=ROOT):
    if implementation_identity(root)!=expected:raise RuntimeError('Queued training code/runtime identity changed; stop and create a reviewed new stage version')


@contextlib.contextmanager
def stage_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if not path.stat().st_size:stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise RuntimeError('Another campus training controller holds the project lock') from error
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:raise RuntimeError('Another campus training controller holds the project lock') from error
            try:yield
            finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def material_state(folder):
    folder=Path(folder)
    if not (folder/'READY').exists():return 'WAITING_FORMAL_MATERIAL'
    verify_ready(folder);manifest=read(folder/'manifest.json');count=manifest.get('pairCount',0)
    classes=manifest.get('classCounts',{});negative=classes.get('0',0);positive=classes.get('1',0)
    if manifest.get('formalScaleAndBalanceReady') is not True or count<20000 or negative+positive!=count or min(negative,positive)<count*.2:return 'NEEDS_MORE_SUPPORTED_MATERIAL'
    return 'FORMAL_MATERIAL_READY'


def completed_stage(folder,expected_state):
    folder=Path(folder)
    if not (folder/'run.json').exists() and not (folder/'status.json').exists():return None
    try:state=read(folder/'status.json')
    except (FileNotFoundError,json.JSONDecodeError):state={}
    if state.get('state')!=expected_state or state.get('reloadVerified') is not True or state.get('epochs')!=2:raise RuntimeError('Existing unfinished neural run requires explicit checkpoint recovery: '+str(folder))
    name=state.get('checkpoint','')
    if not re.fullmatch(r'checkpoint-\d{6}',name):raise ValueError('Invalid completed checkpoint identity')
    checkpoint=folder/name;hashes=verify_ready(checkpoint)
    if 'state.pt' not in hashes:raise ValueError('Completed checkpoint lacks resumable state')
    return checkpoint


def gpu_busy():
    import psutil
    try:
        with socket.create_connection(('127.0.0.1',18081),timeout=.2):raise RuntimeError('Production detector is running; campus training will not compete with the demo')
    except (ConnectionRefusedError,TimeoutError):pass
    consumers={(ROOT/'app/training'/name).resolve() for name in ['construct_correspondence.py','train_text_models.py','train_correspondence.py']}
    for process in psutil.process_iter(['pid','exe','cmdline']):
        try:
            info=process.info
            if not info['exe'] or Path(info['exe']).name.lower()!='python.exe':continue
            for argument in info['cmdline'] or []:
                if not argument.endswith('.py'):continue
                candidate=Path(argument)
                if not candidate.is_absolute():candidate=ROOT/candidate
                if candidate.resolve() in consumers:return True
        except psutil.NoSuchProcess:continue
    return False


def main():
    global OUTPUT_LOCATION
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'campus-training-stage-v1')
    parser.add_argument('--wait-for-material',action='store_true')
    parser.add_argument('--continue-existing-stage',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime/experiments').resolve()):raise ValueError('Use a project experiment stage directory')
    with stage_lock(BASE/'campus-training.lock'):
        output.mkdir(parents=True,exist_ok=True);identity=implementation_identity()
        plan={'implementation':identity,'pairs':str(PAIRS),'retrievalData':str(RETRIEVAL_DATA),
              'retrieverRun':str(RETRIEVER),'correspondenceRun':str(CORRESPONDENCE),'export':str(EXPORT),
              'maximumWaitHours':48,'minimumCorrespondencePairs':20000,'minimumRetrievalGroups':1000,
              'productActivationAllowed':False}
        if (output/'pipeline.json').exists():
            if not args.continue_existing_stage or read(output/'pipeline.json')!=plan:raise RuntimeError('Existing stage needs explicit continuation with unchanged code/runtime/inputs')
        else:
            (output/'pipeline.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
            (output/'code').mkdir()
            for name in identity['scripts']:shutil.copy2(ROOT/'app/training'/name,output/'code'/name)
        OUTPUT_LOCATION=output
        def write(state,**values):
            (output/'status.json').write_text(json.dumps({'state':state,'productActivated':False,'qualityAccepted':False,**values},indent=2),encoding='utf-8')
        def run(script,*arguments):
            assert_identity(identity)
            write('LAUNCHING_OFFLINE_CHILD',script=script,actualNeuralTrainingEvidence='See the child history/checkpoint; launch intent alone is not training.')
            with (output/(Path(script).stem+'.log')).open('a',encoding='utf-8') as log:
                subprocess.run([sys.executable,'-u','-B',str(ROOT/'app/training'/script),*[str(value) for value in arguments]],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            assert_identity(identity)
        deadline=time.monotonic()+48*3600
        while True:
            assert_identity(identity);state=material_state(PAIRS)
            if state=='FORMAL_MATERIAL_READY':break
            write(state,neuralTrainingStarted=False)
            if state!='WAITING_FORMAL_MATERIAL' or not args.wait_for_material:return
            if time.monotonic()>deadline:raise TimeoutError('No complete formal material after 48 hours; no neural training started')
            time.sleep(15)
        if not (RETRIEVAL_DATA/'READY').exists():
            if RETRIEVAL_DATA.exists() and any(RETRIEVAL_DATA.iterdir()):raise RuntimeError('Preserve partial retrieval shard; recover it explicitly in a new version')
            run('prepare_campus_retrieval.py','--pairs',PAIRS,'--output',RETRIEVAL_DATA)
        verify_ready(RETRIEVAL_DATA);retrieval_manifest=read(RETRIEVAL_DATA/'manifest.json')
        retrieval_formal=retrieval_manifest.get('formalScaleAndBalanceReady') is True and retrieval_manifest.get('trainGroups',0)>=1000
        def wait_gpu():
            while gpu_busy():
                write('WAITING_OTHER_GPU_CONSUMER',neuralTrainingStarted=False)
                assert_identity(identity)
                if time.monotonic()>deadline:raise TimeoutError('GPU consumer did not exit before stage deadline')
                time.sleep(15)
            assert_identity(identity)
        if retrieval_formal:
            previous=completed_stage(BASE/'retriever-t2-v1','AUXILIARY_TRAINING_COMPLETE')
            if previous is None:raise RuntimeError('Completed auxiliary initialization is unavailable')
            if completed_stage(RETRIEVER,'CAMPUS_RETRIEVAL_TRAINING_COMPLETE') is None:
                wait_gpu()
                run('train_text_models.py','--model',ROOT/'runtime/models/final/bge-base-zh-v1.5/f03589ceff5aac7111bd60cfc7d497ca17ecac65',
                    '--initial-weights',previous/'model','--data',RETRIEVAL_DATA,'--output',RETRIEVER,
                    '--campus-correspondence','--directed-retrieval','--max-tokens','512','--microbatch','1')
            completed_stage(RETRIEVER,'CAMPUS_RETRIEVAL_TRAINING_COMPLETE')
        else:write('RETRIEVER_PENDING_SUPPORTED_GROUPS',retrievalGroups=retrieval_manifest.get('trainGroups'),M3FormalMaterialReady=True)
        if completed_stage(CORRESPONDENCE,'CORRESPONDENCE_TRAINING_COMPLETE') is None:
            wait_gpu()
            run('train_correspondence.py','--model',BASE.parent/'route-b-development-20261026/model',
                '--base-manifest',BASE.parent/'route-b-development-20261026/candidate-manifest.json','--data',PAIRS,'--output',CORRESPONDENCE)
        completed_stage(CORRESPONDENCE,'CORRESPONDENCE_TRAINING_COMPLETE')
        if not EXPORT.exists():
            run('export_correspondence.py','--run',CORRESPONDENCE,'--data',PAIRS,'--model',BASE.parent/'route-b-development-20261026/model',
                '--base-manifest',BASE.parent/'route-b-development-20261026/candidate-manifest.json','--output',EXPORT)
        verify_ready(EXPORT)
        export=read(EXPORT/'export-manifest.json')
        if not export['comparison']['mergeVerified'] or not export['comparison']['reloadVerified']:raise RuntimeError('Export reload is not verified')
        write('CAMPUS_TRAINING_AND_EXPORT_COMPLETE' if retrieval_formal else 'M3_TRAINING_AND_EXPORT_COMPLETE_RETRIEVER_PENDING',
              retrieverCampusAdaptationComplete=retrieval_formal,M3TrainingComplete=True,exportId=export['exportId'],formalCalibrationComplete=False)


if __name__=='__main__':
    try:main()
    except Exception as error:
        if OUTPUT_LOCATION is not None:
            (OUTPUT_LOCATION/'status.json').write_text(json.dumps({'state':'STAGE_STOPPED','errorType':type(error).__name__,'message':str(error),
                'productActivated':False,'qualityAccepted':False},indent=2),encoding='utf-8')
        raise
