"""Sentence-aligned BERT evidence. Scores are auxiliary, never plagiarism probabilities."""
import re
from campus_shared.contracts import ContractError, evidence_id


def sentence_units(text, tokenizer, budget=60, minimum=12):
    units = []

    def emit(start, end):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end - start >= minimum:
            units.append({'start': start, 'end': end, 'text': text[start:end]})

    for sentence in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]*', text):
        start, end = sentence.span()
        if len(tokenizer(text[start:end], add_special_tokens=False)['input_ids']) <= budget:
            emit(start, end)
            continue
        # Long sentences are packed at clause boundaries; only a clause that exceeds
        # the budget itself is split using tokenizer offsets, without truncating text.
        fragments = []
        for clause in re.finditer(r'[^，,：:]+[，,：:]*', text[start:end]):
            a, b = start + clause.start(), start + clause.end()
            offsets = tokenizer(text[a:b], add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
            for i in range(0, len(offsets), budget):
                part = offsets[i:i + budget]
                if part:
                    fragments.append((a + part[0][0], a + part[-1][1]))
        pending = None
        for a, b in fragments:
            if pending is not None and len(tokenizer(text[pending:b], add_special_tokens=False)['input_ids']) > budget:
                emit(pending, previous_end)
                pending = None
            if pending is None:
                pending = a
            previous_end = b
        if pending is not None:
            emit(pending, previous_end)
    return units


def semantic_summary(windows, config):
    threshold = config.get('scoreThreshold', .5)
    floor = config.get('lexicalFloor', .25)
    selected = []
    for window in sorted(windows, key=lambda w: (-w['score'], -w.get('tfidfScore', 0), w['queryStart'])):
        if window['score'] < threshold or window.get('tfidfScore', 0) < floor:
            continue
        if window['queryEnd'] - window['queryStart'] < 12:
            continue
        if any((window['queryStart'] < old['queryEnd'] and old['queryStart'] < window['queryEnd']) or
               (window['sourceStart'] < old['sourceEnd'] and old['sourceStart'] < window['sourceEnd'])
               for old in selected):
            continue
        selected.append(window)
    characters = sum(w['queryEnd'] - w['queryStart'] for w in selected)
    return {'suspectedReuse': len(selected) >= config.get('minimumPairs', 2) and
            characters >= config.get('minimumCharacters', 64),
            'supportingPairs': len(selected), 'matchedQueryCharacters': characters,
            'scoreThreshold': threshold, 'lexicalFloor': floor,
            'minimumPairs': config.get('minimumPairs', 2),
            'minimumCharacters': config.get('minimumCharacters', 64)}


def add_semantic_evidence(output, index, text, models, config):
    import numpy as np
    policy = config['semanticPolicy']
    units = sentence_units(text, models['tokenizer'], policy['unitTokens'])
    # ponytail: bounded local evaluation, not exhaustive long-document semantics;
    # a larger retrieval strategy needs its own data and latency evaluation.
    limit = policy['maxQueryUnits']
    if len(units) > limit:
        positions = np.linspace(0, len(units) - 1, limit, dtype=int)
        chosen = [units[i] for i in positions]
    else:
        chosen = units
    descriptors = {evidence_id(output['attemptId'], 'text', sid): (sid, source)
                   for sid, source in index['documents'].items()}
    pairs, identities = [], []
    cache = index.setdefault('_sentenceCache', {})
    sources = 0
    for item in output['evidence']:
        item['literalAcceptedCandidate'] = item['acceptedCandidate']
        item['semanticSummary'] = {**semantic_summary([], policy), 'status':'NOT_EVALUATED'}
        sid, source = descriptors[item['evidenceId']]
        if source.get('sourceKind', 'BODY') != 'BODY' or sources >= policy['maxSources'] or not chosen:
            continue
        sources += 1
        if sid not in cache:
            source_units = sentence_units(source['text'], models['tokenizer'], policy['unitTokens'])
            cache[sid] = (source_units, index['vectorizer'].transform([u['text'] for u in source_units]) if source_units else None)
        source_units, source_matrix = cache[sid]
        item['semanticSummary']['status'] = 'EVALUATED'
        if not source_units:
            continue
        similarities = (index['vectorizer'].transform([u['text'] for u in chosen]) @ source_matrix.T).toarray()
        for qi, query in enumerate(chosen):
            for si in np.argsort(-similarities[qi], kind='stable')[:policy['candidatesPerUnit']]:
                if similarities[qi, si] < policy['alignmentMinimum'] or len(pairs) >= policy['maxPairs']:
                    continue
                reference = source_units[si]
                if len(models['tokenizer'](query['text'], reference['text'], add_special_tokens=True)['input_ids']) > 128:
                    raise ContractError('BERT_WINDOW_TOO_LONG', 'Sentence pair exceeds frozen BERT budget')
                pairs.append({'sentence1':query['text'], 'sentence2':reference['text'], 'label':0})
                identities.append((item, {'queryStart':query['start'], 'queryEnd':query['end'],
                    'sourceStart':reference['start'], 'sourceEnd':reference['end'],
                    'queryText':query['text'], 'sourceText':reference['text'],
                    'tfidfScore':float(similarities[qi, si]), 'alignment':'sentence-clause'}))
    scores = models['predictBert'](pairs)
    if len(scores) != len(identities) or not all(np.isfinite(s) and 0 <= s <= 1 for s in scores):
        raise ContractError('MODEL_OUTPUT_MISMATCH', 'BERT sentence scores are invalid')
    for (item, window), score in zip(identities, scores):
        item['semanticWindows'].append({**window, 'score':float(score)})
    for item in output['evidence']:
        if item['semanticSummary']['status'] != 'EVALUATED':
            continue
        item['semanticSummary'] = {**semantic_summary(item['semanticWindows'], policy), 'status':'EVALUATED',
                                  'evaluatedPairs':len(item['semanticWindows'])}
        # Retain all evaluated windows in the immutable report for audit; UI may collapse them.
        item['semanticWindows'].sort(key=lambda w: (-w['score'], w['queryStart'], w['sourceStart']))
    output['semanticEvaluation'] = {'method':'sentence-clause', 'availableQueryUnits':len(units),
        'evaluatedQueryUnits':len(chosen), 'evaluatedSources':sources, 'evaluatedPairs':len(pairs),
        'maxPairs':policy['maxPairs'], 'scope':'Top BODY candidates and selected sentence pairs only; not full semantic coverage'}
