"""Require enough independently paired text on both sides of semantic support."""
import time
from pathlib import Path
from campus_shared.contracts import digest_json,file_sha256
from .text_refinement import independent


def configuration(refined):
    value={**refined,'baseRefinedConfigId':refined['configId'],
           'mutualEvidencePolicy':dict(minimumPairedCharacters=64,algorithmSha256=file_sha256(Path(__file__)))}
    value.pop('configId');value['configId']='text-'+digest_json(value)
    return value


def apply_guard(output):
    for item in output['evidence']:
        summary=item['semanticSummary']
        support=independent(sorted([w for w in item['semanticWindows'] if w.get('citationSupport')],key=lambda w:(-w['score'],-w['tfidfScore'],w['queryStart'])))
        paired=sum(min(w['queryEnd']-w['queryStart'],w['sourceEnd']-w['sourceStart']) for w in support)
        summary['pairedCharacters']=paired
        summary['minimumPairedCharacters']=64
        summary['beforeMutualSupportGuard']=summary['suspectedReuse']
        if paired<64:
            summary['suspectedReuse']=False
            for window in item['semanticWindows']:window['citationSupport']=False
    return output


def detect(request,library,models):
    from .text_refinement import detect as refined_detect
    start=time.perf_counter();output=refined_detect(request,library,models)
    if output['status']=='COMPLETED':apply_guard(output)
    output['elapsedMs']=(time.perf_counter()-start)*1000
    return output
