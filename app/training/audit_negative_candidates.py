"""Validate exact source facts before accepting rule-supported training negatives."""
import hashlib
import argparse
import json
from collections import Counter
from pathlib import Path
from corpus import normalized,read_jsonl
from construct_correspondence import verify_ready
from negative_basis import assess_difference,RULE_VERSION

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/datasets/campus-correspondence-candidates-v1'
OUT=ROOT/'runtime/datasets/campus-supported-negatives-v1'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);parser.add_argument('--source',type=Path,default=SOURCE);args=parser.parse_args();output=args.output;source=args.source
    if (output/'READY').exists():raise RuntimeError('Negative version already frozen')
    candidate_hashes=verify_ready(source)
    partitions=ROOT/'runtime/datasets/campus-partitions-20261026-v1';hashes=verify_ready(partitions)
    originals={row['documentId']:row for row in read_jsonl(partitions/'train.jsonl')}
    output.mkdir(parents=True,exist_ok=True)
    stats=Counter();rejections=Counter();seen=set();parents=set()
    with (output/'negative-pairs.jsonl').open('w',encoding='utf-8') as stream:
        for row in read_jsonl(source/'candidates.jsonl'):
            left,right=row['querySource'],row['candidateSource']
            for window in (left,right):
                original=originals[window['sourceId']]
                if window['text']!=original['text'][window['start']:window['end']]:raise ValueError('Candidate source range does not reconstruct')
                if window['eventClusterId']!=original['eventClusterId'] or window['sourceClusterId']!=original['sourceClusterId']:raise ValueError('Candidate source identity changed')
            stats['candidatesChecked']+=1
            basis=assess_difference(left,right)
            if not basis['supported']:
                rejections.update(key for key,value in basis['checks'].items() if not value)
                continue
            key=hashlib.sha256((normalized(left['text'])+'\0'+normalized(right['text'])).encode()).hexdigest()
            if key in seen:stats['duplicateTextPairs']+=1;continue
            seen.add(key);parents.add(left['sourceId'])
            record={'pairId':key,'taskType':'CONTENT_CORRESPONDENCE','target':0,'split':'train',
                    'labelOrigin':'rule_inferred_noncorrespondence','labelConfidence':'supported_rule','humanVerified':False,
                    'query':left['text'],'source':right['text'],'sourceIds':[right['sourceId']],
                    'sourceClusterId':right['sourceClusterId'],'eventClusterId':left['eventClusterId'],
                    'sourceOffsets':{'start':right['start'],'end':right['end']},
                    'positiveSource':left,'candidateSource':right,'negativeBasis':basis,
                    'retrievalRankForMiningOnly':row['lexicalRank']}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');stats['supportedUniquePairs']+=1
    manifest={'ruleVersion':RULE_VERSION,'state':'RULE_SUPPORTED_NEGATIVES_NOT_HUMAN_GOLD','statistics':dict(stats),'rejectionReasons':dict(rejections),
              'independentQuerySourceParents':len(parents),'sourceTrainSha256':hashes['train.jsonl'],'candidateManifestSha256':candidate_hashes['manifest.json'],
              'usedDetectorScoresForTruth':False,'scope':'Rule-supported training labels only. Do not use as final human-gold accuracy denominator. Counts may be far below the planned training scale; do not pad unsupported labels.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    ready={}
    for path in output.iterdir():
        if path.is_file():
            with path.open('rb') as stream:ready[path.name]=hashlib.file_digest(stream,'sha256').hexdigest()
    (output/'READY').write_text(json.dumps(ready,indent=2),encoding='utf-8');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
