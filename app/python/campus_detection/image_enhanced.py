"""Versioned DINO candidate retrieval with independently verified image regions."""
import json,time
from pathlib import Path
from campus_shared.contracts import ContractError,controlled_file,digest_json,evidence_id,file_sha256,result_header,validate_request
from . import image_geometry as geometry

def configuration(baseline):
    import cv2,numpy,PIL
    config={**baseline,'schemaVersion':'image-v2','baseConfigId':baseline['configId'],
            'candidateK':20,'maximumVerifiedCandidates':40,'maximumHashScans':500,
            'decision':'GEOMETRIC_CORRESPONDENCE','geometryPolicy':geometry.POLICY,
            'algorithms':{name:file_sha256(Path(__file__).with_name(name)) for name in ('image_enhanced.py','image_geometry.py')},
            'software':{'opencv':cv2.__version__,'numpy':numpy.__version__,'Pillow':PIL.__version__}}
    config.pop('configId');config['configId']='image-'+digest_json(config)
    return config

def attach_sources(library,directory):
    # Existing immutable indexes omitted paths; their original input manifest
    # remains independently bound by its canonical content hash.
    source=Path(directory)/'input-manifest.json'
    if not source.is_file():return
    if source.stat().st_size>128*1024*1024:return
    data=json.loads(source.read_text(encoding='utf-8'))
    if digest_json(data)!=library.get('inputManifestHash'):return
    library['_imageSources']={(str(row['sourceRevisionId']),str(row['fileId'])):row for row in data.get('images',[])}

def detect(request,library,models,config):
    import cv2,numpy as np
    from .image import encode_images
    started=time.perf_counter();validate_request(request,config,library);output=result_header(request,config)
    query_path=controlled_file(request.get('path',''),request.get('fileSha256'),models['allowedRoots']);query_bytes=query_path.read_bytes()
    entries=[row for row in library.get('images',[]) if not(request.get('excludeManuscriptId') is not None and row.get('manuscriptId') is not None and str(row['manuscriptId'])==request['excludeManuscriptId'])]
    if any(row.get('featureSpaceId')!=config['featureSpaceId'] for row in entries):raise ContractError('INCOMPATIBLE_FEATURE_SPACE','Image feature configuration is incompatible')
    if not entries:output.update(qualityFlags=['EMPTY_LIBRARY'],elapsedMs=(time.perf_counter()-started)*1000);return output
    matrix=np.asarray([row['vector'] for row in entries],dtype=np.float32)
    if matrix.ndim!=2 or matrix.shape[1]!=384 or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):raise ContractError('INVALID_INDEX','Invalid image vectors')
    scores=matrix@encode_images([query_path],models)[0]
    ranked=sorted(range(len(entries)),key=lambda i:(-float(scores[i]),str(entries[i]['sourceRevisionId']),str(entries[i]['fileId'])))
    candidates=set(ranked[:config['candidateK']]);exact=set();near={};paths={};failures=set()
    source_rows=library.get('_imageSources',{});cache=models.setdefault('_imageHashCache',{})
    query_hash=geometry._phash(geometry._decode(query_bytes),cv2)
    def source_path(i):
        if i in paths:return paths[i]
        row=entries[i];source=source_rows.get((str(row['sourceRevisionId']),str(row['fileId'])))
        if not source or source.get('fileSha256')!=row.get('fileSha256'):raise ValueError('SOURCE_MANIFEST_UNAVAILABLE')
        path=controlled_file(source.get('path',''),row.get('fileSha256'),models['allowedRoots']);paths[i]=path;return path
    scan_order=sorted(range(len(entries)),key=lambda i:(str(entries[i]['sourceRevisionId']),str(entries[i]['fileId'])))
    for i in scan_order[:config['maximumHashScans']]:
        row=entries[i]
        try:
            path=source_path(i)
            if row.get('fileSha256')==request['fileSha256']:exact.add(i);candidates.add(i);continue
            key=row['fileSha256']
            if key not in cache:
                if len(cache)>=512:cache.pop(next(iter(cache)))
                cache[key]=geometry._phash(geometry._decode(path.read_bytes()),cv2)
            distance=(query_hash^cache[key]).bit_count()
            if distance<=config['geometryPolicy']['phashCandidateDistance']:near[i]=distance;candidates.add(i)
        except (ValueError,OSError,KeyError):failures.add(i)
    chosen=sorted(candidates,key=lambda i:(i not in exact,near.get(i,100),-float(scores[i]),str(entries[i]['sourceRevisionId']),str(entries[i]['fileId'])))
    flags=[]
    if len(scan_order)>config['maximumHashScans']:flags.append('PARTIAL_IMAGE_HASH_SCAN')
    if len(chosen)>config['maximumVerifiedCandidates']:flags.append('PARTIAL_IMAGE_CANDIDATE_BUDGET')
    for i in chosen[:config['maximumVerifiedCandidates']]:
        row=entries[i];tick=time.perf_counter()
        try:verified=geometry.verify_images(query_bytes,source_path(i).read_bytes(),config['geometryPolicy'])
        except (ValueError,OSError,KeyError):
            failures.add(i);verified={'status':'SOURCE_UNAVAILABLE','scope':'UNRESOLVED','acceptedCorrespondence':False,'qualityFlags':['SOURCE_UNAVAILABLE']}
        verified['elapsedMs']=(time.perf_counter()-tick)*1000
        output['evidence'].append({'evidenceId':evidence_id(request['attemptId'],'image',[row['sourceRevisionId'],row['fileId']]),'evidenceType':'IMAGE_SIMILARITY','sourceScope':'LIBRARY',
            'queryFileId':request['fileId'],'sourceFileId':str(row['fileId']),'sourceWorkId':str(row['sourceWorkId']),'sourceRevisionId':str(row['sourceRevisionId']),
            'sourceTitle':row['title'],'sourceUrl':row.get('url'),'similarity':float(scores[i]),'threshold':config['threshold'],
            'denseAcceptedCandidate':bool(scores[i]>=config['threshold']),'acceptedCandidate':verified['acceptedCorrespondence'],
            'candidateRoutes':[route for route,yes in [('DINO_TOP20',i in ranked[:config['candidateK']]),('FILE_SHA256',i in exact),('PHASH',i in near)] if yes],
            'geometry':verified,'modelConfig':config})
    if failures:flags.append('PARTIAL_IMAGE_SOURCE_ACCESS')
    output.update(qualityFlags=flags,coverageStatus='PARTIAL' if flags else 'COMPLETE',hashScanned=min(len(entries),config['maximumHashScans']),verifiedCandidates=len(output['evidence']),elapsedMs=(time.perf_counter()-started)*1000)
    return output
