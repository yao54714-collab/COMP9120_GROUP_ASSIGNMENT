import re
import uuid
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from backend.api import app
from backend.db import transaction, one, all_rows


def register_customer():
    client=TestClient(app,headers={'X-PawCare-Client':'web'})
    email='account-'+uuid.uuid4().hex[:8]+'@example.com'
    response=client.post('/api/auth/register',json={'email':email,'password':'Original2026!','display_name':'Account Test','phone':'0400123456'})
    assert response.status_code==200,response.text
    return client,response.json(),email


def test_seed_and_public_messages_are_english(clients):
    with transaction() as c:
        columns=all_rows(c,"""SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema='pawcare' AND data_type IN ('text','character varying')
            AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='pawcare')""")
        for col in columns:
            rows=c.execute(sql.SQL('SELECT {} FROM pawcare.{}').format(sql.Identifier(col['column_name']),sql.Identifier(col['table_name']))).fetchall()
            assert not any(re.search(r'[\u3400-\u9fff]',str(next(iter(row.values())))) for row in rows),col
    with TestClient(app,headers={'X-PawCare-Client':'web'}) as anonymous:
        response=anonymous.get('/api/accounts')
        assert response.status_code==401 and response.json()['detail']=='Please sign in first.'
    for path in ['/api/bootstrap','/api/appointments','/api/reports','/api/docs']:
        response=clients['manager'].get(path)
        assert response.status_code==200
        assert not re.search(r'[\u3400-\u9fff]',response.text),path


def test_frontend_entry_pages_do_not_reuse_cached_html():
    with TestClient(app) as client:
        for path in ['/', '/?launch=regression', '/bookings', '/api/docs']:
            response=client.get(path)
            assert response.status_code==200
            assert response.headers['content-type'].startswith('text/html')
            assert response.headers['cache-control']=='no-store'
        response=client.get('/api/auth/me')
        assert response.status_code==401
        assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('role',['customer','zhou','frontdesk','groomer','mia'])
def test_accounts_are_manager_only(clients,role):
    client=clients[role]
    assert client.get('/api/accounts').status_code==403
    assert client.put('/api/accounts/6/status',json={'is_active':False}).status_code==403
    assert client.put('/api/accounts/6/password',json={'password':'Changed2026!'}).status_code==403


def test_customer_access_toggle_preserves_history_and_revokes_session(clients):
    customer,user,email=register_customer();aid=user['account_id'];cid=user['customer_id']
    try:
        pet=customer.post('/api/catalog/pets',json={'pet_name':'Access Test Pet','species':'dog'}).json()
        accounts=clients['manager'].get('/api/accounts').json()
        row=next(a for a in accounts if a['account_id']==aid)
        assert row['role']=='customer' and not any('password' in k for k in row)
        assert clients['manager'].put(f'/api/accounts/{aid}/status',json={'is_active':False}).status_code==200
        assert customer.get('/api/auth/me').status_code==401
        assert customer.post('/api/auth/login',json={'email':email,'password':'Original2026!'}).status_code==401
        with transaction() as c:
            assert one(c,'SELECT * FROM customer WHERE customer_id=%s',(cid,))['is_active']
            assert one(c,'SELECT customer_id FROM pet WHERE pet_id=%s',(pet['pet_id'],))['customer_id']==cid
        assert clients['manager'].put(f'/api/accounts/{aid}/status',json={'is_active':True}).status_code==200
        assert customer.post('/api/auth/login',json={'email':email,'password':'Original2026!'}).status_code==200
    finally:customer.close()


def test_password_reset_revokes_old_session_and_requires_new_password(clients):
    customer,user,email=register_customer();aid=user['account_id']
    try:
        assert clients['manager'].put(f'/api/accounts/{aid}/password',json={'password':'short'}).status_code==422
        assert customer.get('/api/auth/me').status_code==200
        assert clients['manager'].put(f'/api/accounts/{aid}/password',json={'password':'Changed2026!'}).status_code==200
        assert customer.get('/api/auth/me').status_code==401
        assert customer.post('/api/auth/login',json={'email':email,'password':'Original2026!'}).status_code==401
        assert customer.post('/api/auth/login',json={'email':email,'password':'Changed2026!'}).status_code==200
    finally:customer.close()


