import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'app/python'))
from campus_shared.contracts import digest_json,file_sha256,ContractError
from campus_detection import image_enhanced,image
from campus_ocr import service_profiles

class VisionServiceTests(unittest.TestCase):
    def test_geometry_decision_and_original_config_replay(self):
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as temporary:
            folder=Path(temporary);rng=np.random.default_rng(42)
            for name in ('query','other'):Image.fromarray(rng.integers(0,256,(192,192,3),dtype=np.uint8)).save(folder/(name+'.png'))
            baseline={'schemaVersion':'image-v1','configId':'old','featureSpaceId':'same-dino','threshold':.8};enhanced=image_enhanced.configuration(baseline)
            rows=[]
            for index,name in enumerate(('query','other'),1):rows.append({'fileId':str(index),'sourceWorkId':str(index),'sourceRevisionId':str(index),'title':name,'fileSha256':file_sha256(folder/(name+'.png')),'path':str(folder/(name+'.png')),'vector':[1.]+[0.]*383,'featureSpaceId':'same-dino'})
            original={'generationId':'1','images':rows};(folder/'input-manifest.json').write_text(json.dumps(original),encoding='utf-8')
            library={'generationId':'1','images':rows,'inputManifestHash':digest_json(original)};image_enhanced.attach_sources(library,folder)
            models={'imageConfig':enhanced,'imageConfigs':{'old':baseline,enhanced['configId']:enhanced},'allowedRoots':[folder]}
            request={'taskId':'task','attemptId':'attempt','scene':'PRECHECK','inputSnapshotKey':'draft','inputSha256':'a'*64,'libraryGenerationId':'1','configId':enhanced['configId'],'fileId':'query','fileSha256':rows[0]['fileSha256'],'path':rows[0]['path']}
            with patch.object(image,'encode_images',return_value=np.array([[1.]+[0.]*383])):
                actual=image.detect_image(request,library,models)
                by_source={r['sourceFileId']:r for r in actual['evidence']};self.assertTrue(by_source['1']['acceptedCandidate']);self.assertEqual(by_source['1']['geometry']['identityBasis'],'FILE_SHA256')
                self.assertFalse(by_source['2']['acceptedCandidate']);self.assertTrue(by_source['2']['denseAcceptedCandidate'])
                old=image.detect_image({**request,'configId':'old'},library,models);self.assertTrue(all(r['acceptedCandidate'] for r in old['evidence']));self.assertTrue(all('geometry' not in r for r in old['evidence']))
            original['images'][0]['path']='changed';(folder/'input-manifest.json').write_text(json.dumps(original),encoding='utf-8');untrusted={'inputManifestHash':library['inputManifestHash']};image_enhanced.attach_sources(untrusted,folder);self.assertNotIn('_imageSources',untrusted)

    def test_adaptive_ocr_request_identity_dedup_and_old_dispatch(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as temporary:
            folder=Path(temporary);path=folder/'image.img';Image.new('RGB',(128,128),'white').save(path,format='PNG')
            baseline={'schemaVersion':'ocr-v1','configId':'baseline','modelFiles':{},'lowConfidenceThreshold':.8}
            configs=service_profiles.configurations(baseline);adaptive=next(v for v in configs.values() if v['schemaVersion']=='ocr-v2')
            raw={'rec_texts':['校园新闻'],'rec_scores':[.95],'rec_polys':[[[2,2],[100,2],[100,10],[2,10]]]}
            class Pipeline:
                def __init__(self):self.calls=0
                def predict(self,*args,**kwargs):self.calls+=1;return [SimpleNamespace(json={'res':raw})]
            pipeline=Pipeline();request={'taskId':'task','attemptId':'attempt','fileId':'image','fileSha256':file_sha256(path),'path':str(path),'configId':adaptive['configId']}
            with patch.object(service_profiles.recognizer,'load_pipeline',return_value=(pipeline,baseline)):
                result=service_profiles.recognize(request,adaptive);self.assertEqual(result['actualConfig'],adaptive);self.assertEqual(result['attemptId'],'attempt')
                self.assertTrue(result['fallbackUsed']);self.assertEqual(pipeline.calls,2);self.assertEqual(len(result['recognitionLines']),1)
                old=service_profiles.recognize({**request,'configId':'baseline'},baseline);self.assertEqual(old['actualConfig'],baseline)
                with self.assertRaises(ContractError):service_profiles.recognize({**request,'configId':'wrong'},adaptive)

if __name__=='__main__':unittest.main()
