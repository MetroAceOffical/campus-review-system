"""Opt-in real inference; full local evidence stays in runtime, summary is safe to commit."""
import hashlib
import json
from pathlib import Path
import time
from campus_shared.contracts import file_sha256,validate_result
from campus_detection.models import ROOT,load_models,read
from campus_detection.text import detect_text
from campus_detection.image import detect_image

def jsonl(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line]

def identity(config_id,input_hash):
    return {'taskId':'1','attemptId':'1','scene':'FORMAL','versionId':'1','inputSnapshotKey':'submission:1',
            'inputSha256':input_hash,'libraryGenerationId':'1','configId':config_id,'excludeManuscriptId':None}

def save(name,result,summary):
    local=ROOT/'runtime/probes/M04';local.mkdir(parents=True,exist_ok=True)
    path=local/(name+'-result.json');path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    summary['localEvidenceSha256']=file_sha256(path)
    summary['scope']='isolated current inference probe; not a live database submission or an accuracy evaluation'
    destination=ROOT/'docs/midterm/evidence'/('M04-'+name+'.json')
    destination.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary

def run_text_probe():
    started=time.perf_counter();models=load_models()
    cases=jsonl(ROOT/'validation/remaining/text/cases.jsonl')
    case=next(row for row in cases if row['split']=='development' and row['kind']=='copy')
    documents=probe_documents(case['source_id'])
    assert len(documents)==194
    library={'generationId':'1','documents':documents}
    request=dict(identity(models['textConfig']['configId'],hashlib.sha256(case['text'].encode()).hexdigest()),text=case['text'])
    result=detect_text(request,library,models);validate_result(result,request)
    expected=next(row for row in jsonl(ROOT/'validation/remaining/text/development-0.jsonl') if row['id']==case['id'])
    actual_order=[item['sourceRevisionId'] for item in result['evidence']]
    assert actual_order==expected['candidate_ids'],'Frozen TF-IDF ranking changed'
    target=next(item for item in result['evidence'] if item['sourceRevisionId']==case['source_id'])
    assert target['acceptedCandidate']
    expected_semantic=expected['sources'][case['source_id']]['semantic_windows']
    delta=max(abs(actual['score']-saved['score']) for actual,saved in zip(target['semanticWindows'],expected_semantic))
    assert len(target['semanticWindows'])==len(expected_semantic) and delta<=1e-5
    excluded=detect_text(dict(request,attemptId='2',excludeManuscriptId='17'),library,models)
    assert all(item['sourceRevisionId']!=case['source_id'] for item in excluded['evidence'])
    return save('text',{'request':request,'result':result,'selfExcludedResult':excluded},{
        'matchingSourceFound':True,'selfExcluded':True,'candidateCountAfterExclusion':excluded['candidateCount'],
        'semanticAlpha':result['semanticAlpha'],'sourceCount':len(documents),'queryWindows':result['queryWindowCount'],
        'rankingMatchesFrozen':True,'maxSemanticDeltaFromFrozen':delta,'inputSha256':request['inputSha256'],
        'modelHashes':models['loadedWeights'],'configId':models['textConfig']['configId'],'elapsedSecondsIncludingLoad':time.perf_counter()-started})

def probe_documents(self_source_id):
    raw=jsonl(ROOT/'validation/remaining/text/data/reference_sources.jsonl')+jsonl(ROOT/'validation/text/campus/sources.jsonl')
    return [{'sourceWorkId':row['source_id'],'sourceRevisionId':row['source_id'],'title':row['title'],'text':row['text'],'url':row.get('url'),
             'manuscriptId':'17' if row['source_id']==self_source_id else None,'sourceMetadata':{'scope':'frozen-source-probe'}} for row in raw]

def run_image_probe():
    import numpy as np
    started=time.perf_counter();models=load_models()
    folder=ROOT/'validation/remaining/image/evaluation'
    rows=jsonl(folder/'data/images.jsonl')
    source=next(row for row in rows if row['split']=='development' and row['role']=='primary')
    path=folder/'data'/source['relative_path'];assert file_sha256(path)==source['sha256']
    with np.load(folder/'features.npz') as frozen:vector=frozen['development_reference'][0].tolist()
    entry={'sourceWorkId':source['source_id'],'sourceRevisionId':source['image_id'],'title':source['title'],'url':source['source_url'],
           'fileId':source['image_id'],'featureSpaceId':models['imageConfig']['featureSpaceId'],'vector':vector,'manuscriptId':None}
    request=dict(identity(models['imageConfig']['configId'],source['sha256']),fileId='probe-image',path=str(path),fileSha256=source['sha256'])
    result=detect_image(request,{'generationId':'1','images':[entry]},models);validate_result(result,request)
    score=result['evidence'][0]['similarity'];assert score>.99
    return save('image',{'request':request,'result':result},{'actualEncoding':True,'configCompatible':True,'similarity':score,
        'referenceVectorOrigin':'frozen features.npz development_reference[0]','inputSha256':source['sha256'],
        'configId':models['imageConfig']['configId'],'modelHashes':models['loadedWeights'],'elapsedSeconds':time.perf_counter()-started})
