"""Finite corrected-material pipeline; share the Web compute lock, never activate models."""
import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from construct_correspondence import verify_ready
from run_campus_stage import recipe_paths, stage_lock, material_state

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ('run_corrected_material.py', 'run_campus_stage.py', 'construct_correspondence.py',
           'prepare_corrected_training.py', 'article_extraction.py', 'repair_campus_material.py',
           'mine_correspondence_candidates.py', 'audit_negative_candidates.py', 'prepare_correspondence.py',
           'prepare_campus_retrieval.py', 'train_text_models.py', 'train_correspondence.py',
           'export_correspondence.py', 'corpus.py', 'campus_partitions.py', 'negative_basis.py')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity():
    files = [ROOT / 'app/training' / name for name in SCRIPTS]
    files += [ROOT / 'app/python/campus_workbench' / name for name in ('training.py', 'preparation.py')]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--continue-existing-stage', action='store_true')
    args = parser.parse_args()
    recipe = read(args.recipe); paths = recipe_paths(recipe); output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'runtime/experiments') or output in paths.values():
        raise ValueError('Use a distinct project experiment controller directory')
    partition_hashes = verify_ready(paths['partitions']); verify_ready(paths['preparation'])
    corpus = read(paths['partitions'] / 'manifest.json'); preparation = read(paths['preparation'] / 'manifest.json')
    if not corpus['minimum5000SourcesMet'] or preparation['partitionHashes'] != partition_hashes:
        raise ValueError('Corrected corpus identity/scale differs')
    if preparation['plannedOriginals'] < 1200 or preparation['plannedOriginals'] != recipe['generation']['originals']:
        raise ValueError('Do not reduce the audited original-source generation plan')
    if recipe['generation']['segments'] != preparation['plannedSegments']:
        raise ValueError('Generation segment plan differs')
    expected = {'recipeSha256': sha(args.recipe), 'algorithmHashes': identity(),
                'partitions': partition_hashes, 'preparation': verify_ready(paths['preparation']),
                'resourceWaitHours': 48, 'productActivationAllowed': False}
    with stage_lock(output / 'controller.lock'):
        plan_file = output / 'pipeline.json'
        if plan_file.exists():
            if not args.continue_existing_stage or read(plan_file) != expected:
                raise RuntimeError('Resume requires unchanged inputs/code and explicit continuation')
        else:
            plan_file.write_text(json.dumps(expected, indent=2), encoding='utf-8')
            code = output / 'code'; code.mkdir()
            for name in SCRIPTS:
                shutil.copy2(ROOT / 'app/training' / name, code / name)

        def check():
            if sha(args.recipe) != expected['recipeSha256'] or identity() != expected['algorithmHashes']:
                raise RuntimeError('Queued implementation changed; preserve this stage and review a new version')

        def write(state, **values):
            (output / 'status.json').write_text(json.dumps({'state': state, 'productActivated': False,
                'qualityAccepted': False, **values}, ensure_ascii=False, indent=2), encoding='utf-8')

        def run(script, *arguments):
            check(); write('RUNNING_CHILD', script=script)
            with (output / (Path(script).stem + '.log')).open('a', encoding='utf-8') as log:
                subprocess.run([sys.executable, '-u', '-B', str(ROOT / 'app/training' / script),
                    *map(str, arguments)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            check()

        try:
            deadline = time.monotonic() + 48 * 3600
            # Mining is already running on CPU. Its immutable READY is the only hand-off.
            while not (paths['candidates'] / 'READY').exists():
                check(); write('WAITING_CORRECTED_CANDIDATES', neuralTrainingStarted=False)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Candidate mining did not finish; no duplicate miner or neural job started')
                time.sleep(15)
            verify_ready(paths['candidates'])
            if not (paths['negatives'] / 'READY').exists():
                if paths['negatives'].exists() and any(paths['negatives'].iterdir()):
                    raise RuntimeError('Preserve partial negative audit; explicitly prepare a new version')
                run('audit_negative_candidates.py', '--source', paths['candidates'], '--partitions', paths['partitions'], '--output', paths['negatives'])
            verify_ready(paths['negatives'])
            if not (paths['generation'] / 'status.json').exists() or read(paths['generation'] / 'status.json').get('state') != 'TRAIN_CONSTRUCTION_FINISHED':
                if paths['generation'].exists() and any(paths['generation'].iterdir()) and not args.continue_existing_stage:
                    raise RuntimeError('Existing generation needs explicit same-identity checkpoint continuation')
                sys.path.insert(0, str(ROOT / 'app/python'))
                from campus_workbench.training import compute_slot
                resource_deadline = time.monotonic() + 48 * 3600
                while True:
                    check()
                    with contextlib.ExitStack() as stack:
                        try:
                            stack.enter_context(compute_slot(ROOT / 'runtime', True))
                        except BlockingIOError as error:
                            write('WAITING_WEB_OR_GPU_RESOURCE', reason=str(error), plannedOriginals=preparation['plannedOriginals'],
                                  plannedSegments=preparation['plannedSegments'], neuralTrainingStarted=False)
                            if time.monotonic() >= resource_deadline:
                                raise TimeoutError('Resource still occupied after 48 hours; existing task was not interrupted')
                            time.sleep(15)
                            continue
                        check(); paths['generation'].mkdir(parents=True, exist_ok=True)
                        snapshot = paths['generation'] / 'generation-code.py'
                        if snapshot.exists() and sha(snapshot) != sha(ROOT / 'app/training/construct_correspondence.py'):
                            raise ValueError('Generation code snapshot differs')
                        if not snapshot.exists():
                            shutil.copy2(ROOT / 'app/training/construct_correspondence.py', snapshot)
                        run('construct_correspondence.py', '--partitions', paths['partitions'], '--output', paths['generation'],
                            '--max-originals', preparation['plannedOriginals'], '--prompt-version', '3',
                            '--reuse-generation', paths['preparation'] / 'generation-seed', '--device', 'cuda')
                        break
            if not (paths['pairs'] / 'READY').exists():
                if paths['pairs'].exists() and any(paths['pairs'].iterdir()):
                    raise RuntimeError('Preserve partial pair assembly; explicitly prepare a new version')
                run('prepare_correspondence.py', '--generation', paths['generation'], '--negatives', paths['negatives'],
                    '--partitions', paths['partitions'], '--output', paths['pairs'])
            state = material_state(paths['pairs'])
            if state != 'FORMAL_MATERIAL_READY':
                write(state, neuralTrainingStarted=False, pairManifest=read(paths['pairs'] / 'manifest.json'))
                return
            arguments = ['--recipe', args.recipe, '--output', paths['trainingStage']]
            if (paths['trainingStage'] / 'pipeline.json').exists() and args.continue_existing_stage:
                arguments.append('--continue-existing-stage')
            run('run_campus_stage.py', *arguments)
            write('TRAINING_CONTROLLER_RETURNED', training=read(paths['trainingStage'] / 'status.json'))
        except Exception as error:
            write('MATERIAL_PIPELINE_STOPPED', errorType=type(error).__name__, message=str(error))
            raise


if __name__ == '__main__':
    main()
