"""Conservative, disclosed rule evidence for training negatives; never human-gold labels."""
import difflib
import re
from collections import Counter
from datetime import date
from corpus import normalized

RULE_VERSION='3'

PATTERNS={
 'RESEARCH':r'研究(?!生)|论文|实验|课题|科研',
 'ART_EXHIBITION':r'展览|展演|影像展|艺术展|摄影作品|创作',
 'TEACHING':r'培训|授课|讲授|课程改革|教学设计|学习班',
 'VISIT':r'走访|调研|考察|来访|会见|参观',
 'AGREEMENT':r'签约|签署|协议|共建',
 'ADMISSION':r'招生|录取|考试|报名|面试',
 'VOLUNTEER':r'志愿|支教|义诊|助老|帮扶',
 'EQUIPMENT':r'维护|检修|采购|设备故障|维修',
}


def dominant_process(text):
    counts=Counter({key:len(re.findall(pattern,text)) for key,pattern in PATTERNS.items()})
    ordered=counts.most_common()
    if not ordered or ordered[0][1]<2 or len(ordered)>1 and ordered[0][1]==ordered[1][1]:return None
    return ordered[0][0]


def process_facts(text):
    facts=[]
    pattern=r'(?:提出|研发|研制|开发|设计|构建|建立|合成|制备|揭示|证明|发现|测量|分析|实现|展示|展出|创作|演奏|演出|培育|签署)(?:了)?(?P<object>[^，。；\n]{6,40})'
    for match in re.finditer(pattern,text):
        argument=re.sub(r'[“《][^”》]*[”》]','',match['object'])
        argument=re.sub(r'\d+','',normalized(argument))
        if len(argument)>=12:facts.append({'start':match.start(),'end':match.end(),'text':match[0],'argument':argument})
    return facts


def disjoint_process_facts(left,right):
    a,b=process_facts(left),process_facts(right)
    for x in a:
        for y in b:
            xgrams={x['argument'][i:i+2] for i in range(len(x['argument'])-1)}
            ygrams={y['argument'][i:i+2] for i in range(len(y['argument'])-1)}
            if len(xgrams&ygrams)/max(1,len(xgrams|ygrams))<.2 and max(block.size for block in difflib.SequenceMatcher(None,x['argument'],y['argument'],autojunk=False).get_matching_blocks())<12:
                return [x,y]
    return []


def substantive_facts(text,category):
    if category is None:return []
    facts=[]
    for match in re.finditer(r'[^。；\n]+[。；]?',text):
        sentence=match[0]
        if len(normalized(sentence))>=24 and len(re.findall(PATTERNS[category],sentence))>=2:
            facts.append({'start':match.start(),'end':match.end(),'text':sentence})
    return facts


def distinct_titles(left,right):
    def grams(row):
        title=normalized(row.get('title') or '').replace(row.get('institutionName') or '\0','')
        for common in ['大学','学院','学校']:title=title.replace(common,'')
        return {title[i:i+3] for i in range(max(0,len(title)-2))}
    a,b=grams(left),grams(right)
    return len(a)>=8 and len(b)>=8 and len(a&b)/max(1,len(a|b))<.12


def assess_difference(left,right):
    a,b=normalized(left['text']),normalized(right['text'])
    names=lambda text:set(re.findall(r'[“《]([^”》]{3,40})[”》]',text))
    left_names,right_names=names(left['text']),names(right['text'])
    left_process,right_process=dominant_process(left['text']),dominant_process(right['text'])
    process_evidence=disjoint_process_facts(left['text'],right['text'])
    longest=max((block.size for block in difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks()),default=0)
    def published(row):
        match=re.search(r'\d{4}-\d{2}-\d{2}',str(row.get('publishedAt') or ''))
        try:return date.fromisoformat(match[0]) if match else None
        except ValueError:return None
    dates=[published(row) for row in (left,right)]
    named_process_route=bool(left_names and right_names and not left_names&right_names and left_process and right_process and (left_process!=right_process or process_evidence) and all(dates) and abs((dates[0]-dates[1]).days)>=30)
    direct_facts=[substantive_facts(left['text'],left_process),substantive_facts(right['text'],right_process)]
    title_process_route=bool(left_process and right_process and left_process!=right_process and all(direct_facts) and distinct_titles(left,right))
    checks={'differentSource':left['sourceId']!=right['sourceId'],
            'differentSourceCluster':left['sourceClusterId']!=right['sourceClusterId'],
            'differentEventGroup':left['eventClusterId']!=right['eventClusterId'],
            'supportedContentDifference':named_process_route or title_process_route,
            'noLongNarrativeCopy':longest<24}
    spans=[]
    for side,row in [('query_source',left),('candidate_source',right)]:
        # These are exact source-window facts, not a generated interpretation of them.
        spans.append({'side':side,'start':0,'end':len(row['text']),'text':row['text']})
    return {'ruleVersion':RULE_VERSION,'supported':all(checks.values()),'checks':checks,'factSpans':spans,'processCategories':[left_process,right_process],'specificProcessFacts':process_evidence,
            'evidenceRoutes':{'namedSubjectProcessAndDate':named_process_route,'distinctTitleAndExplicitProcess':title_process_route},'substantiveFactSpans':direct_facts,
            'namedSubjects':[sorted(left_names),sorted(right_names)],'longestLiteralOverlap':longest,
            'labelScope':'Conservative rule-supported training negative, not human gold or independent test truth. Semantic-only common provenance may still be missed.'}
