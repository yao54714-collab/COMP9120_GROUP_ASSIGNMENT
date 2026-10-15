import os
from pathlib import Path
import sys
import uuid
import pytest
from psycopg import sql

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

@pytest.fixture(scope='session',autouse=True)
def isolated_database():
    from backend.bootstrap import admin_connect
    name='pawcare_test_'+uuid.uuid4().hex[:12]
    old=os.environ.get('DB_NAME')
    with admin_connect(autocommit=True) as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        with admin_connect(name,autocommit=True) as c:
            for f in ['01_schema.sql','02_rules.sql','04_hardening.sql','05_care_roles.sql','06_english_demo_data.sql']:c.execute((ROOT/'database'/f).read_text('utf-8'))
            c.execute('GRANT USAGE ON SCHEMA pawcare TO pawcare_app')
            c.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA pawcare TO pawcare_app')
            c.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA pawcare TO pawcare_app')
        os.environ['DB_NAME']=name
        from backend.seed import seed
        seed()
        yield name
    finally:
        if old is None:os.environ.pop('DB_NAME',None)
        else:os.environ['DB_NAME']=old
        assert name.startswith('pawcare_test_') and len(name)==25
        with admin_connect(autocommit=True) as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

@pytest.fixture
def clients():
    from fastapi.testclient import TestClient
    from backend.api import app
    clients={}
    for role in ['customer','frontdesk','manager','groomer','mia','zhou']:
        client=TestClient(app,headers={'X-PawCare-Client':'web'})
        response=client.post('/api/auth/login',json={'email':role+'@pawcare.local','password':'PawCare2026!'})
        assert response.status_code==200,response.text
        clients[role]=client
    yield clients
    for client in clients.values():client.close()