def test_account_status_protects_self_and_assigned_employees(clients):
    manager=clients['manager'];rows=manager.get('/api/accounts').json()
    own=manager.get('/api/auth/me').json()['account_id']
    emma=next(r for r in rows if r['email']=='groomer@pawcare.local')['account_id']
    assert manager.put(f'/api/accounts/{own}/status',json={'is_active':False}).status_code==409
    assert manager.put(f'/api/accounts/{own}/password',json={'password':'Changed2026!'}).status_code==409
    assert manager.put(f'/api/accounts/{emma}/status',json={'is_active':False}).status_code==409
    assert clients['groomer'].get('/api/auth/me').status_code==200


def test_employee_access_and_scheduling_status_change_together(clients):
    manager=clients['manager']
    created=manager.post('/api/employees',json={'employee_code':'ACCOUNT-STAFF','display_name':'Access Test Staff','staff_role':'groomer','email':'account-staff@pawcare.local','password':'Original2026!'})
    assert created.status_code==200
    row=created.json();aid=row['account_id'];eid=row['employee_id']
    for active in [False,True]:
        assert manager.put(f'/api/accounts/{aid}/status',json={'is_active':active}).status_code==200
        with transaction() as c:
            assert one(c,'SELECT is_active FROM employee WHERE employee_id=%s',(eid,))['is_active']==active
            assert one(c,'SELECT is_active FROM user_account WHERE account_id=%s',(aid,))['is_active']==active


def test_inactive_customer_profile_is_not_silently_reactivated(clients):
    customer,user,email=register_customer()
    try:
        assert clients['manager'].put(f"/api/catalog/customers/{user['customer_id']}",json={'display_name':'Account Test','phone':'0400123456','is_active':False}).status_code==200
        assert clients['manager'].put(f"/api/accounts/{user['account_id']}/status",json={'is_active':True}).status_code==409
        assert customer.get('/api/auth/me').status_code==401
    finally:customer.close()


def test_user_entered_multilingual_text_remains_supported(clients):
    # Existing/default content is English; future input is intentionally unrestricted.
    name='Test '+chr(0x732b)
    result=clients['customer'].post('/api/catalog/pets',json={'pet_name':name,'species':'cat'})
    assert result.status_code==200 and result.json()['pet_name']==name
    with transaction() as c:c.execute('DELETE FROM pet WHERE pet_id=%s',(result.json()['pet_id'],))


def test_english_migration_preserves_completed_history_and_restores_guards(isolated_database):
    import json
    from backend.bootstrap import admin_connect, ROOT
    from tools.backup_database import fingerprint
    legacy='清洁与梳毛已完成，建议日常温柔梳理。'
    translated='Bathing and brushing completed. Gentle regular brushing is recommended.'
    with admin_connect(isolated_database) as c:
        c.execute('SET LOCAL search_path TO pawcare, public')
        c.execute('ALTER TABLE pawcare.service_record DISABLE TRIGGER care_record_guard')
        target=c.execute('SELECT appointment_item_id FROM pawcare.service_record WHERE actual_end_at IS NOT NULL ORDER BY appointment_item_id LIMIT 1').fetchone()[0]
        c.execute('UPDATE pawcare.service_record SET result_notes=%s WHERE appointment_item_id=%s',(legacy,target))
        c.execute('SET CONSTRAINTS ALL IMMEDIATE')
        c.execute('ALTER TABLE pawcare.service_record ENABLE TRIGGER care_record_guard')
    before=fingerprint(isolated_database)
    with admin_connect(isolated_database,autocommit=True) as c:
        c.execute("SET TIME ZONE 'UTC'")
        expected=[r[0] for r in c.execute('SELECT row_to_json(t) FROM pawcare.service_record t')]
        for row in expected:
            if row['appointment_item_id']==target:row['result_notes']=translated
        c.execute((ROOT/'database/06_english_demo_data.sql').read_text('utf-8'))
        actual=[r[0] for r in c.execute('SELECT row_to_json(t) FROM pawcare.service_record t')]
        canonical=lambda rows: sorted(json.dumps(r,sort_keys=True) for r in rows)
        assert canonical(actual)==canonical(expected)
        assert c.execute("SELECT count(*) FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='pawcare' AND NOT t.tgisinternal AND t.tgenabled<>'O'").fetchone()[0]==0
    after=fingerprint(isolated_database)
    assert all(before[t]==after[t] for t in before if t!='service_record')
    with admin_connect(isolated_database,autocommit=True) as c:
        c.execute((ROOT/'database/06_english_demo_data.sql').read_text('utf-8'))
    assert fingerprint(isolated_database)==after
