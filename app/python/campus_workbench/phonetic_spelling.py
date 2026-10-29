"""Conservative homophone candidates supported by existing train-document contexts."""
import difflib,functools,json,re
from collections import defaultdict
from pathlib import Path
from campus_shared.contracts import file_sha256


@functools.lru_cache(maxsize=8192)
def sounds(character):
    from pypinyin import pinyin,Style
    return frozenset(pinyin(character,style=Style.NORMAL,heteronym=True)[0])


class SpellingLexicon:
    def __init__(self,counts,minimum_candidate=5,minimum_context=2):
        self.counts=counts;self.minimum_context=minimum_context;self.index=defaultdict(list)
        for word,frequency in counts.items():
            if frequency<minimum_candidate or len(word) not in (2,3,4):continue
            for i in range(len(word)):self.index[(i,word[:i],word[i+1:])].append(word)


@functools.lru_cache(maxsize=1)
def load_lexicon(folder):
    folder=Path(folder);ready=json.loads((folder/'READY').read_text(encoding='utf-8'))
    if file_sha256(folder/'lexicon.json')!=ready['lexicon.json']:raise ValueError('Spelling lexicon changed')
    value=json.loads((folder/'lexicon.json').read_text(encoding='utf-8'))
    return SpellingLexicon(value['counts'],value['minimumCandidateDocuments'],value['minimumContextDocuments'])


def spelling_edits(text,counts):
    lex=counts if isinstance(counts,SpellingLexicon) else SpellingLexicon(counts)
    proposals=defaultdict(dict)
    for match in re.finditer(r'[\u4e00-\u9fff]+',text):
        part=match.group()
        for size in (2,3,4):
            for start in range(len(part)-size+1):
                raw=part[start:start+size]
                for position,old in enumerate(raw):
                    at=start+position
                    for word in lex.index.get((position,raw[:position],raw[position+1:]),[]):
                        if lex.counts[word]<20*(lex.counts.get(raw,0)+1):continue
                        new=word[position]
                        if old==new or not sounds(old)&sounds(new):continue
                        corrected=part[:at]+new+part[at+1:]
                        contexts=[corrected[j:j+3] for j in range(max(0,at-2),min(at+1,len(part)-2))]
                        if not contexts or not all(lex.counts.get(context,0)>=lex.minimum_context for context in contexts):continue
                        proposals[match.start()+at][new]=word
    # Multiple different qualifying corrections are ambiguity, not a forced choice.
    return [dict(start=at,end=at+1,original=text[at],replacement=next(iter(options))) for at,options in sorted(proposals.items()) if len(options)==1]


def guided_edits(text,raw,parser,lexicon):
    """Recover only places the neural model itself attempted to change.

    Normal unchanged sentences are never scanned into independent suggestions.
    Preserve grammatical edits unless a non-homophone one-character substitution
    has a unique, independently attested homophone alternative.
    """
    recovered=set()
    try:
        value,edits=parser(text,raw)
    except ValueError as failure:
        if str(failure) not in ('CONTENT_WORD_DELETION','EXCESSIVE_REWRITE'):raise
        value=json.loads(re.search(r'\{.*\}',raw,re.S).group())['corrected']
        changed=[(a,b) for tag,a,b,c,d in difflib.SequenceMatcher(None,text,value,autojunk=False).get_opcodes() if tag!='equal']
        fallback=[e for e in spelling_edits(text,lexicon) if any(a<=e['start']<b for a,b in changed)]
        if not fallback:raise failure
        substitutions=[(e['start'],e['end'],e['replacement']) for e in fallback];recovered={e['start'] for e in fallback}
    else:
        if not edits:return value,edits,recovered
        fallback={e['start']:e for e in spelling_edits(text,lexicon)}
        substitutions=[]
        for tag,a,b,c,d in edits:
            replacement=value[c:d]
            if tag=='replace' and b-a==d-c==1 and re.fullmatch(r'[\u4e00-\u9fff]',text[a:b]) and re.fullmatch(r'[\u4e00-\u9fff]',replacement) and not sounds(text[a])&sounds(replacement) and a in fallback:
                replacement=fallback[a]['replacement'];recovered.add(a)
            substitutions.append((a,b,replacement))
    corrected=text
    for a,b,replacement in sorted(substitutions,reverse=True):corrected=corrected[:a]+replacement+corrected[b:]
    value,edits=parser(text,json.dumps(dict(corrected=corrected),ensure_ascii=False))
    return value,edits,recovered
