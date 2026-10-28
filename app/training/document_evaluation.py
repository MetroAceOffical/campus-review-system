"""Known development controls for grammar edits and image/local-context facts."""
import argparse
import hashlib
import json
from pathlib import Path
from corpus import read_jsonl
from construct_correspondence import verify_ready

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'runtime/datasets/document-check-controls-20261028-v1'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def edit_score(sample, issues):
    expected = {(e['start'], e['end'], e['original'], e['replacement']) for e in sample['expected']}
    actual, invalid = set(), 0
    for issue in issues:
        a, b = issue.get('start'), issue.get('end')
        if (issue.get('field') != 'BODY' or not isinstance(a, int) or not isinstance(b, int)
                or not 0 <= a <= b <= len(sample['text']) or sample['text'][a:b] != issue.get('original')
                or not isinstance(issue.get('replacement'), str)):
            invalid += 1
            continue
        actual.add((a, b, issue['original'], issue['replacement']))
    return dict(truePositive=len(expected & actual), falsePositive=len(actual - expected) + invalid,
                falseNegative=len(expected - actual), invalidSuggestions=invalid)


def grammar_material():
    rows = []
    topics = ['数字媒介', '新闻采写', '摄影创作', '校园文化', '网络安全',
              '学术研究', '影视制作', '志愿服务', '艺术实践', '就业指导']
    def append(identity, family, category, text, expected=None, citations=None):
        rows.append(dict(sampleId=identity, sourceFamilyId=family, category=category,
                         text=text, expected=expected or [], citations=citations or [],
                         split='development', truthOrigin='explicitly_authored_control', humanVerified=False))
    def edit(text, old, replacement, minimal=False):
        start = text.index(old)
        if minimal:
            left = 0
            while left < min(len(old), len(replacement)) and old[left] == replacement[left]:
                left += 1
            right = 0
            while right < min(len(old), len(replacement))-left and old[-1-right] == replacement[-1-right]:
                right += 1
            return dict(start=start+left, end=start+len(old)-right,
                        original=old[left:len(old)-right], replacement=replacement[left:len(replacement)-right])
        return dict(start=start, end=start+len(old), original=old, replacement=replacement)
    for i in range(100):
        family = f'grammar-authored:{i:03d}'
        text = f'学院开展{topics[i%10]}主题交流，第{i+1}组师生已经完成准备。'
        append(family+':clean', family, 'clean', text)
        for category, old, replacement in [('punctuation','，','，，'), ('word','开展','开展开展'), ('spaces','师生已经','师生  已经')]:
            changed = text.replace(old, replacement, 1)
            expected = edit(changed, '  ', '') if category == 'spaces' else edit(changed, replacement, old)
            append(family+':'+category, family, category, changed, [expected])
    for i in range(20):
        text = f'《开展开展实践活动》第{i+1}组的安排已经公布。' if i < 10 else f'开展开展实践活动，第{i+1}组按原文引用。'
        citations = [] if i < 10 else [dict(plainStart=0, plainEnd=4)]
        append(f'grammar-protected:{i:03d}', f'grammar-protected:{i:03d}', 'protected', text, citations=citations)
    pairs = [('勾通能力','沟通能力'), ('实贱能力','实践能力'), ('学习效律','学习效率'), ('知识储被','知识储备'),
             ('团对协作','团队协作'), ('专业素杨','专业素养'), ('参于意识','参与意识'), ('组织协条','组织协调')]
    for i in range(80):
        wrong, correct = pairs[i%len(pairs)]
        text = f'本次{topics[(i//8)%10]}活动旨在提升师生的{wrong}，第{i+1}组按要求完成记录。'
        append(f'grammar-typo:{i:03d}', f'grammar-typo:{i:03d}', 'typo', text, [edit(text, wrong, correct, True)])
    return rows


def fact_material(sample):
    # Independent truth from render_notice's frozen generation parameters, not fields().
    index = int(sample['sampleId'].split(':')[1])
    day = index % 28 + 1
    location = f'Media Lab A{200+index}' if index >= 25 else f'综合实验楼 A{200+index}室'
    kind = sample['transformation']
    truth = {'日期':'MATCH', '地点':'MATCH', '主办单位':'INSUFFICIENT'}
    if kind == 'low_contrast':
        return '请按活动安排参与交流。', {key:'INSUFFICIENT' for key in truth}
    if kind == 'downscale_jpeg':
        truth['日期'] = 'CONFLICT'
        day = day % 28 + 1
    if kind == 'blur':
        truth['地点'] = 'CONFLICT'
        location = '第二教学楼 B999室'
    return f'日期：2026年11月{day}日。\n地点：{location}。', truth


