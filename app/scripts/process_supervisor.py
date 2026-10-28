"""Launch only this project's existing runtimes; never terminate a process by name or PID alone."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid
from contextlib import contextmanager
import msvcrt
import psutil  # Already present in the frozen main environment; no installation performed.
from runtime_manager import ROOT,configuration,listening,mysql_start,mysql_stop

@contextmanager
def manager_lock(runtime):
    path=runtime/'processes/manager.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('Another project start/stop/backup operation is active; no duplicate operation started')
        try:yield
        finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

def record_process(process):
    return {'pid':process.pid,'created':process.create_time(),'exe':process.exe(),'cmdline':process.cmdline(),'cwd':process.cwd()}

def verify_process(record):
    try:process=psutil.Process(record['pid'])
    except psutil.NoSuchProcess:return None
    if abs(process.create_time()-record['created'])>.01 or process.exe().casefold()!=record['exe'].casefold() or process.cmdline()!=record['cmdline'] or Path(process.cwd()).resolve()!=Path(record['cwd']).resolve():
        raise RuntimeError('Process identity changed; unknown process left untouched')
    return process

def stop_owned(record):
    process=verify_process(record)
    if process is None:return
    process.terminate()
    try:process.wait(15)
    except psutil.TimeoutExpired:raise RuntimeError('Owned process did not stop; no automatic second process or forced PID kill')

def health(config,runtime,component):
    port=config['ports'][component];path='/api/auth/csrf' if component=='java' else '/health'
    headers={} if component=='java' else {'X-Internal-Token':(runtime/'private-config/internal-token').read_text().strip()}
    try:
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers=headers),timeout=3) as response:value=json.load(response)
        if component=='java':return {'ready':value.get('code')=='OK','busy':False}
        result={key:value.get(key) for key in ('ready','busy','runId','activeAttemptId','errorCode','availableTextConfigs')}
        if component=='detector':result['imageSchema']=(value.get('configs') or {}).get('imageConfig',{}).get('schemaVersion')
        return result
    except Exception:return {'ready':False,'busy':None,'errorCode':'SERVICE_UNAVAILABLE'}

def registry(runtime,component):return runtime/'processes'/f'{component}.json'

def read_record(runtime,component):
    path=registry(runtime,component)
    return json.loads(path.read_text()) if path.is_file() else None

def write_record(runtime,component,record):
    path=registry(runtime,component);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(record),encoding='utf-8');temporary.replace(path)

def verified_members(record):
    return [process for saved in record.get('members',[]) if (process:=verify_process(saved)) is not None]

def detector_profile(config,runtime):
    selected=config.get('detectorProfile')
    if not selected:return None
    path=(ROOT/selected).resolve();profiles=(runtime/'delivery/text-profiles').resolve()
    if path.name!='profile.json' or path.parent.parent!=profiles or str(uuid.UUID(path.parent.name))!=path.parent.name or not path.is_file():
        raise ValueError('detectorProfile must select a prepared project profile.json')
    return path

def start(config,runtime,component):
    profile=detector_profile(config,runtime) if component=='detector' else None
    enhanced=config.get('imageEnhancement',False) is True
    old=read_record(runtime,component)
    if old and verified_members(old):
        state=health(config,runtime,component)
        if old.get('runId') and state.get('runId') and old['runId']!=state['runId']:raise RuntimeError('Process runId changed; leaving it untouched')
        if not state.get('ready'):raise RuntimeError('Existing owned process is not ready; inspect status/logs; no duplicate launched')
        loaded={item.get('profileId') for item in (state.get('availableTextConfigs') or []) if item.get('profileId')}
        if component=='detector' and loaded!=({profile.parent.name} if profile else set()):raise RuntimeError('Running detector uses another profile; stop it explicitly when idle before starting the selected profile')
        if component=='detector' and state.get('imageSchema','image-v1')!=('image-v2' if enhanced else 'image-v1'):raise RuntimeError('Running detector uses another image policy; stop it explicitly when idle before changing it')
        print(json.dumps({'component':component,'status':'ALREADY_RUNNING',**state}));return
    if listening(config['ports'][component]):raise RuntimeError(f'{component} port occupied without a verified project handle; leaving it untouched')
    env=dict(os.environ,CAMPUS_ROOT=ROOT.as_posix(),PYTHONPATH=str(ROOT/'app/python'),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    for name,port in config['ports'].items():env['CAMPUS_'+name.upper()+'_PORT']=str(port)
    if component=='java':
        jar=ROOT/'app/backend/target/review-0.1.0.jar'
        if not jar.is_file():raise RuntimeError('Build the project first; startup does not install or build environments')
        credentials=json.loads((runtime/'private-config/database.json').read_text());env.update(CAMPUS_DB_PASSWORD=credentials['app'],CAMPUS_DB_URL=f"jdbc:mysql://127.0.0.1:{config['ports']['mysql']}/{config['database']}?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true",CAMPUS_MIGRATIONS=str(ROOT/'app/backend/src/main/resources/db/migrations'),CAMPUS_ACCOUNTS_FILE=str(runtime/'private-config/accounts.json'),CAMPUS_WORKER_ENABLED='true')
        args=[config['java'],'-Xmx384m','-jar',str(jar)]
    else:
        args=[str(ROOT/config['python' if component=='detector' else 'ocrPython']),'-B',str(ROOT/'app/python/run_service.py'),component,'--port',str(config['ports'][component])]
        if component=='detector':args+=['--index-root',str(runtime/'indexes')]
        if profile or component=='detector' and enhanced:
            interpreter=runtime/'environments/final-training/Scripts/python.exe'
            if not interpreter.is_file():raise RuntimeError('Approved project training environment is missing; no environment is installed at startup')
            args[0]=str(interpreter)
            if profile:args+=['--v3-profile',str(profile)]
        if component=='detector' and enhanced:args+=['--enhanced-images']
    (runtime/'logs').mkdir(parents=True,exist_ok=True)
    with (runtime/'logs'/f'{component}.log').open('ab') as log:
        child=subprocess.Popen(args,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    process=psutil.Process(child.pid);record={'launcherId':str(uuid.uuid4()),'component':component,'members':[record_process(process)]};write_record(runtime,component,record)
    deadline=time.monotonic()+config['timeoutsSeconds']['modelStartup']
    while time.monotonic()<deadline:
        if child.poll() is not None:raise RuntimeError(f'{component} exited; inspect its project log')
        members=[process,*process.children(recursive=True)]
        record['members']=[record_process(member) for member in members if member.is_running()];write_record(runtime,component,record)
        state=health(config,runtime,component)
        if state.get('runId'):record['runId']=state['runId'];write_record(runtime,component,record)
        if state.get('ready'):
            owners={connection.pid for connection in psutil.net_connections(kind='tcp') if connection.status==psutil.CONN_LISTEN and connection.laddr.port==config['ports'][component]}
            if not owners or not owners.issubset({member.pid for member in members}):raise RuntimeError('Listener is not a child of the recorded project launcher')
            print(json.dumps({'component':component,'status':'READY',**state}),flush=True);return
        time.sleep(1)
    raise RuntimeError(f'{component} startup not ready within configured timeout; process retained for inspection, no duplicate launched')

def stop(config,runtime,component,interrupt=False):
    record=read_record(runtime,component)
    if not record:
        if listening(config['ports'][component]):raise RuntimeError(f'{component} has no owned handle; unknown listener left untouched')
        print(component+': STOPPED');return
    members=verified_members(record)
    if not members:print(component+': STOPPED');return
    state=health(config,runtime,component)
    if record.get('runId') and state.get('runId') and record['runId']!=state['runId']:raise RuntimeError('Run identity changed; no process stopped')
    if component!='java' and (state.get('busy') is not False) and not interrupt:raise RuntimeError('Busy/unreachable does not prove idle; use explicit -Interrupt only for a deliberate project interruption')
    # Validate every member before stopping any of them, including a Windows venv launcher child.
    for saved in reversed(record['members']):stop_owned(saved)
    if listening(config['ports'][component]):raise RuntimeError('Port is still occupied; no additional process stopped')
    print(component+': STOPPED')

def status(config,runtime):
    values={}
    for component in ('java','detector','ocr'):
        record=read_record(runtime,component)
        try:owned=bool(record and verified_members(record));error=None
        except RuntimeError:owned=False;error='PROCESS_IDENTITY_CHANGED'
        values[component]={'owned':owned,'listening':listening(config['ports'][component]),**health(config,runtime,component)}
        if error:values[component]['errorCode']=error
    values['mysql']={'port':3308,'listening':listening(3308)};print(json.dumps(values,indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status']);parser.add_argument('--component',choices=['all','java','detector','ocr'],default='all');parser.add_argument('--interrupt',action='store_true');parser.add_argument('--stop-mysql',action='store_true');args=parser.parse_args();config,runtime=configuration()
    if args.action=='status':status(config,runtime);return
    with manager_lock(runtime):
        if args.action=='start':
            if not (runtime/'private-config/mysql-provisioned').is_file():raise RuntimeError('Initialize this project first; startup does not reset or provision data')
            mysql_start(config,runtime)
            for component in (('java','detector','ocr') if args.component=='all' else (args.component,)):start(config,runtime,component)
        else:
            for component in (('java','detector','ocr') if args.component=='all' else (args.component,)):stop(config,runtime,component,args.interrupt)
            if args.stop_mysql:mysql_stop(config,runtime)

if __name__=='__main__':main()
