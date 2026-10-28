"""Fixed server-owned configurations for release verification and CPU index delivery."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import file_sha256, digest_json

def run(config):
    from campus_detection.models import configurations
    if config['action']=='CONFIG':
        text,image=configurations(legacy=config['preset']=='LEGACY')
        lock=json.loads((ROOT/'validation/text/round2/selection-lock.json').read_text(encoding='utf-8'))
        path=ROOT/'validation/text'/lock['selected']['bert']['artifact']
        if file_sha256(path)!=text['weightSha256']:raise ValueError('审核权重身份不一致')
        files=[path,ROOT/'validation/text/models/bert-base-chinese/tokenizer.json',ROOT/'validation/remaining/text/selection.json',ROOT/'app/python/campus_detection/semantic.py']
        return {'scene':'TEXT_REUSE','textConfig':text,'imageConfig':image,'verifiedWeights':text['weightSha256'],'verifiedFiles':{p.relative_to(ROOT).as_posix():file_sha256(p) for p in files}}
    if config['action']=='MODEL':
        from campus_workbench.training import load_model,predict
        folder=Path(config['model']);manifest=load_model(folder)
        evaluation=json.loads(Path(config['evaluation']).read_text(encoding='utf-8'))
        if evaluation.get('taskType')!='EVALUATION' or evaluation.get('status')!='COMPLETED' or evaluation.get('modelSha256')!=file_sha256(folder/'manifest.json'):raise ValueError('独立评价与模型版本不匹配')
        for name,sha in evaluation['artifacts'].items():
            target=(Path(config['evaluation']).parent/name).resolve()
            if not target.is_relative_to(Path(config['evaluation']).parent.resolve()) or file_sha256(target)!=sha:raise ValueError('评价产物校验失败')
        rows=[]
        with (Path(config['evaluation']).parent/'predictions.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                rows.append(json.loads(line))
                if len(rows)==3:break
        # Saved validation predictions contain original sentences and raw scores.
        if not rows:raise ValueError('缺少重载核验样本')
        actual=predict(folder,rows,lambda _:None,device_override='cpu')
        if max(abs(a['score']-b['score']) for a,b in zip(actual,rows))>1e-4:raise ValueError('模型重载结果不一致')
        files=[folder/'manifest.json',Path(config['evaluation']),*(folder/name for name in manifest['artifacts'])]
        return {'scene':'PAIR_PREDICTION','modelManifestSha256':file_sha256(folder/'manifest.json'),'evaluationSha256':file_sha256(config['evaluation']),'metrics':evaluation['metrics'],'family':manifest['family'],'scoreType':'margin' if manifest['family']=='svm' else 'probability','threshold':0 if manifest['family']=='svm' else .5,'reloadRows':len(rows),'verifiedFiles':{p.relative_to(ROOT).as_posix():file_sha256(p) for p in files}}
    if config['action']=='PREDICT':
        from campus_workbench.training import predict
        if file_sha256(Path(config['model'])/'manifest.json')!=config['modelManifestSha256']:raise ValueError('发布工件已变化')
        return {'rows':predict(config['model'],config['rows'],lambda _:None,device_override='cpu'),'device':'cpu','modelManifestSha256':config['modelManifestSha256']}
    if config['action']=='INDEX':
        from campus_detection.library import build_library,artifact_cache_key,validate_image_feature
        from transformers import AutoTokenizer
        text,image=configurations()
        manifest=json.loads(Path(config['input']).read_text(encoding='utf-8'))
        for source in manifest.get('images',[]):
            cache=ROOT/'runtime/derived/image-features'/(artifact_cache_key(source['fileSha256'],image)+'.json')
            if not cache.is_file():raise ValueError('图片特征尚未准备，待检测服务恢复后重试')
            value=json.loads(cache.read_text(encoding='utf-8'));validate_image_feature(value)
            if value.get('producerConfigHash')!=digest_json(image) or value.get('fileSha256')!=source['fileSha256']:raise ValueError('图片特征身份不一致')
        models={'textConfig':text,'imageConfig':image,'tokenizer':AutoTokenizer.from_pretrained(ROOT/'validation/text/models/bert-base-chinese',local_files_only=True),'allowedRoots':[ROOT/'runtime',ROOT/'validation']}
        models['tokenizer'].model_max_length=10**8
        result=build_library(manifest,{'models':models})
        if any(p.get('status')=='FAILED' for p in result['partResults']):raise ValueError('索引包含失败部分，继续保留原版本')
        return result
    raise ValueError('不支持的交付操作')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:print(json.dumps(run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))),ensure_ascii=False,allow_nan=False))
    except Exception as error:print(json.dumps({'error':str(error)[:500]},ensure_ascii=False));sys.exit(1)
