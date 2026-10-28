"""Snapshot the business bank or prepare an explicit, fully verified service profile."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_detection import service_profile


def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='action',required=True)
    snapshot=commands.add_parser('snapshot');snapshot.add_argument('--generation',required=True);snapshot.add_argument('--output',type=Path,required=True)
    prepare=commands.add_parser('prepare');prepare.add_argument('--name',required=True);prepare.add_argument('--generation',required=True)
    for key in ('bundle','index','calibration','protocol','evaluation','predictions','baseline','baseline-predictions'):
        prepare.add_argument('--'+key,type=Path,required=True)
    verify=commands.add_parser('verify');verify.add_argument('--profile-id',required=True)
    commands.add_parser('list');args=parser.parse_args()
    if args.action=='snapshot':result=service_profile.snapshot_references(args.generation,args.output)
    elif args.action=='prepare':
        profile=service_profile.create_profile(name=args.name,generation=args.generation,bundle=args.bundle,index=args.index,
            calibration=args.calibration,quality_evidence={key:getattr(args,key) for key in ('protocol','evaluation','predictions','baseline','baseline_predictions')})
        result={'profileId':profile['profileId'],'state':'READY_FOR_EXPLICIT_SERVICE_LOAD','name':profile['name'],'libraryGenerationId':args.generation}
    elif args.action=='verify':
        profile=service_profile.verify_profile(args.profile_id)
        result={key:profile[key] for key in ('profileId','name','profileSha256','libraryGenerationId','libraryManifestSha256','quality')}
    else:result=service_profile.candidates()
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
