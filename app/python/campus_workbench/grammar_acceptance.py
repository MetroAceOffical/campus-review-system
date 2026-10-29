"""Keep model edits supported as corrections, rather than optional rewriting."""
import re
from .phonetic_spelling import sounds


def accept_edit(text,start,end,replacement,lexicon):
    old=text[start:end]
    if not replacement and old in ('已经','通过','进行','以及','同时','为了','由于','表示','开展') and (text[max(0,start-len(old)):start]==old or text[end:end+len(old)]==old):
        return True
    if len(old)!=1 or len(replacement)!=1 or not re.fullmatch(r'[\u4e00-\u9fff]',old) or not re.fullmatch(r'[\u4e00-\u9fff]',replacement):
        return False
    if old in '的地得' and replacement in '的地得':return True
    if not sounds(old)&sounds(replacement):return False
    for size in (2,3,4):
        for left in range(max(0,start-size+1),min(start+1,len(text)-size+1)):
            raw=text[left:left+size]
            if not re.fullmatch(r'[\u4e00-\u9fff]+',raw):continue
            corrected=raw[:start-left]+replacement+raw[start-left+1:]
            if lexicon.counts.get(corrected,0)>=max(5,20*(lexicon.counts.get(raw,0)+1)):return True
    return False
