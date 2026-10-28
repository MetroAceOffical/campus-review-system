import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/python'))
from campus_workbench.inspection import grammar, image_text

def send(kind, data):print(json.dumps({'type': kind, 'data': data}, ensure_ascii=False, allow_nan=False), flush=True)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    try:
        config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        emit = lambda value: send('event', value)
        profile=config.get('modelProfile')
        if profile is not None and config['kind'] in ('GRAMMAR_MODEL','IMAGE_TEXT'):
            from campus_workbench.document_profiles import validate,device
            from campus_shared.document_compute import document_slot
            validate(profile)
            with document_slot(config['runtime'],neural=True):
                config['device']=device(config['kind'],profile)
                result=grammar(config,emit,True) if config['kind']=='GRAMMAR_MODEL' else image_text(config,emit)
            result['modelProfile']=profile
            result['executionDevice']=config['device']
        elif config['kind'] == 'GRAMMAR_MODEL':
            import psutil
            import torch
            from contextlib import nullcontext
            from campus_workbench.training import compute_slot
            config['device'] = 'cpu' if psutil.virtual_memory().available >= 8 * 1024 ** 3 else 'cuda'
            if config['device'] == 'cuda' and (not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 6.5 * 1024 ** 3):
                raise BlockingIOError('等待语法模型计算资源')
            with compute_slot(config['runtime'], True) if config['device'] == 'cuda' else nullcontext():
                result = grammar(config, emit, True)
        else:
            result = image_text(config, emit) if config['kind'] == 'IMAGE_TEXT' else grammar(config, emit)
        result['inputHash'] = config['inputHash']; send('result', result)
    except BlockingIOError as error:
        send('error', {'message': str(error)[:500]});raise SystemExit(75)
    except Exception as error:
        send('error', {'message': str(error)[:500]});raise SystemExit(1)