def prepare(output):
    output = output.resolve()
    if not output.is_relative_to((ROOT/'runtime/datasets').resolve()):
        raise ValueError('Use project dataset output')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Preserve existing material; use another reviewed version')
    ocr = ROOT/'runtime/datasets/campus-ocr-controls-v1'
    ocr_hashes = verify_ready(ocr)
    history = ROOT/'runtime/experiments/final-training-20261026/ocr-recovery-development-v2'
    historical = json.loads((history/'run.json').read_text(encoding='utf-8'))
    if historical['split'] != 'development' or historical['datasetReadySha256'] != sha(ocr/'READY'):
        raise ValueError('Historical OCR development data identity mismatch')
    predictions = {r['sampleId']:r for r in read_jsonl(history/'predictions.jsonl')}
    sources = list(read_jsonl(ocr/'samples.jsonl'))
    samples = [r for r in sources if r['split']=='development']
    if len(samples) != 100:
        raise ValueError('Complete OCR development controls required')
    references = {r['imageId']:r for r in read_jsonl(ROOT/'runtime/datasets/campus-image-protocol-v1/references.jsonl')}
    corpus = list(read_jsonl(ROOT/'runtime/datasets/campus-quality-20261028-v1/corpus.jsonl'))
    by_id = {r['documentId']:r for r in corpus}; by_url = {r['url']:r for r in corpus}
    image_rows = []
    for sample in samples:
        context, truth = fact_material(sample)
        previous = predictions[sample['sampleId']]
        if not previous['cerEligible'] or previous['split']!='development':
            raise ValueError('Historical prediction scope mismatch')
        image_rows.append(dict(sampleId=sample['sampleId'], sourceFamilyId=sample['sourceFamilyId'],
            split='development', imagePath=str((ocr/sample['path']).resolve()), imageSha256=sample['sha256'],
            factContext=context, expectedFields=truth, transformation=sample['transformation'],
            cachedOcr=previous['adaptive'], cachedOcrError=previous['error'],
            contexts=[dict(field='CAPTION', text=sample['groundTruthText'][:500], label='已知通知内容', contextId='related'),
                      *[dict(field='BODY',text=text,label='其他话题',contextId=f'other-{i}') for i,text in enumerate([
                          '篮球运动员在球场参加篮球决赛，观众为球队加油。', '化学实验室开展药物分析，研究人员观察试剂反应。',
                          '山间自然风光，湖水与森林交相辉映。', '学校食堂提供午餐，师生有序排队取餐。'])]],
            expectedContextId='related', truthOrigin='known_rendered_notice_parameters', realOrSynthetic='synthetic'))
    for sample in (s for s in sources if s['split']=='runtime_only'):
        ref = references[sample['sourceImageId']]
        article = by_id.get(ref['sourceId']) or by_url.get(ref['articleUrl'])
        contexts = [dict(field='TITLE',text=article['title'],label='原发布标题',contextId='publication-title'),
                    dict(field='BODY',text=article['text'][:500],label='原发布正文',contextId='publication-body')] if article else []
        image_rows.append(dict(sampleId=sample['sampleId'],sourceFamilyId=sample['sourceFamilyId'],split='runtime_only',
            imagePath=str((ocr/sample['path']).resolve()),imageSha256=sample['sha256'],factContext='',
            expectedFields=None,contexts=contexts,expectedContextId=None,truthOrigin='untranscribed_publication_association_only',
            realOrSynthetic='real',sourceArticleAvailable=article is not None))
    output.mkdir(parents=True)
    for name, rows in [('grammar.jsonl',grammar_material()),('image-text.jsonl',image_rows)]:
        (output/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest=dict(state='DOCUMENT_DEVELOPMENT_CONTROLS_FROZEN',grammarSamples=500,knownImageTextSamples=100,
                  realImageRuntimeSamples=50,finalQueriesEvaluated=0,grammarTruth='authored_format_and_typo_controls',
                  imageTruth='synthetic_notice_parameters',naturalImageRelevanceTruthCount=0,
                  realTranscriptionsAvailable=0,qualityAccepted=False,
                  ocrReadySha256=sha(ocr/'READY'),ocrSampleManifestSha256=ocr_hashes['samples.jsonl'],
                  historicalOcrRunSha256=sha(history/'run.json'),historicalOcrPredictionsSha256=sha(history/'predictions.jsonl'),
                  historicalOcrConfiguration=historical['adaptiveConfiguration'],
                  materialCodeSha256=sha(Path(__file__)))
    atomic_json(output/'manifest.json',manifest)
    atomic_json(output/'READY',{name:sha(output/name) for name in ['grammar.jsonl','image-text.jsonl','manifest.json']})
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DATA)
    print(json.dumps(prepare(parser.parse_args().output)),flush=True)
