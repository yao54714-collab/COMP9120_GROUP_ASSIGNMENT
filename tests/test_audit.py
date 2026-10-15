"""Regression cases for the overall audit and its fixes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,time
import uuid
import pytest
import psycopg
from fastapi.testclient import TestClient
from backend.api import app
from backend.config import SYDNEY
from backend.db import transaction,one

def key():return uuid.uuid4().hex

def book(clients,offset=30,items=None):
    start=datetime.combine(datetime.now(SYDNEY).date()+timedelta(days=offset),time(13),SYDNEY)
    result=clients['customer'].post('/api/appointments',json={'requested_start_at':start.isoformat(),'items':items or [{'pet_id':2,'service_id':3}]})
    assert result.status_code==200,result.text
    aid=result.json()['appointment_id']
    a=clients['frontdesk'].get(f'/api/appointments/{aid}').json()
    cursor=start;plans=[]
    for i in a['items']:
        plans.append({'appointment_item_id':i['appointment_item_id'],'employee_id':3,'workstation_id':1 if i['workstation_type']=='wash' else 3,'planned_start_at':cursor.isoformat(),'duration_minutes':i['default_duration_minutes'],'agreed_price':i['base_price']})
        cursor+=timedelta(minutes=i['default_duration_minutes'])
    result=clients['frontdesk'].post(f'/api/appointments/{aid}/confirm',json={'items':plans})
    assert result.status_code==200,result.text
    return clients['frontdesk'].get(f'/api/appointments/{aid}').json()

def test_audit_unauthenticated_access_is_denied():
    with TestClient(app,headers={'X-PawCare-Client':'web'}) as c:
        for path in ['/api/bootstrap','/api/appointments','/api/appointments/1','/api/reports','/api/care-history/1','/api/shifts?start=2026-10-13&end=2026-10-14']:
            assert c.get(path).status_code==401,path

def test_audit_role_write_permissions(clients):
    payload={'amount':'1.00','method':'cash','request_key':key()}
    for role in ['customer','zhou','groomer','mia']:
        assert clients[role].post('/api/appointments/9/payments',json=payload).status_code==403
    for role in ['customer','zhou','groomer','mia','frontdesk']:
        assert clients[role].post('/api/inventory/movements',json={'consumable_id':1,'movement_kind':'receipt','quantity_delta':1,'reason':'unauthorised','request_key':key()}).status_code==403
        assert clients[role].put('/api/employees/3/skills',json={'service_ids':[]}).status_code==403
        assert clients[role].post('/api/appointments/1/refunds',json={'payment_id':1,'amount':1,'reason':'unauthorised','request_key':key()}).status_code==403

def test_audit_cat_two_services_payment_cancel_and_concurrent_refund(clients):
    a=book(clients,30,[{'pet_id':2,'service_id':3},{'pet_id':2,'service_id':4}]);aid=a['appointment_id']
    assert float(a['charge_total'])==110
    ids=[]
    for amount in ['60.00','50.00']:
        r=clients['frontdesk'].post(f'/api/appointments/{aid}/payments',json={'amount':amount,'method':'card','request_key':key()})
        assert r.status_code==200,r.text
        ids.append(r.json()['payment_id'])
    assert clients['customer'].post(f"/api/items/{a['items'][1]['appointment_item_id']}/cancel").status_code==200
    detail=clients['frontdesk'].get(f'/api/appointments/{aid}').json()
    assert float(detail['charge_total'])==75 and float(detail['refund_due'])==35
    def refund(_):
        return clients['manager'].post(f'/api/appointments/{aid}/refunds',json={'payment_id':ids[0],'amount':'30','reason':'Partial cancellation','request_key':key()}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(refund,range(2)))
    assert sorted(statuses)==[200,409]
    detail=clients['frontdesk'].get(f'/api/appointments/{aid}').json()
    assert float(detail['refund_due'])==5 and float(detail['amount_due'])==0

def test_audit_money_precision_and_negative_values_rejected(clients):
    a=book(clients,31)
    for amount in ['-1','0','0.001','100000.01']:
        r=clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/payments",json={'amount':amount,'method':'card','request_key':key()})
        assert r.status_code==422,(amount,r.status_code,r.text)
    assert float(clients['frontdesk'].get(f"/api/appointments/{a['appointment_id']}").json()['paid_total'])==0

def test_audit_sql_and_html_input_remain_literal_data(clients):
    name="QA <img src=x onerror=alert(1)> '); DROP TABLE pet;--"
    r=clients['customer'].post('/api/catalog/pets',json={'pet_name':name,'species':'cat'})
    assert r.status_code==200,r.text
    pid=r.json()['pet_id']
    with transaction() as c:assert one(c,'SELECT pet_name FROM pet WHERE pet_id=%s',(pid,))['pet_name']==name

def test_audit_employee_password_change_revokes_old_session(clients):
    body={'employee_code':'QA-AUTH','display_name':'QA auth','staff_role':'groomer','email':'qa-auth@pawcare.local','password':'Initial2026!'}
    r=clients['manager'].post('/api/employees',json=body);assert r.status_code==200,r.text
    eid=r.json()['employee_id']
    with TestClient(app,headers={'X-PawCare-Client':'web'}) as c:
        assert c.post('/api/auth/login',json={'email':body['email'],'password':body['password']}).status_code==200
        assert clients['manager'].put(f'/api/employees/{eid}',json={**body,'password':'Changed2026!'}).status_code==200
        assert c.get('/api/auth/me').status_code==401
        assert c.post('/api/auth/login',json={'email':body['email'],'password':'Initial2026!'}).status_code==401
        assert c.post('/api/auth/login',json={'email':body['email'],'password':'Changed2026!'}).status_code==200

def test_audit_concurrent_inventory_cannot_go_negative(clients):
    r=clients['manager'].post('/api/catalog/consumables',json={'sku':'QA-STOCK','consumable_name':'QA concurrent stock','base_unit':'unit','reorder_level':0})
    assert r.status_code==200,r.text
    cid=r.json()['consumable_id']
    assert clients['manager'].post('/api/inventory/movements',json={'consumable_id':cid,'movement_kind':'receipt','quantity_delta':10,'reason':'QA initial','request_key':key()}).status_code==200
    def consume(_):return clients['manager'].post('/api/inventory/movements',json={'consumable_id':cid,'movement_kind':'waste','quantity_delta':-7,'reason':'QA concurrent','request_key':key()}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(consume,range(2)))
    assert sorted(statuses)==[200,409]
    with transaction() as c:assert one(c,'SELECT quantity_on_hand FROM inventory_balance WHERE consumable_id=%s',(cid,))['quantity_on_hand']==3

def test_audit_invalid_shift_date_is_validation_error(clients):
    response=clients['manager'].get('/api/shifts?start=not-a-date&end=2026-10-14')
    assert response.status_code==422,f'Expected validation error, received {response.status_code}: {response.text}'

def test_audit_cannot_remove_groomer_role_with_assigned_tasks(clients):
    employee=next(e for e in clients['manager'].get('/api/bootstrap').json()['employees'] if e['employee_id']==3)
    body={k:employee[k] for k in ['employee_code','display_name','staff_role','email','is_active']}
    try:
        result=clients['manager'].put('/api/employees/3',json={**body,'staff_role':'receptionist'})
        subsequent=clients['groomer'].post('/api/items/9/start') if result.status_code==200 else None
        assert result.status_code==409,f'Role change returned {result.status_code}; assigned employee start returned {subsequent.status_code if subsequent is not None else None}'
    finally:
        assert clients['manager'].put('/api/employees/3',json=body).status_code==200

def test_audit_receptionist_not_offered_for_grooming(clients):
    assert clients['manager'].put('/api/employees/2/skills',json={'service_ids':[3]}).status_code==409
    # Legacy qualifications remain historical data after a permitted role change.
    # They must not make a receptionist eligible for new care assignments.
    body={'employee_code':'QA-ROLE','display_name':'QA role','staff_role':'groomer','email':'qa-role@pawcare.local','password':'Testing2026!'}
    employee=clients['manager'].post('/api/employees',json=body)
    assert employee.status_code==200,employee.text
    eid=employee.json()['employee_id']
    assert clients['manager'].put(f'/api/employees/{eid}/skills',json={'service_ids':[3]}).status_code==200
    day=datetime.now(SYDNEY).date()+timedelta(days=32)
    shift=clients['manager'].post('/api/shifts',json={'employee_id':eid,'starts_at':day.isoformat()+'T09:00','ends_at':day.isoformat()+'T18:00'})
    assert shift.status_code==200,shift.text
    assert clients['manager'].put(f'/api/employees/{eid}',json={**body,'staff_role':'receptionist','password':''}).status_code==200
    try:
        r=clients['frontdesk'].get('/api/availability',params={'service_id':3,'pet_id':2,'starts_at':day.isoformat()+'T10:00','duration':60})
        assert r.status_code==200,r.text
        assert all(x['employee_id'] not in [2,eid] for x in r.json()),'Receptionist appears as an available groomer but cannot start/complete care.'
        a=book(clients,32);item=a['items'][0]
        plan={'appointment_item_id':item['appointment_item_id'],'employee_id':eid,'workstation_id':1,'planned_start_at':day.isoformat()+'T13:00','duration_minutes':60,'agreed_price':'75'}
        assert clients['manager'].post(f"/api/appointments/{a['appointment_id']}/confirm",json={'items':[plan]}).status_code==409
        assert clients['manager'].get(f"/api/appointments/{a['appointment_id']}").json()['items'][0]['employee_id']==3
    finally:
        clients['manager'].put(f'/api/employees/{eid}/skills',json={'service_ids':[]})
        clients['manager'].delete('/api/shifts/'+str(shift.json()['shift_id']))

def test_role_guards_also_protect_direct_database_writes(clients):
    for query in ["UPDATE employee SET staff_role='receptionist' WHERE employee_id=3",
                  "UPDATE employee SET is_active=false WHERE employee_id=3",
                  'INSERT INTO employee_service(employee_id,service_id) VALUES(2,3)']:
        with pytest.raises(psycopg.errors.CheckViolation):
            with transaction() as c:c.execute(query)

def test_role_change_is_blocked_during_care_but_manager_promotion_is_valid(clients):
    a=book(clients,33);iid=a['items'][0]['appointment_item_id']
    assert clients['groomer'].post(f'/api/items/{iid}/start').status_code==200
    employee=next(e for e in clients['manager'].get('/api/bootstrap').json()['employees'] if e['employee_id']==3)
    body={k:employee[k] for k in ['employee_code','display_name','staff_role','email','is_active']}
    try:
        assert clients['manager'].put('/api/employees/3',json={**body,'staff_role':'receptionist'}).status_code==409
        assert clients['manager'].put('/api/employees/3',json={**body,'staff_role':'manager'}).status_code==200
        assert clients['groomer'].post(f'/api/items/{iid}/complete',json={'result_notes':'Care can still be completed after promotion to manager.','consumptions':[]}).status_code==200
    finally:
        assert clients['manager'].put('/api/employees/3',json=body).status_code==200

@pytest.mark.parametrize('start,end',[('', '2026-10-14'),('2026-10-15','2026-10-14'),('2025-01-01','2026-10-14')])
def test_shift_ranges_are_validated_before_sql(clients,start,end):
    response=clients['manager'].get('/api/shifts',params={'start':start,'end':end})
    assert response.status_code==422,response.text

def test_recipe_cannot_add_inactive_consumables(clients):
    manager=clients['manager'];supply=next(c for c in manager.get('/api/bootstrap').json()['consumables'] if c['consumable_id']==3)
    body={k:supply[k] for k in ['sku','consumable_name','base_unit','reorder_level','is_active']}
    before=[r for r in manager.get('/api/bootstrap').json()['recipes'] if r['service_id']==4]
    try:
        assert manager.put('/api/catalog/consumables/3',json={**body,'is_active':False}).status_code==200
        assert manager.put('/api/services/4/recipe',json={'consumptions':[{'consumable_id':3,'quantity':1}]}).status_code==409
        assert [r for r in manager.get('/api/bootstrap').json()['recipes'] if r['service_id']==4]==before
    finally:
        assert manager.put('/api/catalog/consumables/3',json=body).status_code==200
