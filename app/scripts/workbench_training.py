"""Restricted file-config CLI used by the persistent web compute queue."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/python'))
from campus_workbench.preparation import prepare, prepared, write_json
from campus_workbench.datasets import read_dataset
from campus_workbench.preparation import sha
from campus_workbench.training import compute_slot, train, predict, evaluate
from campus_workbench.news_samples import generate


def send(kind, value):
    print(json.dumps({'type': kind, 'data': value}, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-file', type=Path, required=True)
    args = parser.parse_args()
    if args.config_file.stat().st_size > 1024 * 1024:
        raise ValueError('任务配置过大')
    config = json.loads(args.config_file.read_text(encoding='utf-8-sig'))
    emit = lambda value: send('event', value)
    action = config['action']
    if action == 'PREPARE':
        result = prepare(config['input'], config['output'], config['kind'], config.get('parameters', {}), emit)
    else:
        gpu = config.get('device') == 'cuda'
        # CPU work has its own serial lane while formal GPU preparation runs.
        # Keep the frozen core and the shared GPU exclusion unchanged.
        compute_runtime = config['runtime'] if gpu else str(Path(config['runtime']) / 'web-cpu')
        with compute_slot(compute_runtime, gpu):
            if action == 'GENERATE':
                result = generate(config['preparation'], config['output'], config.get('parameters', {}), emit, resume=config.get('resume'), caches=config.get('caches', []))
            elif action == 'TRAIN':
                if config['family'] in ('cnn','bilstm','bert'):
                    from campus_workbench.training_resume import train as neural_train
                    result = neural_train(config['preparation'], config['output'], config['family'], config.get('parameters', {}), emit,config.get('resumeTraining'))
                else:result = train(config['preparation'], config['output'], config['family'], config.get('parameters', {}), emit)
            elif action == 'EVALUATE':
                result = evaluate(config['model'], config['preparation'], config['output'], emit)
            elif action == 'PREDICT':
                rows = config.get('rows')
                uploaded=config.get('predictionInput')
                if uploaded:
                    if rows is not None or config.get('preparation'):raise ValueError('预测输入只能选择一种来源')
                    from campus_workbench.prediction_input import read_prediction_input
                    rows=read_prediction_input(uploaded,config['runtime'])
                elif rows is None:
                    if config.get('preparation'):
                        _, partitions = prepared(config['preparation'])
                        rows = [row for values in partitions.values() for row in values]
                    else:
                        rows = read_dataset(config['input'], 'PAIRS', internal=True)['rows']
                result_rows = predict(config['model'], rows, emit)
                output = Path(config['output']); output.mkdir(parents=True, exist_ok=False)
                path = output / 'predictions.jsonl'
                path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in result_rows), encoding='utf-8')
                result = {'taskType': 'PREDICTION', 'status': 'COMPLETED', 'count': len(result_rows), 'rows': result_rows[:20], 'modelSha256':sha(Path(config['model'])/'manifest.json'), 'artifacts': {'predictions.jsonl': sha(path)}}
                if uploaded:result.update(inputKind='UPLOADED_FILE',inputName=uploaded['name'],inputSha256=uploaded['sha256'])
                write_json(output / 'manifest.json', result)
            else:
                raise ValueError('不支持的任务')
    send('result', result)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except BlockingIOError as error:
        send('error', {'message': str(error), 'code': 'RESOURCE_BUSY'}); raise SystemExit(75)
    except Exception as error:
        send('error', {'message': str(error)[:900], 'code': 'MODEL_TASK_FAILED'}); raise SystemExit(1)
