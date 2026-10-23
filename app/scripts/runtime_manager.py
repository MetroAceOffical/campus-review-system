"""Manage this project's isolated runtime. Never use service control or process-name termination."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def validate_config(root, config):
    runtime = (root / config['runtimeRoot']).resolve()
    if runtime == root.resolve() or not runtime.is_relative_to(root.resolve()):
        raise ValueError('Runtime must be a dedicated directory within this project')
    if config['ports']['mysql'] != 3308:
        raise ValueError('Only isolated port 3308 is permitted')
    if (config['database'], config['testDatabase']) != ('campus_review_midterm', 'campus_review_midterm_test'):
        raise ValueError('Database names must be the dedicated project and test names')
    return runtime


def configuration():
    local = ROOT / 'app/config/local.json'
    config = json.loads((local if local.exists() else ROOT / 'app/config/local.example.json').read_text(encoding='utf-8'))
    return config, validate_config(ROOT, config)


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.3):
            return True
    except OSError:
        return False


def sql(config, runtime, statement, account='root'):
    credentials = json.loads((runtime / 'private-config/database.json').read_text())
    env = dict(os.environ, MYSQL_PWD=credentials[account])
    user = {'root': 'root', 'app': 'campus_app', 'test': 'campus_test'}[account]
    args = [str(Path(config['mysqlBin']) / 'mysql.exe'), '--no-defaults', '--protocol=TCP',
            '-h', '127.0.0.1', '-P', '3308', '-u', user, '--batch', '--skip-column-names', '--default-character-set=utf8mb4']
    result = subprocess.run(args, input=statement, text=True, encoding='utf-8', capture_output=True, env=env)
    if result.returncode:
        # SQL text may include credentials. Never echo it or client diagnostics.
        raise RuntimeError('Project database operation failed; SQL and credentials omitted')
    return result.stdout.strip()


def verify_database_identity(config, runtime):
    actual = Path(sql(config, runtime, 'SELECT @@datadir;')).resolve()
    expected = (runtime / 'mysql/data').resolve()
    if actual != expected:
        raise RuntimeError('Port 3308 belongs to a different datadir; leaving it untouched')


def mysql_start(config, runtime):
    private = runtime / 'private-config'
    credentials_path = private / 'database.json'
    if listening(3308):
        if not credentials_path.exists():
            raise RuntimeError('Port 3308 occupied by unknown service; leaving it untouched')
        verify_database_identity(config, runtime)
        print('Project MySQL already ready; existing users and data preserved')
        return
    for folder in ['mysql', 'logs', 'private-config', 'uploads', 'derived', 'indexes', 'experiments']:
        (runtime / folder).mkdir(parents=True, exist_ok=True)
    data = runtime / 'mysql/data'
    if data.exists() and not credentials_path.exists():
        raise RuntimeError('Existing datadir without project credentials; no automatic reset')
    if not credentials_path.exists():
        credentials_path.write_text(json.dumps({key: secrets.token_hex(24) for key in ['root', 'app', 'test']}), encoding='utf-8')
    credentials = json.loads(credentials_path.read_text())
    binary = Path(config['mysqlBin']) / 'mysqld.exe'
    mysql_config = runtime / 'mysql/my.ini'
    mysql_config.write_text(
        f'[mysqld]\nbasedir={Path(config["mysqlBin"]).parent.as_posix()}\n'
        f'datadir={data.as_posix()}\nport=3308\nbind-address=127.0.0.1\nmysqlx=0\n'
        f'skip-log-bin\ninnodb-buffer-pool-size=128M\ninnodb-redo-log-capacity=64M\n'
        f'character-set-server=utf8mb4\ncollation-server=utf8mb4_0900_ai_ci\n'
        f'log-error={(runtime / "logs/mysql-error.log").as_posix()}\n'
        f'pid-file={(runtime / "mysql/mysql.pid").as_posix()}\n', encoding='utf-8')
    if not data.exists():
        result = subprocess.run([str(binary), '--no-defaults', '--initialize-insecure',
                                 f'--basedir={Path(config["mysqlBin"]).parent.as_posix()}', f'--datadir={data.as_posix()}'], capture_output=True)
        if result.returncode:
            raise RuntimeError('New dedicated MySQL initialization failed; no existing instance was changed')
    provisioned = private / 'mysql-provisioned'
    initfile = private / 'mysql-bootstrap.sql'
    arguments = [str(binary), f'--defaults-file={mysql_config}', '--no-monitor']
    if not provisioned.exists():
        # Bootstrap is restartable after interruption; credentials are generated once and reused.
        initfile.write_text(
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{credentials['root']}';\n"
            f"CREATE DATABASE IF NOT EXISTS {config['database']} CHARACTER SET utf8mb4;\n"
            f"CREATE DATABASE IF NOT EXISTS {config['testDatabase']} CHARACTER SET utf8mb4;\n"
            f"CREATE USER IF NOT EXISTS 'campus_app'@'127.0.0.1' IDENTIFIED BY '{credentials['app']}';\n"
            f"CREATE USER IF NOT EXISTS 'campus_test'@'127.0.0.1' IDENTIFIED BY '{credentials['test']}';\n"
            f"GRANT ALL PRIVILEGES ON {config['database']}.* TO 'campus_app'@'127.0.0.1';\n"
            f"GRANT ALL PRIVILEGES ON {config['testDatabase']}.* TO 'campus_test'@'127.0.0.1';\n", encoding='utf-8')
        arguments.append(f'--init-file={initfile}')
    with (runtime / 'logs/mysql-console.log').open('ab') as log:
        process = subprocess.Popen(arguments, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    (runtime / 'mysql/process.json').write_text(json.dumps({'pid': process.pid, 'config': str(mysql_config), 'datadir': str(data)}))
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError('Project MySQL exited; inspect runtime/logs/mysql-error.log')
        if listening(3308):
            try:
                verify_database_identity(config, runtime)
                break
            except RuntimeError:
                pass
        time.sleep(.2)
    else:
        raise RuntimeError('Project MySQL startup timeout')
    if initfile.exists():
        initfile.unlink()
    provisioned.write_text('Dedicated midterm instance; credentials unchanged on repeated init')
    print('Project MySQL ready:', sql(config, runtime, 'SELECT VERSION();'))


def ensure_accounts(runtime):
    target = runtime / 'private-config/accounts.json'
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({name: secrets.token_urlsafe(18) for name in ['member1', 'member2', 'reviewer', 'admin']}), encoding='utf-8')
    token=runtime/'private-config/internal-token'
    if not token.exists():token.write_text(secrets.token_hex(32),encoding='utf-8')


def mysql_stop(config, runtime):
    if not listening(3308):
        print('Project MySQL is not listening')
        return
    verify_database_identity(config, runtime)
    credentials = json.loads((runtime / 'private-config/database.json').read_text())
    subprocess.run([str(Path(config['mysqlBin']) / 'mysqladmin.exe'), '--no-defaults', '--protocol=TCP',
                    '-h', '127.0.0.1', '-P', '3308', '-u', 'root', 'shutdown'],
                   env=dict(os.environ, MYSQL_PWD=credentials['root']), check=True, capture_output=True)
    for _ in range(100):
        if not listening(3308):
            print('Dedicated project MySQL stopped')
            return
        time.sleep(.2)
    raise RuntimeError('Project MySQL has not stopped; do not restart')


def inventory(runtime):
    folders = ['validation/text/round2', 'validation/text/models', 'validation/remaining/text',
               'validation/remaining/image/models', 'validation/remaining/image/evaluation',
               'validation/remaining/vision/models', 'validation/remaining/vision/evaluation']
    entries = []
    for folder in folders:
        for path in sorted((ROOT / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
            entries.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest})
    output = ROOT / 'docs/midterm/evidence/frozen-assets.json'
    if output.exists():
        previous = json.loads(output.read_text(encoding='utf-8'))
        if previous['files'] != entries:
            raise RuntimeError('Frozen asset inventory changed; original inventory preserved')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'files': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Frozen assets verified:', len(entries), 'files')


def status(config, runtime):
    print(json.dumps({'runtime': str(runtime), 'ports': {name: listening(port) for name, port in config['ports'].items()}}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['mysql-start', 'mysql-stop', 'status', 'inventory', 'accounts'])
    args = parser.parse_args()
    config, runtime = configuration()
    {'mysql-start': mysql_start, 'mysql-stop': mysql_stop, 'status': status,
     'inventory': lambda c, r: inventory(r), 'accounts': lambda c,r: ensure_accounts(r)}[args.action](config, runtime)
