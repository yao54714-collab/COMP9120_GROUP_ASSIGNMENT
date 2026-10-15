"""Export schema metadata and row counts, without customer rows or credentials."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from psycopg import sql

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.db import transaction,all_rows,one

def main():
    with transaction() as c:
        tables=all_rows(c,"SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='pawcare' ORDER BY table_name")
        for table in tables:
            name=table['table_name']
            table['columns']=all_rows(c,"""SELECT column_name,data_type,udt_name,is_nullable,column_default,
                character_maximum_length,numeric_precision,numeric_scale FROM information_schema.columns
                WHERE table_schema='pawcare' AND table_name=%s ORDER BY ordinal_position""",(name,))
            table['constraints']=all_rows(c,"""SELECT con.conname AS name,con.contype AS kind,
                pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con
                JOIN pg_class rel ON rel.oid=con.conrelid JOIN pg_namespace n ON n.oid=rel.relnamespace
                WHERE n.nspname='pawcare' AND rel.relname=%s ORDER BY con.conname""",(name,))
            table['row_count']=one(c,sql.SQL('SELECT COUNT(*) AS n FROM pawcare.{}').format(sql.Identifier(name)))['n']
        result={'generated_at':datetime.now(timezone.utc).isoformat(),
                'database':one(c,'SELECT current_database() AS name')['name'],'schema':'pawcare',
                'schema_version':one(c,'SELECT MAX(version) AS version FROM schema_version')['version'],
                'table_count':sum(t['table_type']=='BASE TABLE' for t in tables),
                'view_count':sum(t['table_type']=='VIEW' for t in tables),'relations':tables}
    target=ROOT/'docs/schema-inventory.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),'utf-8')
    print(f"Exported {result['table_count']} tables and {result['view_count']} views to docs/schema-inventory.json (schema version {result['schema_version']}).")

if __name__=='__main__':main()
