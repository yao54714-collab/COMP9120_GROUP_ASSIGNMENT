"""Register just the PawCare connection through pgAdmin's supported importer."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.bootstrap import ROOT,RUNTIME,pg_bin,FLAGS
from backend.config import database_config

def main():
    RUNTIME.mkdir(exist_ok=True)
    config=database_config()
    passfile=RUNTIME/'pgadmin.pgpass'
    def escaped(value):return str(value).replace('\\','\\\\').replace(':','\\:')
    passfile.write_text(':'.join(escaped(config[k]) for k in ['host','port','dbname','user','password'])+'\n','utf-8')
    name='PawCare 本地项目'
    definition={'Servers':{'1':{'Name':name,'Group':'PawCare','Host':config['host'],'Port':config['port'],
                 'MaintenanceDB':config['dbname'],'Username':config['user'],'SSLMode':'prefer',
                 'ConnectionParameters':{'sslmode':'prefer','connect_timeout':10,'passfile':str(passfile)},
                 'Comment':'PawCare isolated local database; run python run.py before connecting.',
                 'PostConnectionSQL':"SET search_path TO pawcare, public; SET TIME ZONE 'Australia/Sydney';"}}}
    target=ROOT/'database/pgadmin-servers.json'
    target.write_text(json.dumps(definition,ensure_ascii=True,indent=2),'utf-8')
    install=pg_bin().parent/'pgAdmin 4'
    python=install/'python/python.exe'
    setup=install/'web/setup.py'
    db=Path(os.environ.get('APPDATA',''))/'pgAdmin/pgadmin4.db'
    if not all(p.exists() for p in [python,setup,db]):
        print('Connection definition generated: database/pgadmin-servers.json. Import it in pgAdmin Tools > Import/Export Servers.')
        return
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
        existing=c.execute('SELECT name,host,port,username FROM server WHERE name=?',(name,)).fetchall()
        if existing:
            print('PawCare pgAdmin connection already exists. No existing connections changed.')
            return
        with sqlite3.connect(RUNTIME/'pgadmin-before-pawcare.db') as backup:c.backup(backup)
    env={**os.environ,'PYTHONUTF8':'1','PATH':str(pg_bin())+os.pathsep+os.environ.get('PATH','')}
    result=subprocess.run([str(python),str(ROOT/'tools/pgadmin_entry.py'),str(pg_bin()),str(setup),
                           'load-servers',str(target),'--sqlite-path',str(db)],
                          capture_output=True,creationflags=FLAGS,timeout=90,env=env)
    if result.returncode:
        print(result.stderr.decode('utf-8',errors='replace')[-1500:])
        raise RuntimeError('pgAdmin import failed; use the generated JSON through Tools > Import/Export Servers.')
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
        if not c.execute('SELECT 1 FROM server WHERE name=? AND port=?',(name,config['port'])).fetchone():
            print(result.stdout.decode('utf-8',errors='replace')[-1800:])
            raise RuntimeError('pgAdmin did not import the connection. The JSON file remains available for manual import.')
    print('PawCare connection registered in pgAdmin. Refresh the server tree. Password is read from the project-owned pgpass file.')

if __name__=='__main__':main()
