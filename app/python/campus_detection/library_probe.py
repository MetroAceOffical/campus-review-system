"""Real M06 build/add/disable probe, isolated from business jobs and pointer."""
import json
from campus_detection.models import ROOT,load_models
from campus_detection.library import build_library
from campus_detection.text import detect_text
from campus_detection.probe import identity
from campus_shared.contracts import digest_json,file_sha256

def run():
    models=load_models()
    prepared=json.loads((ROOT/'runtime/import/initial-sources.json').read_text(encoding='utf-8'))
    documents=[];images=[]
    for work in prepared['works']:
        common={'sourceWorkId':work['externalKey'],'sourceRevisionId':work['externalKey'],
                'title':work['title'],'url':work['url'],'manuscriptId':None,'sourceMetadata':work['sourceMetadata']}
        if work['text']:documents.append(dict(common,text=work['text']))
        for image in work['images']:
            images.append(dict(common,fileId=image['sourceMetadata']['image_id'],path=image['path'],fileSha256=image['sha256']))
    folder=ROOT/'runtime/probes/M06';config={'models':models,'indexRoot':folder/'indexes','cacheRoot':folder/'image-cache'}
    target=documents[0];target_id=target['sourceWorkId']
    without={'documents':[row for row in documents if row['sourceWorkId']!=target_id],
             'images':[row for row in images if row['sourceWorkId']!=target_id]}
    before=build_library(dict(without,generationId='1'),config)
    added=build_library({'generationId':'2','documents':documents,'images':images},config)
    added_manifest=json.loads(open(added['manifestPath'],encoding='utf-8').read())
    assert len(added_manifest['documents'])==194 and len(added_manifest['images'])==59
    request=dict(identity(models['textConfig']['configId'],digest_json(target['text'])),libraryGenerationId='2',text=target['text'])
    found=detect_text(request,added_manifest,models)
    assert any(row['sourceWorkId']==target_id and row['acceptedCandidate'] for row in found['evidence'])
    disabled=build_library(dict(without,generationId='3'),config)
    disabled_manifest=json.loads(open(disabled['manifestPath'],encoding='utf-8').read())
    after=detect_text(dict(request,libraryGenerationId='3',attemptId='2'),disabled_manifest,models)
    assert all(row['sourceWorkId']!=target_id for row in after['evidence'])
    assert file_sha256(added['manifestPath'])==added['manifestSha256']
    assert all((folder/'indexes'/generation/'READY').exists() for generation in ('1','2','3'))
    repeated=build_library({'generationId':'2','documents':documents,'images':images},config)
    assert repeated['manifestSha256']==added['manifestSha256']
    (folder/'result.json').write_text(json.dumps({'before':before,'added':added,'disabled':disabled,'query':found,'after':after},ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'stage':'M06','scope':'real model isolated generation build; business queue/pointer integration belongs to M07',
             'sourceWorks':196,'texts':194,'images':59,'sourceFilesChecksumVerified':True,
             'addedWorkRetrievable':True,'disabledWorkExcluded':True,'oldGenerationRetained':True,
             'immutableRebuildIdempotent':True,'cachedImages':len(list((folder/'image-cache').glob('*.json'))),
             'imagePartFailures':sum(part['status']=='FAILED' for part in added['partResults']),
             'evidenceSha256':file_sha256(folder/'result.json')}
    (ROOT/'docs/midterm/evidence/M06-library.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__':run()
