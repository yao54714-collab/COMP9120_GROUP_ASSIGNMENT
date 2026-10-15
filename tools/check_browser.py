"""Run browser flows against a disposable PostgreSQL database, never demo data."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from urllib.request import urlopen
from psycopg import sql
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.bootstrap import ROOT,admin_connect,FLAGS

def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    name='pawcare_browser_'+uuid.uuid4().hex[:12]
    with admin_connect(autocommit=True) as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    process=None
    try:
        with admin_connect(name,autocommit=True) as c:
            for file in ['01_schema.sql','02_rules.sql','04_hardening.sql','05_care_roles.sql','06_english_demo_data.sql']:c.execute((ROOT/'database'/file).read_text('utf-8'))
            c.execute('GRANT USAGE ON SCHEMA pawcare TO pawcare_app')
            c.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA pawcare TO pawcare_app')
            c.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA pawcare TO pawcare_app')
        os.environ['DB_NAME']=name
        from backend.seed import seed
        seed()
        env={**os.environ,'DB_NAME':name,'PAWCARE_TEST_URL':f'http://127.0.0.1:{port}'}
        (ROOT/'test-results').mkdir(exist_ok=True)
        with (ROOT/'test-results/browser-server.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=FLAGS)
            for _ in range(60):
                try:
                    with urlopen(env['PAWCARE_TEST_URL']+'/api/health',timeout=1):break
                except OSError:time.sleep(.2)
            import shutil
            npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm') or 'D:/Node/npm.cmd'
            result=subprocess.run([npm,'exec','playwright','test'],cwd=ROOT/'frontend',env=env)
            if result.returncode:raise SystemExit(result.returncode)
    finally:
        if process:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        assert name.startswith('pawcare_browser_') and len(name)==28
        with admin_connect(autocommit=True) as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

if __name__=='__main__':main()
