import time
from campus_shared.contracts import ContractError,controlled_file,evidence_id,result_header,validate_request

def encode_images(paths,models):
    import numpy as np
    import torch
    from PIL import Image
    vectors=[]
    with torch.inference_mode():
        for path in paths:
            with Image.open(path) as source:
                image=source.convert('RGB')
                try:
                    inputs={key:value.cuda() for key,value in models['processor'](images=[image],return_tensors='pt').items()}
                    vector=torch.nn.functional.normalize(models['dino'](**inputs).last_hidden_state[:,0],dim=-1).cpu().numpy()[0]
                finally:image.close()
            if vector.shape!=(384,) or not np.isfinite(vector).all():raise ContractError('INVALID_IMAGE_FEATURE','DINO produced an invalid vector')
            vectors.append(vector)
    return np.asarray(vectors,dtype=np.float32)

def detect_image(request,library,models):
    start=time.perf_counter();config=models['imageConfig'];validate_request(request,config,library)
    output=result_header(request,config)
    path=controlled_file(request.get('path',''),request.get('fileSha256'),models['allowedRoots'])
    entries=[entry for entry in library.get('images',[]) if not (request.get('excludeManuscriptId') is not None and entry.get('manuscriptId') is not None and str(entry['manuscriptId'])==request['excludeManuscriptId'])]
    if any(entry.get('featureSpaceId')!=config['featureSpaceId'] for entry in entries):raise ContractError('INCOMPATIBLE_FEATURE_SPACE','Image feature configuration is incompatible')
    if not entries:output.update(qualityFlags=['EMPTY_LIBRARY'],elapsedMs=(time.perf_counter()-start)*1000);return output
    import numpy as np
    vector=encode_images([path],models)[0]
    matrix=np.asarray([entry['vector'] for entry in entries],dtype=np.float32)
    if matrix.ndim!=2 or matrix.shape[1]!=384 or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):raise ContractError('INVALID_INDEX','Image index vectors are invalid')
    scores=matrix@vector
    order=sorted(range(len(entries)),key=lambda i:(-float(scores[i]),str(entries[i]['sourceRevisionId']),str(entries[i]['fileId'])))[:10]
    for i in order:
        entry=entries[i]
        output['evidence'].append({'evidenceId':evidence_id(request['attemptId'],'image',[entry['sourceRevisionId'],entry['fileId']]),'evidenceType':'IMAGE_SIMILARITY','sourceScope':'LIBRARY',
          'queryFileId':request['fileId'],'sourceFileId':str(entry['fileId']),'sourceWorkId':str(entry['sourceWorkId']),'sourceRevisionId':str(entry['sourceRevisionId']),
          'sourceTitle':entry['title'],'sourceUrl':entry.get('url'),'similarity':float(scores[i]),'threshold':config['threshold'],'acceptedCandidate':bool(scores[i]>=config['threshold']),'modelConfig':config})
    output.update(elapsedMs=(time.perf_counter()-start)*1000)
    return output
