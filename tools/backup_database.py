"""Create a private PostgreSQL backup and compare business-table fingerprints."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.bootstrap import ROOT,RUNTIME,pg_bin,cluster_info,admin_connect,FLAGS
from backend.config import SYDNEY
from psycopg import sql

def fingerprint(dbname='pawcare'):
    result={}
    with admin_connect(dbname) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute("SET TIME ZONE 'UTC'")
        tables=c.execute("SELECT tablename FROM pg_tables WHERE schemaname='pawcare' AND tablename NOT IN ('auth_session','schema_version') ORDER BY tablename").fetchall()
        for (name,) in tables:
            rows=c.execute(sql.SQL('SELECT row_to_json(t)::text FROM pawcare.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(name))).fetchall()
            result[name]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(row[0] for row in rows).encode()).hexdigest()}
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compare',type=Path);args=parser.parse_args()
    if args.compare:
        before=json.loads(args.compare.read_text('utf-8'));after=fingerprint()
        changed=[t for t in set(before)|set(after) if before.get(t)!=after.get(t)]
        print('Business data comparison:', 'UNCHANGED' if not changed else 'CHANGED: '+', '.join(sorted(changed)))
        print('Tables checked:',len(after))
        if changed:raise SystemExit(1)
        return
    folder=RUNTIME/'backups'/datetime.now(SYDNEY).strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
    info=cluster_info();backup=folder/'pawcare.dump'
    env={**os.environ,'PGPASSWORD':info['admin_password']}
    subprocess.run([str(pg_bin()/'pg_dump.exe'),'-h','127.0.0.1','-p',str(info['port']),'-U','pawcare_owner','-d','pawcare','-Fc','-f',str(backup)],env=env,check=True,creationflags=FLAGS)
    with (folder/'backup-contents.txt').open('w',encoding='utf-8') as output:
        subprocess.run([str(pg_bin()/'pg_restore.exe'),'--list',str(backup)],stdout=output,check=True,creationflags=FLAGS)
    (folder/'business-data.json').write_text(json.dumps(fingerprint(),indent=2),'utf-8')
    print('Backup:',backup)
    print('Business fingerprint:',folder/'business-data.json')
    print('Backup bytes:',backup.stat().st_size)

if __name__=='__main__':main()
