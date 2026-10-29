"""Auditable navigation exclusions and anchored contextual corroboration."""
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from campus_shared.contracts import digest_json, file_sha256
from .semantic import semantic_summary


def footer(text):
    lines=text.splitlines(keepends=True);offsets=[];position=0
    for line in lines:offsets.append(position);position+=len(line)
    for i in range(len(lines)-1,-1,-1):
        link=re.fullmatch(r'本文链接[：:][ \t]*(https?://\S+)?',lines[i].strip())
        if not link:continue
        j=i+1
        url=link.group(1)
        if not url:
            if j>=len(lines) or not re.fullmatch(r'https?://\S+',lines[j].strip()):continue
            url=lines[j].strip();j+=1
        count=0
        while j<len(lines) and count<2:
            navigation=re.fullmatch(r'(?:上一篇|下一篇)\s*[>：:](.*)',lines[j].strip())
            if not navigation:break
            j+=1;count+=1
            if not navigation.group(1).strip():
                if j>=len(lines) or re.match(r'(?:上一篇|下一篇|收藏|分享)',lines[j].strip()):break
                j+=1
        if not count or j>=len(lines):continue
        if lines[j].strip()=='收藏' and j+1<len(lines) and lines[j+1].strip()=='分享':j+=1
        elif not re.fullmatch(r'收藏\s+分享',lines[j].strip()):continue
        start=i
        while start>0 and re.fullmatch(r'(?:点赞\(\d+\)|本文分类[：:].*|本文标签[：:].*|浏览次数[：:].*|发布日期[：:].*)',lines[start-1].strip()):start-=1
        end=offsets[j]+len(lines[j])
        return offsets[start],end,text[end:].strip(),url
    return None


def chrome_ranges(text,shared_tails=()):
    block=footer(text)
    if not block:return []
    start,end,tail,_=block
    # A continuation after the navigation controls is content unless the entire
    # suffix is a confirmed repeated recommendation panel in reference pages.
    return [(start,len(text) if tail and tail in shared_tails else end)]


def reference_chrome(documents):
    panels=defaultdict(set);blocks={}
    for key,source in documents.items():
        block=footer(source['text'])
        if block:
            blocks[key]=block;_,_,tail,url=block
            if tail:panels[(urlsplit(url).hostname,tail)].add(url.rstrip('/'))
    result={}
    for key,(_,_,tail,url) in blocks.items():
        shared={tail} if len(panels[(urlsplit(url).hostname,tail)])>=3 else set()
        result[key]=chrome_ranges(documents[key]['text'],shared)
    return result


def intersects(start, end, ranges):
    return any(start < right and left < end for left, right in ranges)


def literal_pieces(matches, query_exclusions, source_exclusions, minimum):
    result = []
    for match in matches:
        start, end, source = match['queryStart'], match['queryEnd'], match['sourceStart']
        excluded = list(query_exclusions) + [(start+a-source, start+b-source) for a,b in source_exclusions]
        cuts = sorted({start,end} | {max(start,a) for a,b in excluded if a<end and start<b} |
                      {min(end,b) for a,b in excluded if a<end and start<b})
        for left,right in zip(cuts,cuts[1:]):
            if right-left < minimum or intersects(left,right,excluded):
                continue
            a,b = left-start,right-start
            result.append(dict(match,queryStart=left,queryEnd=right,sourceStart=source+a,sourceEnd=source+b,
                               queryText=match['queryText'][a:b],sourceText=match['sourceText'][a:b]))
    return result


def independent(windows):
    chosen = []
    for window in windows:
        if window['queryEnd']-window['queryStart'] < 12:
            continue
        if any(window['queryStart']<old['queryEnd'] and old['queryStart']<window['queryEnd'] or
               window['sourceStart']<old['sourceEnd'] and old['sourceStart']<window['sourceEnd'] for old in chosen):
            continue
        chosen.append(window)
    return chosen


