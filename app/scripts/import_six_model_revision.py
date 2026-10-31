import json,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'app/python'),str(ROOT/'app/scripts')]
from runtime_manager import configuration,sql
from campus_workbench.preparation import prepare,sha,write_json
from campus_workbench.datasets import read_dataset,audit_dataset,write_dataset_version
from import_six_model_datasets import quoted
cfg,runtime=configuration();db=lambda q:sql(cfg,runtime,'USE campus_review_midterm; '+q,'app')
receipt_path=ROOT/'runtime/six-model-bundles-20261031/import-receipt-v2.json'
if receipt_path.exists():raise RuntimeError('Revision already imported')
old=json.loads((receipt_path.parent/'import-receipt.json').read_text(encoding='utf8'));package=ROOT/'runtime/datasets/six-model-20261031-v2';manifest=json.loads((package/'manifest.json').read_text(encoding='utf8'))
actor=db("SELECT id FROM app_user WHERE username='admin' AND role='ADMIN' AND enabled=true;");statements=[];receipt={}
def register(run_id,dataset,version,action,result,options,output=None):
    statements.append("INSERT INTO ml_run(id,dataset_id,input_version_id,output_version_id,action,status,mapping_json,options_json,result_json,created_by,created_at,started_at,finished_at) VALUES("+','.join(quoted(x) for x in [run_id,dataset,version,output,action,'COMPLETED','{}',json.dumps(options),json.dumps(result,ensure_ascii=False)])+f",{actor},UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),UTC_TIMESTAMP(3));")
for key,item in old.items():
    pair_path=ROOT/manifest['sets'][key]['path'];dataset=item['datasetId'];version=item['versionId'];kind=item['kind']
    if sha(pair_path)!=manifest['sets'][key]['sha256']:raise ValueError('Revision changed')
    if kind=='PAIRS':
        raw,version=[str(uuid.uuid4()) for _ in range(2)];folder=runtime/'workbench/datasets'/dataset/raw;folder.mkdir();shutil.copyfile(pair_path,folder/'source.jsonl');data=read_dataset(folder/'source.jsonl','PAIRS');clean=write_dataset_version(folder/'source.jsonl',runtime/'workbench/datasets'/dataset/version,'PAIRS')
        for identity,stage,filename,parent,digest,count in [(raw,'RAW','source.jsonl',None,sha(folder/'source.jsonl'),data['totalRows']),(version,'CLEAN','corpus.jsonl',raw,sha(runtime/'workbench/datasets'/dataset/version/'corpus.jsonl'),clean['outputRows'])]:
            statements.append("INSERT INTO ml_dataset_version(id,dataset_id,parent_version_id,stage,status,file_name,sha256,row_count,mapping_json,created_at) VALUES("+','.join(quoted(x) for x in [identity,dataset,parent,stage,'READY',filename,digest,count,json.dumps(data['mapping'])])+",UTC_TIMESTAMP(3));")
        register(str(uuid.uuid4()),dataset,raw,'AUDIT',{'audit':audit_dataset(data),'columns':data['columns'],'mapping':data['mapping']},{'origin':'PARTITION_ISOLATION_REVISION'})
        register(str(uuid.uuid4()),dataset,raw,'CLEAN',clean,{'origin':'PARTITION_ISOLATION_REVISION'},version)
    prep_id=str(uuid.uuid4());output=runtime/'workbench/computations'/prep_id/'output';events=[]
    prepared=prepare(pair_path if kind=='NEWS' else runtime/'workbench/datasets'/dataset/version/'corpus.jsonl',output,'PAIRS',{},events.append)
    if kind=='NEWS':prepared.update(sourceKind='NEWS',inputSha256=sha(runtime/'workbench/datasets'/dataset/version/'corpus.jsonl'),inputRows=item['originalRows'],outputRows=manifest['sets'][key]['rows'])
    prepared.update(preparationOrigin='REUSED_CHECKED_LABELLED_MATERIAL',pairedInputSha256=sha(pair_path),sourcePackageSha256=sha(package/'manifest.json'));write_json(output/'manifest.json',prepared)
    write_json(output.parent/'config.json',{'action':'PREPARE','input':str(runtime/'workbench/datasets'/dataset/version/'corpus.jsonl'),'kind':kind,'output':str(output),'parameters':{},'preparationOrigin':'REUSED_CHECKED_LABELLED_MATERIAL','pairedInputSha256':sha(pair_path)})
    register(prep_id,dataset,version,'PREPARE',prepared,{'origin':'REUSED_CHECKED_LABELLED_MATERIAL','pairedInputSha256':sha(pair_path),'parameters':{}})
    for event in events:statements.append(f"INSERT INTO ml_run_event(run_id,payload_json,created_at) VALUES({quoted(prep_id)},{quoted(json.dumps(event,ensure_ascii=False))},UTC_TIMESTAMP(3));")
    receipt[key]={**item,'rawVersionId':raw if kind=='PAIRS' else item['rawVersionId'],'versionId':version,'preparationId':prep_id,'sampleRows':sum(p['rows'] for p in prepared['partitions'].values()),'partitions':prepared['partitions']}
    if not prepared['trainReady']:raise ValueError('Revision missing classes')
statements.append("UPDATE ml_pipeline SET archived=true WHERE id='6f9ded9b-a543-4ced-8aa5-a9d72020c0c4' AND status='FAILED';")
statements.append("UPDATE ml_model SET catalog='HISTORY' WHERE id='1301e6c9-af1b-4a42-b7e5-cb5666e860b9';")
db('START TRANSACTION;'+''.join(statements)+'COMMIT;');write_json(receipt_path,receipt);print(json.dumps(receipt,ensure_ascii=False))
