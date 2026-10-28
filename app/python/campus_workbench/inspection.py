"""CPU manuscript grammar and image/text checks on immutable input snapshots."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
QWEN = ROOT / 'runtime/models/final/Qwen2.5-3B-Instruct/aa8e72537993ba99e69dfaafa59ed015b17504d1'
CLIP = ROOT / 'runtime/models/final/chinese-clip-vit-base-patch16/36e679e65c2a2fead755ae21162091293ad37834'


def check_files(folder):
    manifest = json.loads((folder / 'acquisition.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        with (folder / item['file']).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                raise ValueError('模型文件校验失败')


def protected(text):
    return [(m.start(), m.end()) for m in re.finditer(r'\d+(?:[年月日号:.%/\-]\d*)*|[“《][^”》\n]*[”》]|南京传媒学院|[A-Za-z][A-Za-z.\-]*(?: [A-Za-z][A-Za-z.\-]*)*|(?:记者|通讯员|摄影|作者|编辑|审核)[：:]\s*[\u4e00-\u9fff·]{2,12}', text)]


def grammar(config, emit, enhanced=False):
    issues = []; blocked = 0
    def add(field, start, end, old, replacement, category, engine):
        nonlocal blocked
        text = config['title'] if field == 'TITLE' else config['plainText']
        if text[start:end] != old or old == replacement:
            return
        spans = protected(text) + ([(c['plainStart'], c['plainEnd']) for c in config['citations']] if field == 'BODY' else [])
        if any(start < b and end > a or start == end and a <= start < b for a, b in spans):
            blocked += 1;return
        if any(x['field'] == field and x['start'] < end and x['end'] > start for x in issues):
            return
        issues.append({'id': hashlib.sha256(f'{field}:{start}:{end}:{replacement}'.encode()).hexdigest()[:20], 'field': field,
                       'start': start, 'end': end, 'original': old, 'replacement': replacement, 'category': category, 'engine': engine})
    for field, text in [('TITLE', config['title']), ('BODY', config['plainText'])]:
        for match in re.finditer(r'([，。；：！？])\1+', text):
            add(field, match.start(), match.end(), match.group(), match.group(1), '标点重复', 'RULES')
        for match in re.finditer(r'(已经|通过|进行|以及|同时|为了|由于|表示|开展)\1', text):
            add(field, match.start(), match.end(), match.group(), match.group(1), '词语重复', 'RULES')
        for match in re.finditer(r'(?<=[\u4e00-\u9fff]) {2,}(?=[\u4e00-\u9fff])', text):
            add(field, match.start(), match.end(), match.group(), '', '多余空格', 'RULES')
    emit({'stage': 'RULES_CHECKED', 'processed': len(config['plainText']), 'total': len(config['plainText']), 'issues': len(issues)})
    if enhanced:
        import psutil
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        device = config.get('device', 'cpu')
        if device == 'cpu' and psutil.virtual_memory().available < 8 * 1024 ** 3:
            raise ValueError('可用内存不足，请稍后重试模型语法检查')
        check_files(QWEN);torch.set_num_threads(2)
        emit({'stage': 'MODEL_LOADING', 'processed': 0, 'total': 1})
        tokenizer = AutoTokenizer.from_pretrained(QWEN, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(QWEN, torch_dtype=torch.bfloat16, device_map={'': device}, local_files_only=True, trust_remote_code=False).eval()
        sentences = [(field, match.start(), match.group()) for field, text in [('TITLE', config['title']), ('BODY', config['plainText'])] for match in re.finditer(r'[^。！？\n]{1,180}[。！？]?', text)]
        for i, (field, start, text) in enumerate(sentences):
            prompt = '检查下面句子的错别字、成分缺失、语序和搭配。只做必要的最小修改，保留人名、校名、日期、数字和引文，不润色或增加事实。没有错误则保持原句。只输出JSON对象，格式为{"corrected":"纠正后的完整句子"}。\n原句：' + text
            inputs = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}], add_generation_prompt=True, return_tensors='pt').to(device)
            with torch.inference_mode():
                output = model.generate(inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=384, do_sample=False, pad_token_id=tokenizer.eos_token_id)
            raw = tokenizer.decode(output[0, inputs.shape[1]:], skip_special_tokens=True)
            try:
                value = json.loads(re.search(r'\{.*\}', raw, re.S).group())['corrected']
                if not isinstance(value, str) or set(re.findall(r'\d+', value)) != set(re.findall(r'\d+', text)):
                    blocked += 1;continue
                edits = [entry for entry in difflib.SequenceMatcher(None, text, value, autojunk=False).get_opcodes() if entry[0] != 'equal']
                if sum(max(b - a, d - c) for _, a, b, c, d in edits) > max(4, len(text) * .2):
                    blocked += 1;continue
                for _, a, b, c, d in edits:
                    add(field, start + a, start + b, text[a:b], value[c:d], '语法或表达建议', 'QWEN')
            except (ValueError, TypeError, KeyError, AttributeError):
                blocked += 1
            emit({'stage': 'GRAMMAR_CHECKING', 'processed': i + 1, 'total': len(sentences), 'issues': len(issues)})
    return {'status': 'COMPLETED', 'kind': 'GRAMMAR_MODEL' if enhanced else 'GRAMMAR_RULES', 'issues': sorted(issues, key=lambda x: (x['field'], x['start'])), 'protectedSuggestions': blocked, 'model': 'Qwen2.5-3B-Instruct / ' + config.get('device','cpu').upper() if enhanced else '中文格式规则', 'categoryCounts': {category: sum(x['category'] == category for x in issues) for category in sorted({x['category'] for x in issues})}}


def fields(text):
    values = {'日期': set(), '地点': set(), '主办单位': set()}
    for match in re.finditer(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', text):
        values['日期'].add(f'{int(match[1]) if match[1] else ""}/{int(match[2])}/{int(match[3])}')
    for key in ('地点', '主办单位'):
        values[key].update(m.group(1).strip() for m in re.finditer(key + r'[：:]\s*([^\n，。；]{2,40})', text))
    return values


def compare_fields(ocr, context):
    left, right = fields(ocr), fields(context); rows = []
    for key in left:
        a, b = left[key], right[key]
        status = 'INSUFFICIENT'
        if len(a) == len(b) == 1:
            x, y = next(iter(a)), next(iter(b))
            if key == '日期':
                xa, ya = x.split('/'), y.split('/')
                status = 'MATCH' if xa[-2:] == ya[-2:] and (not xa[0] or not ya[0] or xa[0] == ya[0]) else 'CONFLICT'
            else:
                status = 'MATCH' if x == y else 'CONFLICT'
        rows.append({'field': key, 'imageValues': sorted(a), 'textValues': sorted(b), 'status': status})
    return rows


def image_text(config, emit):
    import torch
    from PIL import Image
    from transformers import ChineseCLIPModel, ChineseCLIPProcessor
    if not config['images']:
        return {'status': 'COMPLETED', 'kind': 'IMAGE_TEXT', 'images': [], 'model': 'Chinese-CLIP ViT-B/16'}
    check_files(CLIP);torch.set_num_threads(2)
    emit({'stage': 'MODEL_LOADING', 'processed': 0, 'total': 1})
    model = ChineseCLIPModel.from_pretrained(CLIP, local_files_only=True).eval()
    processor = ChineseCLIPProcessor.from_pretrained(CLIP, local_files_only=True)
    token = (ROOT / 'runtime/private-config/internal-token').read_text().strip()
    results = []
    for index, picture in enumerate(config['images']):
        path = Path(picture['path'])
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != picture['sha256']:
                raise ValueError('图片内容已变化，请重新检查')
        candidates = picture['contexts']
        scores = []
        if candidates:
            with Image.open(path) as picture_file:
                inputs = processor(text=[item['text'] for item in candidates], images=picture_file.convert('RGB'), return_tensors='pt', padding=True, truncation=True, max_length=512)
            with torch.no_grad():
                value = model(**inputs)
                image = value.image_embeds / value.image_embeds.norm(dim=-1, keepdim=True)
                text = value.text_embeds / value.text_embeds.norm(dim=-1, keepdim=True)
                scores = (image @ text.T)[0].tolist()
        ranked = sorted([dict(item, score=float(score)) for item, score in zip(candidates, scores)], key=lambda x: -x['score'])
        recognized = ''; ocr_status = 'UNAVAILABLE'; error = ''; ocr_result = None
        try:
            frozen = config.get('ocrConfig') or json.loads((ROOT / 'app/config/frozen-ocr.json').read_text(encoding='utf-8'))
            body = {'taskId': config['checkId'], 'attemptId': config['checkId'] + ':' + picture['nodeId'], 'fileId': picture['fileId'], 'fileSha256': picture['sha256'], 'path': str(path), 'configId': frozen['configId']}
            request = urllib.request.Request('http://127.0.0.1:18082/recognize', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-Internal-Token': token})
            with urllib.request.urlopen(request, timeout=120) as response:
                ocr = json.loads(response.read())
            if any(ocr.get(key)!=body[key] for key in ('taskId','attemptId','fileId','fileSha256')) or ocr.get('actualConfig')!=frozen:
                raise ValueError('OCR图片身份不一致')
            recognized = '\n'.join(line['text'] for line in ocr.get('recognitionLines', []) if line['confidence'] >= .8)
            ocr_status = ocr.get('ocrStatus','COMPLETED'); ocr_result = ocr
        except Exception:
            error = '图片文字识别暂不可用'
        # Only local caption/adjacent text may establish a concrete fact conflict.
        # A remote paragraph with a higher semantic score cannot supply a date.
        facts = compare_fields(recognized, picture['factContext'])
        results.append({'nodeId': picture['nodeId'], 'fileId': picture['fileId'], 'caption': picture['caption'], 'matches': ranked[:5], 'ocrStatus': ocr_status, 'ocrText': recognized, 'ocrError': error, 'fields': facts, 'factStatus': 'CONFLICT' if any(row['status'] == 'CONFLICT' for row in facts) else 'MATCH' if any(row['status'] == 'MATCH' for row in facts) else 'INSUFFICIENT'})
        if ocr_result is not None:results[-1]['ocr']=ocr_result
        emit({'stage': 'IMAGE_TEXT_CHECKING', 'processed': index + 1, 'total': len(config['images'])})
    return {'status': 'COMPLETED', 'kind': 'IMAGE_TEXT', 'images': results, 'model': 'Chinese-CLIP ViT-B/16 / CPU', 'modelRevision': CLIP.name}