def summarize(windows):
    order = lambda w: (-w['score'],-w['tfidfScore'],w['queryStart'])
    anchors = independent(sorted([w for w in windows if w['score']>=.5 and w['tfidfScore']>=.25],key=order))
    summary = semantic_summary(anchors,{})
    chosen = anchors
    strong = any(w['tfidfScore']>=.35 and w['queryEnd']-w['queryStart']>=32 and
                 w['sourceEnd']-w['sourceStart']>=24 and
                 min(w['queryEnd']-w['queryStart'],w['sourceEnd']-w['sourceStart']) /
                 max(w['queryEnd']-w['queryStart'],w['sourceEnd']-w['sourceStart']) >= .5 for w in anchors)
    if not summary['suspectedReuse'] and strong:
        weak = sorted([w for w in windows if w['score']>=.6 and .15<=w['tfidfScore']<.25],key=order)
        candidate = independent(anchors+weak)
        characters = sum(w['queryEnd']-w['queryStart'] for w in candidate)
        weighted = sum(w['tfidfScore']*(w['queryEnd']-w['queryStart']) for w in candidate)/max(1,characters)
        if len(candidate)>=2 and characters>=64 and weighted>=.25:
            chosen = candidate
            summary.update(suspectedReuse=True,supportingPairs=len(chosen),matchedQueryCharacters=characters)
    summary.update(selectionMethod='anchored-context-v1',corroborated=chosen is not anchors)
    return summary,chosen


def configuration(context):
    value = {**context,'method':'navigation-aware-anchored-context-20261029','baseContextConfigId':context['configId'],
             'refinementAlgorithmSha256':file_sha256(Path(__file__)),
             'refinementPolicy':dict(version='anchored-context-v1',anchorScore=.5,anchorLexical=.35,
                 anchorQueryCharacters=32,anchorSourceCharacters=24,anchorLengthBalance=.5,
                 corroboratingScore=.6,corroboratingLexical=.15,weightedLexical=.25,
                 minimumPairs=2,minimumCharacters=64,navigation='reference-contiguous-controls-and-three-url-identical-panel',
                 queryMarkersTrusted=False)}
    value.pop('configId');value['configId']='text-'+digest_json(value)
    return value


def refine(output, library, text):
    from .models import frozen_text_helpers
    helper = frozen_text_helpers()
    sources = {str(d.get('sourceKey',d['sourceRevisionId'])):d for d in library['documents']}
    # Author-supplied markers cannot disable checking of their following text.
    query_exclusions = []
    source_chrome = reference_chrome(sources)
    params = output['actualConfig']['params']
    for item in output['evidence']:
        key=item['sourceKey'] if item['sourceKey'] in sources else str(item['sourceRevisionId'])
        source_exclusions = source_chrome.get(key,[])
        item['rawMatches'] = item['matches']
        item['rawLiteralSummary'] = item['literalSummary']
        item['rawLiteralAcceptedCandidate'] = item.get('literalAcceptedCandidate',item['acceptedCandidate'])
        item['rawSemanticSummary'] = item['semanticSummary']
        item['matches'] = literal_pieces(item['matches'],query_exclusions,source_exclusions,params['literal_minimum'])
        mapped = [dict(text=m['queryText'],q_start=m['queryStart'],q_end=m['queryEnd'],s_start=m['sourceStart'],s_end=m['sourceEnd']) for m in item['matches']]
        summary = helper.evidence_summary(mapped,len(text))
        item['literalSummary'] = summary
        accepted = summary['matched_characters']>=params['min_chars'] and (summary['query_character_coverage']>=params['min_coverage'] or summary['longest_match']>=2*params['min_chars'])
        item['literalAcceptedCandidate'] = item['acceptedCandidate'] = bool(accepted)
        windows = []
        for window in item['semanticWindows']:
            excluded = intersects(window['queryStart'],window['queryEnd'],query_exclusions) or intersects(window['sourceStart'],window['sourceEnd'],source_exclusions)
            window['excludedAsNavigation'] = excluded
            if not excluded:windows.append(window)
        summary,support = summarize(windows)
        summary.update(status=item['rawSemanticSummary'].get('status','NOT_EVALUATED'),evaluatedPairs=len(item['semanticWindows']))
        item['semanticSummary'] = summary
        identities = {(w['queryText'],w['sourceText']) for w in support}
        for window in item['semanticWindows']:
            window['citationSupport'] = not window['excludedAsNavigation'] and (window['queryText'],window['sourceText']) in identities
        item['navigationExclusions'] = dict(queryRanges=query_exclusions,sourceRanges=source_exclusions)
    return output


def detect(request, library, models):
    from .contextual_text import detect as contextual_detect
    start = time.perf_counter()
    output = contextual_detect(request,library,models)
    if output['status']=='COMPLETED':refine(output,library,request['text'])
    output['elapsedMs'] = (time.perf_counter()-start)*1000
    return output
