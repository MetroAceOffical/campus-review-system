"""Apply exact, nonoverlapping model corrections; never infer an ambiguous offset."""
import json
import re

def correction_text(text,raw):
    match=re.search(r'\{.*\}',raw,re.S)
    if not match:raise ValueError('INVALID_CORRECTIONS')
    value=json.loads(match.group());edits=value.get('corrections')
    if not isinstance(edits,list) or len(edits)>20:raise ValueError('INVALID_CORRECTIONS')
    ranges=[]
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)!={'original','replacement'}:raise ValueError('INVALID_CORRECTION')
        old,new=edit['original'],edit['replacement']
        if not isinstance(old,str) or not isinstance(new,str) or not 1<=len(old)<=12 or not 1<=len(new)<=12:
            raise ValueError('INVALID_CORRECTION_LENGTH')
        if old==new:continue
        if text.count(old)!=1:raise ValueError('AMBIGUOUS_CORRECTION')
        start=text.index(old);end=start+len(old)
        if any(start<b and end>a for a,b,_ in ranges):raise ValueError('OVERLAPPING_CORRECTIONS')
        ranges.append((start,end,new))
    for start,end,new in sorted(ranges,reverse=True):text=text[:start]+new+text[end:]
    return text
