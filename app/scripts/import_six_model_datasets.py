"""Import verified project packages with actual audit/clean/partition artifacts.

No inference/generation/training is started. Runtime credentials stay local.
NEWS collections retain full originals for reference import and attach checked
labelled samples as a separate preparation, with explicit source hashes.
"""
import json,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'app/python'),str(ROOT/'app/scripts')]
from runtime_manager import configuration,sql
from campus_workbench.datasets import read_dataset,audit_dataset,write_dataset_version
from campus_workbench.preparation import prepare,sha,write_json
PACKAGE=ROOT/'runtime/datasets/six-model-20261031-v1'
RECEIPT=ROOT/'runtime/six-model-bundles-20261031/import-receipt.json'
def quoted(value):
    if value is None:return 'NULL'
    return "CONVERT(X'"+str(value).encode().hex()+"' USING utf8mb4)"
def main():
    if RECEIPT.exists():raise RuntimeError('Already imported; reuse receipt')
    cfg,runtime=configuration();db=lambda text:sql(cfg,runtime,'USE campus_review_midterm; '+text,'app')
    if int(db("SELECT COUNT(*) FROM ml_run WHERE status IN ('RUNNING','QUEUED');")):raise RuntimeError('Wait until existing jobs finish')
    actor=db("SELECT id FROM app_user WHERE username='admin' AND role='ADMIN' AND enabled=true;")
    if not actor.isdigit():raise RuntimeError('Local admin unavailable')
    manifest=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf8'))
    parents=[json.loads(s) for s in (ROOT/'runtime/datasets/campus-quality-20261028-v1/train.jsonl').read_text(encoding='utf8').splitlines() if s]
    names={'public-pairs':('公开中文句对 · PAWS-X','PAIRS',2),'ncuc-news-pairs':('南京传媒学院 · 新闻原稿与改写','NEWS',1),'campus-enhancement-pairs':('高校新闻 · 复用与正常对照','NEWS',2),'combined-pairs':('综合文本复用 · 正式训练','PAIRS',1)}
    receipt={};statements=[];events=[]
    def run(run_id,dataset,version,action,result,options,mapping=None,output_version=None):
        statements.append("INSERT INTO ml_run(id,dataset_id,input_version_id,output_version_id,action,status,mapping_json,options_json,result_json,created_by,created_at,started_at,finished_at) VALUES("+','.join(quoted(v) for v in [run_id,dataset,version,output_version,action,'COMPLETED',json.dumps(mapping or {}),json.dumps(options,ensure_ascii=False),json.dumps(result,ensure_ascii=False)])+f",{actor},UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),UTC_TIMESTAMP(3));")
    for key,(name,kind,organization) in names.items():
        pair_path=ROOT/manifest['sets'][key]['path']
        if sha(pair_path)!=manifest['sets'][key]['sha256']:raise ValueError('Package changed')
        source=pair_path
        if kind=='NEWS':
            source=PACKAGE/(key.replace('-pairs','-originals')+'.jsonl')
            home=key=='ncuc-news-pairs'
            with source.open('w',encoding='utf8') as stream:
                for r in parents:
                    if (r['institutionName']=='南京传媒学院')!=home:continue
                    item={'id':r['documentId'],'title':r['title'],'text':r['text'],'source_institution':r['institutionName'],'url':r['url'],'published_at':r.get('publishedAt'),'source_cluster_id':r['sourceClusterId'],'event_cluster_id':r['eventClusterId'],'split':'train'}
                    stream.write(json.dumps(item,ensure_ascii=False)+'\n')
        dataset,raw,clean,audit_id,clean_id,prep_id=[str(uuid.uuid4()) for _ in range(6)]
        raw_dir=runtime/'workbench/datasets'/dataset/raw;raw_dir.mkdir(parents=True)
        raw_file=raw_dir/'source.jsonl';shutil.copyfile(source,raw_file)
        data=read_dataset(raw_file,kind);audit=audit_dataset(data)
        clean_dir=runtime/'workbench/datasets'/dataset/clean
        clean_manifest=write_dataset_version(raw_file,clean_dir,kind)
        prepare_dir=runtime/'workbench/computations'/prep_id/'output'
        prepared=prepare(clean_dir/'corpus.jsonl' if kind=='PAIRS' else pair_path,prepare_dir,'PAIRS',{},lambda e:events.append((prep_id,e)))
        if kind=='NEWS':
            prepared.update(sourceKind='NEWS',inputSha256=sha(clean_dir/'corpus.jsonl'),inputRows=clean_manifest['outputRows'],outputRows=manifest['sets'][key]['rows'],preparationOrigin='REUSED_CHECKED_LABELLED_MATERIAL',pairedInputSha256=sha(pair_path),sourcePackageSha256=sha(PACKAGE/'manifest.json'))
            write_json(prepare_dir/'manifest.json',prepared)
        config={'action':'PREPARE','input':str(clean_dir/'corpus.jsonl'),'kind':kind,'output':str(prepare_dir),'parameters':{},'preparationOrigin':'REUSED_CHECKED_LABELLED_MATERIAL','pairedInputSha256':sha(pair_path)}
        write_json(prepare_dir.parent/'config.json',config)
        purpose='BOTH' if kind=='NEWS' else 'TRAIN'
        statements.append(f"INSERT INTO ml_dataset(id,organization_id,name,kind,purpose,catalog,created_by,created_at,updated_at) VALUES({quoted(dataset)},{organization},{quoted(name)},{quoted(kind)},{quoted(purpose)},'FORMAL',{actor},UTC_TIMESTAMP(3),UTC_TIMESTAMP(3));")
        for identity,stage,filename,parent_id,digest,count in [(raw,'RAW','source.jsonl',None,sha(raw_file),data['totalRows']),(clean,'CLEAN','corpus.jsonl',raw,sha(clean_dir/'corpus.jsonl'),clean_manifest['outputRows'])]:
            statements.append("INSERT INTO ml_dataset_version(id,dataset_id,parent_version_id,stage,status,file_name,sha256,row_count,mapping_json,created_at) VALUES("+','.join(quoted(v) for v in [identity,dataset,parent_id,stage,'READY',filename,digest,count,json.dumps(data['mapping'])])+",UTC_TIMESTAMP(3));")
        run(audit_id,dataset,raw,'AUDIT',{'audit':audit,'columns':data['columns'],'mapping':data['mapping'],'preview':data['rows'][:5]},{'origin':'CURATED_IMPORT'},data['mapping'])
        run(clean_id,dataset,raw,'CLEAN',clean_manifest,{'origin':'CURATED_IMPORT'},data['mapping'],clean)
        run(prep_id,dataset,clean,'PREPARE',prepared,{'origin':'REUSED_CHECKED_LABELLED_MATERIAL','parameters':{},'pairedInputSha256':sha(pair_path)})
        receipt[key]={'datasetId':dataset,'versionId':clean,'rawVersionId':raw,'preparationId':prep_id,'kind':kind,'originalRows':data['totalRows'] if kind=='NEWS' else None,'sampleRows':sum(p['rows'] for p in prepared['partitions'].values()),'partitions':prepared['partitions'],'trainReady':prepared['trainReady']}
        if not prepared['trainReady']:raise ValueError('Preparation not train ready')
    # Keep every original row and model accessible in the historical catalog.
    old=['50321be7-377c-429c-9844-882fb33ad36d','2bdab7e3-7fcb-43ee-8caf-06d0d75fe225','f1e430a9-7787-40f4-ba51-e07df95f798c','84b6e075-394b-442e-a005-524c19078d15','babcdeee-5c3f-438e-9643-2a95192147a6','e5f34be6-f8b6-473d-902b-47fc1811c1c0','9d53b898-9bf0-42b6-be1b-0a7151c9389c','d8f1e29b-cc9f-4713-8ab6-b0b123f6db68']
    statements.append("UPDATE ml_dataset SET catalog='HISTORY' WHERE id IN ("+','.join(quoted(x) for x in old)+");")
    statements.append("UPDATE ml_model SET catalog='HISTORY' WHERE dataset_id IN ("+','.join(quoted(x) for x in old)+");")
    db('START TRANSACTION;'+''.join(statements)+'COMMIT;')
    # The import computation was performed above; these are its actual events.
    for run_id,event in events:db(f"INSERT INTO ml_run_event(run_id,payload_json,created_at) VALUES({quoted(run_id)},{quoted(json.dumps(event,ensure_ascii=False))},UTC_TIMESTAMP(3));")
    RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
