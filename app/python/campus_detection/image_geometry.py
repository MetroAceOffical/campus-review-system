"""Optional image correspondence evidence; inactive in the existing image-v1 pipeline.

Requires the approved isolated environment's OpenCV. Defaults are engineering
parameters, not a calibrated product operating point or a correctness guarantee.
"""
import hashlib
import io
import json

import numpy as np
from PIL import Image,ImageOps

POLICY={'longEdge':1280,'features':5000,'ratioTest':.75,'minimumMatches':12,
        'minimumInliers':10,'minimumInlierRatio':.45,'ransacPixels':3.,
        'wholeCoverage':.60,'localMinimumCoverage':.04,'phashCandidateDistance':6}


def _decode(payload):
    if not payload or len(payload)>10*1024*1024:raise ValueError('Image byte budget exceeded or empty')
    with Image.open(io.BytesIO(payload)) as source:
        if source.width*source.height>20_000_000:raise ValueError('Image pixel budget exceeded')
        image=ImageOps.exif_transpose(source).convert('RGB')
        try:return np.array(image)
        finally:image.close()


def _phash(rgb,cv):
    gray=cv.cvtColor(rgb,cv.COLOR_RGB2GRAY)
    coefficients=cv.dct(cv.resize(gray,(32,32),interpolation=cv.INTER_AREA).astype(np.float32))[:8,:8].reshape(-1)
    bits=coefficients>np.median(coefficients[1:])
    return sum(int(bit)<<index for index,bit in enumerate(bits))


def _features(rgb,policy,cv):
    height,width=rgb.shape[:2];scale=min(1.,policy['longEdge']/max(width,height))
    gray=cv.cvtColor(rgb,cv.COLOR_RGB2GRAY)
    if scale<1:gray=cv.resize(gray,(max(1,round(width*scale)),max(1,round(height*scale))),interpolation=cv.INTER_AREA)
    keypoints,descriptors=cv.SIFT_create(nfeatures=policy['features']).detectAndCompute(gray,None)
    return keypoints,descriptors,(gray.shape[1]/width,gray.shape[0]/height)


def _region(points,scale,width,height,cv):
    points=points.reshape(-1,2).copy()
    points[:,0]=np.clip((points[:,0]+.5)/scale[0]-.5,0,width)
    points[:,1]=np.clip((points[:,1]+.5)/scale[1]-.5,0,height)
    hull=cv.convexHull(points.astype(np.float32)).reshape(-1,2)
    coverage=float(cv.contourArea(hull)/(width*height)) if len(hull)>=3 else 0.
    return hull.tolist(),min(1.,max(0.,coverage))


def original_homography(working,qscale,sscale):
    query_to_work=np.array([[qscale[0],0.,.5*qscale[0]-.5],[0.,qscale[1],.5*qscale[1]-.5],[0.,0.,1.]])
    work_to_source=np.array([[1/sscale[0],0.,.5/sscale[0]-.5],[0.,1/sscale[1],.5/sscale[1]-.5],[0.,0.,1.]])
    return work_to_source@working@query_to_work


