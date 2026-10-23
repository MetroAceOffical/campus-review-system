"""Quiescent local backup and non-destructive, isolated restore verification."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import uuid
from runtime_manager import ROOT,configuration,listening,verify_database_identity,sql
from process_supervisor import health,manager_lock

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def same_counts(actual,expected):
    def parsed(value):return {name:int(count) for name,count in (line.split('\t') for line in value.splitlines() if line)}
    return parsed(actual)==parsed(expected)

def validate_restore_target(target,port):
    target=Path(target).resolve();parent=(ROOT/'runtime/restores').resolve()
    if target==parent or not target.is_relative_to(parent) or target.exists():raise ValueError('Restore requires a new dedicated directory under runtime/restores; existing data is never overwritten')
    if not 3310<=port<=3399:raise ValueError('Restore verification uses an isolated port 3310..3399 only')
    return target

def verify_backup(folder):
    folder=Path(folder).resolve();manifest_path=folder/'manifest.json';ready=folder/'READY'
    if not manifest_path.is_file() or not ready.is_file() or sha(manifest_path)!=ready.read_text().strip():raise ValueError('Backup is incomplete or manifest checksum differs')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schemaVersion')!='1' or manifest.get('database')!='campus_review_midterm':raise ValueError('Unsupported backup')
    expected={row['path'] for row in manifest['files']}
    actual={path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}-{'manifest.json','READY'}
    if actual!=expected:raise ValueError('Backup contains missing or unknown files')
    for row in manifest['files']:
        path=(folder/row['path']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('Backup file checksum or path differs')
    return manifest

def backup(config,runtime):
    if listening(config['ports']['java']):raise RuntimeError('Stop project Java before a consistent backup; no automatic business interruption')
    for component in ('detector','ocr'):
        if listening(config['ports'][component]) and health(config,runtime,component).get('busy') is not False:raise RuntimeError('Model process not proven idle; backup deferred')
    verify_database_identity(config,runtime)
    folder=runtime/'backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
    credentials=json.loads((runtime/'private-config/database.json').read_text());dump=folder/'database.sql'
    args=[str(Path(config['mysqlBin'])/'mysqldump.exe'),'--no-defaults','--host=127.0.0.1','--port=3308','--user=campus_app','--single-transaction','--skip-add-locks','--set-gtid-purged=OFF','--column-statistics=0','--no-tablespaces','--hex-blob','--default-character-set=utf8mb4',f'--result-file={dump}',config['database']]
    result=subprocess.run(args,env=dict(os.environ,MYSQL_PWD=credentials['app']),capture_output=True)
    if result.returncode:raise RuntimeError('Project SQL backup failed; private diagnostics omitted; incomplete directory retained')
    for name in ('uploads','derived','indexes','experiments','private-config'):
        source=runtime/name
        if source.exists():shutil.copytree(source,folder/'runtime'/name)
    shutil.copytree(ROOT/'app/config',folder/'configuration')
    shutil.copyfile(ROOT/'docs/midterm/evidence/frozen-assets.json',folder/'frozen-assets.json')
    files=[{'path':path.relative_to(folder).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)} for path in sorted(folder.rglob('*')) if path.is_file()]
    counts=sql(config,runtime,"SELECT 'manuscript',COUNT(*) FROM campus_review_midterm.manuscript UNION ALL SELECT 'submission_version',COUNT(*) FROM campus_review_midterm.submission_version UNION ALL SELECT 'detection_attempt',COUNT(*) FROM campus_review_midterm.detection_attempt UNION ALL SELECT 'reference_work',COUNT(*) FROM campus_review_midterm.reference_work UNION ALL SELECT 'publication',COUNT(*) FROM campus_review_midterm.manuscript WHERE publication_state='PUBLISHED';",'app')
    manifest={'schemaVersion':'1','createdAt':datetime.now(timezone.utc).isoformat(),'database':config['database'],'sourceRoot':str(ROOT),'runtimeRoot':str(runtime),'rowCounts':counts,'files':files,'notes':['Private local backup: contains accounts, internal token and business SQL; never upload to GitHub.','Frozen model weights remain in their original directories, identified by frozen-assets.json.','Absolute paths in immutable historical manifests are retained; isolated verification does not activate or rewrite them.']}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');(folder/'READY').write_text(sha(folder/'manifest.json'));verify_backup(folder)
    print(json.dumps({'status':'BACKUP_VERIFIED','folder':str(folder),'files':len(files)}));return folder

def instance_sql(config,port,password,statement=None,source=None,database=None):
    args=[str(Path(config['mysqlBin'])/'mysql.exe'),'--no-defaults','--protocol=TCP','--host=127.0.0.1',f'--port={port}','--user=root','--batch','--skip-column-names','--default-character-set=utf8mb4']
    if database:args.append(database)
    if source is not None:
        with source.open('rb') as stream:result=subprocess.run(args,stdin=stream,env=dict(os.environ,MYSQL_PWD=password),capture_output=True)
    else:result=subprocess.run(args,input=statement.encode('utf-8'),env=dict(os.environ,MYSQL_PWD=password),capture_output=True)
    if result.returncode:raise RuntimeError('Isolated restore SQL operation failed; private diagnostics omitted')
    return result.stdout.decode('utf-8').strip()

def restore(config,folder,target,port):
    manifest=verify_backup(folder);folder=Path(folder).resolve();target=validate_restore_target(target,port)
    if listening(port):raise RuntimeError('Restore port occupied; unknown process left untouched')
    target.mkdir(parents=True,exist_ok=False);snapshot=target/'snapshot';shutil.copytree(folder,snapshot);verify_backup(snapshot)
    verification=target/'verification';verification.mkdir();data=verification/'mysql/data';data.parent.mkdir();password=secrets.token_hex(24)
    (verification/'private-config').mkdir();(verification/'private-config/database.json').write_text(json.dumps({'root':password}),encoding='utf-8')
    binary=Path(config['mysqlBin'])/'mysqld.exe';result=subprocess.run([str(binary),'--no-defaults','--initialize-insecure',f'--basedir={Path(config["mysqlBin"]).parent}',f'--datadir={data}'],capture_output=True)
    if result.returncode:raise RuntimeError('New isolated restore datadir initialization failed')
    ini=verification/'mysql/my.ini';ini.write_text(f'[mysqld]\nbasedir={Path(config["mysqlBin"]).parent.as_posix()}\ndatadir={data.as_posix()}\nport={port}\nbind-address=127.0.0.1\nmysqlx=0\nskip-log-bin\ninnodb-buffer-pool-size=128M\ninnodb-redo-log-capacity=64M\nlog-error={(verification/"mysql/error.log").as_posix()}\n',encoding='utf-8')
    bootstrap=verification/'private-config/bootstrap.sql';bootstrap.write_text(f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{password}';\nCREATE DATABASE campus_review_restore CHARACTER SET utf8mb4;\n",encoding='utf-8')
    with (verification/'mysql/console.log').open('ab') as log:process=subprocess.Popen([str(binary),f'--defaults-file={ini}','--no-monitor',f'--init-file={bootstrap}'],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    ready=False
    try:
        for _ in range(60):
            if process.poll() is not None:raise RuntimeError('Isolated restore MySQL exited')
            try:
                actual=instance_sql(config,port,password,'SELECT @@datadir;')
                if Path(actual).resolve()!=data.resolve():raise RuntimeError('Restore datadir identity mismatch')
                ready=True;break
            except RuntimeError:time.sleep(.5)
        if not ready:raise RuntimeError('Isolated restore startup timeout; inspect verification log')
        bootstrap.unlink()
        instance_sql(config,port,password,source=snapshot/'database.sql',database='campus_review_restore')
        counts=instance_sql(config,port,password,"SELECT 'manuscript',COUNT(*) FROM manuscript UNION ALL SELECT 'submission_version',COUNT(*) FROM submission_version UNION ALL SELECT 'detection_attempt',COUNT(*) FROM detection_attempt UNION ALL SELECT 'reference_work',COUNT(*) FROM reference_work UNION ALL SELECT 'publication',COUNT(*) FROM manuscript WHERE publication_state='PUBLISHED';",database='campus_review_restore')
        (verification/'row-counts.json').write_text(json.dumps({'actual':counts,'expected':manifest['rowCounts']}),encoding='utf-8')
        if not same_counts(counts,manifest['rowCounts']):raise RuntimeError('Restored row counts differ')
        verify_backup(snapshot)
        report={'status':'RESTORE_VERIFIED','target':str(target),'port':port,'database':'campus_review_restore','filesVerified':len(manifest['files']),'rowCounts':counts,'businessDirectoryOverwritten':False,'activated':False,'historicalManifestPathsRetained':True}
        (verification/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));return report
    finally:
        if process.poll() is None:
            # Authenticate and check the new datadir before shutting down this verification instance.
            try:
                if Path(instance_sql(config,port,password,'SELECT @@datadir;')).resolve()==data.resolve():
                    result=subprocess.run([str(Path(config['mysqlBin'])/'mysqladmin.exe'),'--no-defaults','--host=127.0.0.1',f'--port={port}','--user=root','shutdown'],env=dict(os.environ,MYSQL_PWD=password),capture_output=True)
                    if result.returncode:raise RuntimeError('Restore verification shutdown failed')
                    process.wait(30)
            except Exception as error:raise RuntimeError('Verification instance retained for inspection; never stop a guessed PID') from error

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore']);parser.add_argument('--backup',type=Path);parser.add_argument('--target',type=Path);parser.add_argument('--port',type=int,default=3318);args=parser.parse_args();config,runtime=configuration()
    if args.action=='backup':
        with manager_lock(runtime):backup(config,runtime)
    elif args.backup is None or args.target is None:parser.error('restore requires explicit --backup and --target')
    else:restore(config,args.backup,args.target,args.port)
