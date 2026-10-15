"""Create/start only the PostgreSQL cluster owned by this project."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import psycopg
from psycopg import sql
from dotenv import dotenv_values
from .config import ROOT

RUNTIME = ROOT / '.runtime'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

def pg_bin():
    env = {**dotenv_values(ROOT / '.env'), **os.environ}
    candidates = [env.get('PG_BIN'), shutil.which('pg_ctl')]
    candidates += ['D:/PostgreSQL/postgresql-16.14-2/bin']
    candidates += [str(p) for p in Path('C:/Program Files/PostgreSQL').glob('*/bin')]
    for path in candidates:
        if not path:
            continue
        folder = Path(path)
        if folder.is_file():
            folder = folder.parent
        if (folder / ('pg_ctl.exe' if os.name == 'nt' else 'pg_ctl')).exists():
            return folder
    raise RuntimeError('PostgreSQL not found. Install PostgreSQL 16+ and configure PG_BIN.')

def pg_command(name, *args, check=True):
    exe = pg_bin() / (name + ('.exe' if os.name == 'nt' else ''))
    # pg_ctl starts a long-lived child on Windows. Regular files avoid inherited
    # pipe handles keeping communicate() open after pg_ctl has already exited.
    RUNTIME.mkdir(exist_ok=True)
    command_log=RUNTIME/'pg-command.log'
    with command_log.open('wb') as log:
        result = subprocess.run([str(exe), *map(str,args)], stdin=subprocess.DEVNULL,
                                stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS,timeout=90)
    if check and result.returncode:
        message=command_log.read_text('utf-8',errors='replace')
        raise RuntimeError(f'{name} failed: {message}')
    return result

def cluster_info():
    return json.loads((RUNTIME / 'postgres-admin.json').read_text('utf-8'))

def admin_connect(dbname='postgres', **kwargs):
    info = cluster_info()
    return psycopg.connect(host='127.0.0.1', port=info['port'], dbname=dbname,
                           user='pawcare_owner', password=info['admin_password'], **kwargs)

def ensure_database():
    env = dotenv_values(ROOT / '.env')
    if env.get('MANAGED_POSTGRES') == '0':
        from .db import transaction, one
        with transaction() as conn:
            if not one(conn,"SELECT to_regclass('pawcare.schema_version') AS name")['name']:
                raise RuntimeError('External database is not initialized. Follow the external database steps in README.')
        return False
    RUNTIME.mkdir(exist_ok=True)
    metadata = RUNTIME / 'postgres-admin.json'
    if not metadata.exists():
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',55432)) == 0:
                raise RuntimeError('Port 55432 is occupied. The existing service was not changed. Resolve the conflict before first setup.')
        metadata.write_text(json.dumps({'port':55432,'admin_password':secrets.token_urlsafe(32),
                                       'app_password':secrets.token_urlsafe(32)}),'utf-8')
    info=cluster_info()
    data=RUNTIME/'postgres-data'
    if not (data/'PG_VERSION').exists():
        password_file=RUNTIME/'init-password.txt'
        try:
            password_file.write_text(info['admin_password'],'utf-8')
            pg_command('initdb','-D',data,'-U','pawcare_owner','--auth=scram-sha-256',
                       '--encoding=UTF8','--locale=C',f'--pwfile={password_file}')
        finally:
            password_file.unlink(missing_ok=True)
    if pg_command('pg_ctl','-D',data,'status',check=False).returncode:
        pg_command('pg_ctl','-D',data,'-l',RUNTIME/'postgres.log','-o',
                   f'-h 127.0.0.1 -p {info["port"]}','-w','start')
    with admin_connect(autocommit=True) as conn:
        real_data=Path(conn.execute('SHOW data_directory').fetchone()[0]).resolve()
        if real_data != data.resolve():
            raise RuntimeError('The database on this port belongs to another project. Initialization stopped.')
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='pawcare_app'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE pawcare_app LOGIN PASSWORD {}').format(sql.Literal(info['app_password'])))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='pawcare'").fetchone():
            conn.execute('CREATE DATABASE pawcare')
    env_path=ROOT/'.env'
    if not env_path.exists():
        env_path.write_text(f'MANAGED_POSTGRES=1\nPG_BIN={pg_bin().as_posix()}\nDB_HOST=127.0.0.1\nDB_PORT={info["port"]}\nDB_NAME=pawcare\nDB_USER=pawcare_app\nDB_PASSWORD={info["app_password"]}\n','utf-8')
    from dotenv import load_dotenv
    load_dotenv(env_path,override=True)
    with admin_connect('pawcare',autocommit=True) as conn:
        if not conn.execute("SELECT to_regclass('pawcare.user_account')").fetchone()[0]:
            conn.execute((ROOT/'database/01_schema.sql').read_text('utf-8'))
        if not conn.execute("SELECT to_regclass('pawcare.schema_version')").fetchone()[0]:
            conn.execute((ROOT/'database/02_rules.sql').read_text('utf-8'))
        if conn.execute('SELECT MAX(version) FROM pawcare.schema_version').fetchone()[0]<2:
            conn.execute((ROOT/'database/04_hardening.sql').read_text('utf-8'))
        if conn.execute('SELECT MAX(version) FROM pawcare.schema_version').fetchone()[0]<3:
            conn.execute((ROOT/'database/05_care_roles.sql').read_text('utf-8'))
        if conn.execute('SELECT MAX(version) FROM pawcare.schema_version').fetchone()[0]<4:
            conn.execute((ROOT/'database/06_english_demo_data.sql').read_text('utf-8'))
        conn.execute('GRANT USAGE ON SCHEMA pawcare TO pawcare_app')
        conn.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA pawcare TO pawcare_app')
        conn.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pawcare TO pawcare_app')
        conn.execute('REVOKE INSERT, UPDATE, DELETE ON pawcare.schema_version FROM pawcare_app')
    from .seed import seed
    seed()
    return True

def stop_database():
    data=RUNTIME/'postgres-data'
    if (data/'PG_VERSION').exists():
        pg_command('pg_ctl','-D',data,'-m','fast','-w','stop',check=False)