def verify_images(query_bytes,source_bytes,policy=None):
    import cv2 as cv
    policy={**POLICY,**(policy or {})}
    query,source=_decode(query_bytes),_decode(source_bytes)
    qh,qw=query.shape[:2];sh,sw=source.shape[:2]
    result={'schemaVersion':'image-geometry-v1','status':'INSUFFICIENT_EVIDENCE','scope':'UNRESOLVED',
            'acceptedCorrespondence':False,'identityBasis':None,'matches':0,'inliers':0,'inlierRatio':0.,
            'querySpatialCoverage':0.,'sourceSpatialCoverage':0.,'queryRegion':[],'sourceRegion':[],
            'querySize':{'width':qw,'height':qh},'sourceSize':{'width':sw,'height':sh},
            'coordinateFrame':'EXIF_ORIENTED_ORIGINAL_PIXELS','coverageMeasure':'convex_hull_of_geometric_inliers_not_pixel_copy_percentage',
            'qualityFlags':[],'policy':policy,'opencvVersion':cv.__version__,'operatingPointCalibrated':False}
    result['policyId']=hashlib.sha256(json.dumps({'policy':policy,'opencvVersion':cv.__version__},sort_keys=True).encode()).hexdigest()
    identity='FILE_SHA256' if hashlib.sha256(query_bytes).digest()==hashlib.sha256(source_bytes).digest() else 'DECODED_PIXELS' if query.shape==source.shape and np.array_equal(query,source) else None
    if identity:
        result.update(status='CORRESPONDENCE_SUPPORTED',scope='WHOLE_IMAGE',acceptedCorrespondence=True,identityBasis=identity,
                      querySpatialCoverage=1.,sourceSpatialCoverage=1.,queryRegion=[[0,0],[qw,0],[qw,qh],[0,qh]],sourceRegion=[[0,0],[sw,0],[sw,sh],[0,sh]])
        return result
    distance=(_phash(query,cv)^_phash(source,cv)).bit_count()
    result.update(phashDistance=distance,phashNearCandidate=distance<=policy['phashCandidateDistance'])
    qpoints,qdesc,qscale=_features(query,policy,cv);spoints,sdesc,sscale=_features(source,policy,cv)
    result.update(queryKeypoints=len(qpoints),sourceKeypoints=len(spoints))
    if qdesc is None or sdesc is None or min(len(qdesc),len(sdesc))<policy['minimumMatches']:
        result['qualityFlags'].append('LOW_TEXTURE');return result
    # SIFT uses Euclidean descriptors, not the Hamming distance used for ORB.
    matcher=cv.BFMatcher(cv.NORM_L2)
    def ratio_matches(left,right):
        return [neighbors[0] for neighbors in matcher.knnMatch(left,right,k=2) if len(neighbors)==2 and neighbors[0].distance<policy['ratioTest']*neighbors[1].distance]
    backward={(match.trainIdx,match.queryIdx) for match in ratio_matches(sdesc,qdesc)}
    matches=[match for match in ratio_matches(qdesc,sdesc) if (match.queryIdx,match.trainIdx) in backward]
    result['matches']=len(matches)
    if len(matches)<policy['minimumMatches']:
        result['qualityFlags'].append('TOO_FEW_UNIQUE_MATCHES');return result
    left=np.float32([qpoints[match.queryIdx].pt for match in matches]).reshape(-1,1,2)
    right=np.float32([spoints[match.trainIdx].pt for match in matches]).reshape(-1,1,2)
    homography,mask=cv.findHomography(left,right,cv.RANSAC,policy['ransacPixels'],maxIters=3000,confidence=.995)
    if homography is None or mask is None or not np.isfinite(homography).all() or abs(np.linalg.det(homography))<1e-10:
        result['qualityFlags'].append('DEGENERATE_GEOMETRY');return result
    keep=mask.reshape(-1).astype(bool);inliers=int(keep.sum());ratio=inliers/len(matches)
    result.update(inliers=inliers,inlierRatio=ratio)
    if inliers<policy['minimumInliers'] or ratio<policy['minimumInlierRatio']:
        result['qualityFlags'].append('WEAK_GEOMETRY');return result
    query_region,qcoverage=_region(left[keep],qscale,qw,qh,cv)
    source_region,scoverage=_region(right[keep],sscale,sw,sh,cv)
    result.update(queryRegion=query_region,sourceRegion=source_region,querySpatialCoverage=qcoverage,sourceSpatialCoverage=scoverage)
    if min(qcoverage,scoverage)>=policy['wholeCoverage']:scope='WHOLE_IMAGE'
    elif max(qcoverage,scoverage)>=policy['wholeCoverage'] and min(qcoverage,scoverage)>=policy['localMinimumCoverage']:scope='LOCAL_REGION'
    else:
        result['qualityFlags'].append('INSUFFICIENT_SPATIAL_SUPPORT');return result
    # Coordinates of H are converted from the bounded working images to originals.
    result.update(status='CORRESPONDENCE_SUPPORTED',scope=scope,acceptedCorrespondence=True,
                  queryToSourceHomography=original_homography(homography,qscale,sscale).tolist())
    return result
