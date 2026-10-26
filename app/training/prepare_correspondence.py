"""Freeze supported campus pairs without starting a GPU or relabelling unknowns."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from corpus import normalized,read_jsonl,eligible_correspondence
from construct_correspondence import verify_ready,rewrite_checks
from mine_correspondence_candidates import aligned_windows
from negative_basis import assess_difference

ROOT=Path(__file__).resolve().parents[2]


def control_budget(generated_count):
    # Each control type is at most 25% of positives; generated chunks remain >=50%.
    return generated_count//2


def generated_pairs(originals,records,tokenizer,stats):
    for record in records:
        if len(record['sourceIds'])!=1:raise ValueError('Generation must map to one original segment')
        source_id=record['sourceIds'][0];original=originals[source_id]
        span=record['sourceOffsets'];text=original['text'][span['start']:span['end']]
        if original.get('split')!='train' or text!=record['source'] or span['start']<0 or span['end']>len(original['text']):raise ValueError('Generation source provenance mismatch')
        entities=[original['institutionName']]+re.findall(r'[“《]([^”》]{2,30})[”》]',text)
        checks=rewrite_checks(text,record['query'],entities,require_rewording=False)
        if not record.get('checks',{}).get('accepted') or not checks['accepted']:raise ValueError('Failed generation cannot become correspondence truth')
        stats['acceptedGenerationSegments']+=1
        # Non-overlapping query slices retain the entire checked source segment.
        # Arbitrary source slices cannot be aligned to paraphrases by character ratio.
        for window in aligned_windows(record['query'],tokenizer,window=120,overlap=0):
            if len(normalized(window['text']))<32:stats['shortGeneratedQueries']+=1;continue
            if len(tokenizer(window['text'],text,truncation=False)['input_ids'])>512:stats['oversizeGeneratedPairs']+=1;continue
            yield {'taskType':'CONTENT_CORRESPONDENCE','target':1,'labelOrigin':'controlled_construction',
                   'labelConfidence':'known','humanVerified':False,'split':'train','sourceIds':[source_id],
                   'sourceClusterId':original['sourceClusterId'],'eventClusterId':original['eventClusterId'],
                   'query':window['text'],'source':text,'sourceOffsets':span,
                   'queryOffsets':{'start':window['start'],'end':window['end']},
                   'transformationKind':rewrite_checks(text,window['text'],[],require_rewording=False)['transformationKind'],
                   'constructionParent':{'query':record['query'],'sourceOffsets':span,'checks':checks,
                                         'generatorRevision':record.get('generatorRevision')}}


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    from transformers import AutoTokenizer
    parser=argparse.ArgumentParser()
    parser.add_argument('--generation',type=Path,required=True)
    parser.add_argument('--negatives',type=Path,required=True)
    parser.add_argument('--partitions',type=Path,default=ROOT/'runtime/datasets/campus-partitions-20261026-v1')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if (args.output/'READY').exists():raise RuntimeError('Prepared version already frozen')
    state=json.loads((args.generation/'status.json').read_text(encoding='utf-8'))
    if state['state']!='TRAIN_CONSTRUCTION_FINISHED':raise RuntimeError('Wait for completed generation export; never read the live partial database')
    partition_hashes=verify_ready(args.partitions);negative_hashes=verify_ready(args.negatives)
    config=json.loads((args.generation/'config.json').read_text(encoding='utf-8'))
    if config['sourceSplit']!='train' or config['partitionTrainSha256']!=partition_hashes['train.jsonl']:raise ValueError('Generation partition identity differs')
    negative_manifest=json.loads((args.negatives/'manifest.json').read_text(encoding='utf-8'))
    if negative_manifest['sourceTrainSha256']!=partition_hashes['train.jsonl']:raise ValueError('Negative partition identity differs')
    generation_hashes={name:sha(args.generation/name) for name in ['config.json','status.json','paragraph-pairs.jsonl','whole-rewrites.jsonl','generation-code.py']}
    originals={row['documentId']:row for row in read_jsonl(args.partitions/'train.jsonl')}
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'runtime/experiments/route-b-development-20261026/model',local_files_only=True,trust_remote_code=False,use_fast=True)
    args.output.mkdir(parents=True,exist_ok=True)
    stats=Counter();classes=Counter();kinds=Counter();seen={};parents=set();events=set();accepted_generated=0
    with (args.output/'pairs.jsonl').open('w',encoding='utf-8') as stream:
        def emit(row):
            key=tuple(sorted((normalized(row['query']),normalized(row['source']))))
            if key in seen:
                if seen[key]!=row['target']:raise ValueError('Conflicting labels for the same normalized pair')
                stats['duplicateOrReversePairsExcluded']+=1;return False
            if not eligible_correspondence(row) or row['split']!='train':raise ValueError('Unsupported label')
            if len(tokenizer(row['query'],row['source'],truncation=False)['input_ids'])>512:stats['oversizePairsExcluded']+=1;return False
            seen[key]=row['target'];classes[row['target']]+=1;kinds[row.get('transformationKind','SUPPORTED_NEGATIVE')]+=1
            parents.update(row['sourceIds']);events.add(row['eventClusterId'])
            row['pairId']=hashlib.sha256(('\0'.join(key)).encode()).hexdigest()
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');return True
        for row in generated_pairs(originals,read_jsonl(args.generation/'paragraph-pairs.jsonl'),tokenizer,stats):
            if row['transformationKind']=='COPY_CONTROL':stats['generatedCopySegmentsExcludedFromParaphrases']+=1;continue
            accepted_generated+=emit(row)
        budgets={'COPY_CONTROL':control_budget(accepted_generated),'SENTENCE_REORDER':control_budget(accepted_generated)}
        for original in sorted(originals.values(),key=lambda row:hashlib.sha256(row['documentId'].encode()).hexdigest()):
            for window in aligned_windows(original['text'],tokenizer,window=240,overlap=0):
                if len(normalized(window['text']))<64:continue
                text=window['text'];sentences=[part for part in re.split(r'(?<=[。！？；])',text) if part]
                queries=[('COPY_CONTROL',text)]
                if len(sentences)>=2:queries.append(('SENTENCE_REORDER',''.join(sentences[1:]+sentences[:1])))
                for kind,query in queries:
                    if budgets[kind]<=0:continue
                    row={'taskType':'CONTENT_CORRESPONDENCE','target':1,'split':'train','labelOrigin':'controlled_construction',
                         'labelConfidence':'known','humanVerified':False,'sourceIds':[original['documentId']],
                         'sourceClusterId':original['sourceClusterId'],'eventClusterId':original['eventClusterId'],
                         'query':query,'source':text,'sourceOffsets':{'start':window['start'],'end':window['end']},'transformationKind':kind}
                    if emit(row):budgets[kind]-=1
            if not any(budgets.values()):break
        for row in read_jsonl(args.negatives/'negative-pairs.jsonl'):
            for field in ['positiveSource','candidateSource']:
                item=row[field];original=originals[item['sourceId']]
                if item['text']!=original['text'][item['start']:item['end']] or any(item[key]!=original[key] for key in ['sourceClusterId','eventClusterId']):raise ValueError('Negative original range or identity changed')
            if row['query']!=row['positiveSource']['text'] or row['source']!=row['candidateSource']['text'] or row['sourceIds']!=[row['candidateSource']['sourceId']]:raise ValueError('Negative training text changed')
            if row['sourceOffsets']!={'start':row['candidateSource']['start'],'end':row['candidateSource']['end']}:raise ValueError('Negative range changed')
            if not assess_difference(row['positiveSource'],row['candidateSource'])['supported']:raise ValueError('Negative content evidence no longer holds')
            emit(row)
    if any(sha(args.generation/name)!=digest for name,digest in generation_hashes.items()):raise ValueError('Generation export changed while reading')
    total=sum(classes.values());scale_ready=total>=20000 and min(classes[0],classes[1])>=total*.2
    manifest={'state':'FORMAL_PAIR_SHARD_READY' if scale_ready else 'PREPARED_BELOW_FORMAL_SCALE_OR_BALANCE',
              'pairCount':total,'classCounts':dict(classes),'transformationCounts':dict(kinds),'statistics':dict(stats),
              'independentSourceParents':len(parents),'queryEventGroups':len(events),'generatedPositiveQueryChunks':accepted_generated,
              'partitionHashes':partition_hashes,'negativeHashes':negative_hashes,'generationExportHashes':generation_hashes,
              'formalScaleAndBalanceReady':scale_ready,'M3TrainingStarted':False,'humanGold':False,
              'scope':'Distinct window pairs, not independent articles/events. Non-overlapping query slices retain the full corresponding source segment. Generated semantics and rule negatives remain fallible; no detector scores create truth.'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (args.output/'READY').write_text(json.dumps({name:sha(args.output/name) for name in ['pairs.jsonl','manifest.json']},indent=2),encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
