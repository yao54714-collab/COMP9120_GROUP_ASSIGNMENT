from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,time
from itertools import count
import uuid
import psycopg
import pytest
from backend.config import SYDNEY
from backend.db import transaction,one

days=count(5)
def key():return uuid.uuid4().hex
def make_booking(clients,pet=1,service=1,offset=None,items=None):
    date=datetime.now(SYDNEY).date()+timedelta(days=next(days) if offset is None else offset)
    start=datetime.combine(date,time(10),SYDNEY).isoformat()
    r=clients['customer'].post('/api/appointments',json={'requested_start_at':start,'items':items or [{'pet_id':pet,'service_id':service}]})
    assert r.status_code==200,r.text
    a=clients['frontdesk'].get('/api/appointments/'+str(r.json()['appointment_id'])).json()
    return a,start
def plans(a,start):
    return {'items':[{'appointment_item_id':i['appointment_item_id'],'employee_id':3,'workstation_id':1 if i['workstation_type']=='wash' else 3,'planned_start_at':(datetime.fromisoformat(start)+timedelta(minutes=60*n)).isoformat(),'duration_minutes':i['default_duration_minutes'],'agreed_price':str(i['base_price'])} for n,i in enumerate(a['items'])]}
def confirm(clients,a,start):
    r=clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/confirm",json=plans(a,start))
    assert r.status_code==200,r.text
def detail(clients,a):return clients['frontdesk'].get(f"/api/appointments/{a['appointment_id']}").json()

def test_health_and_scope(clients):
    assert clients['customer'].get('/api/health').json()['status']=='ok'
    reference=clients['customer'].get('/api/docs')
    assert reference.status_code==200 and 'PawCare API Reference' in reference.text
    assert 'cdn.jsdelivr.net' not in reference.text
    assert clients['customer'].get('/api/reports').status_code==403
    assert clients['frontdesk'].post('/api/catalog/services',json={'service_code':'BAD','service_name':'bad','species':'dog','workstation_type':'wash','base_price':1,'default_duration_minutes':10}).status_code==403
    assert clients['groomer'].get('/api/inventory/movements').status_code==403
    assert {p['customer_id'] for p in clients['customer'].get('/api/bootstrap').json()['pets']}=={1}
    assert clients['zhou'].get('/api/care-history/1').status_code==404

def test_cross_customer_booking_and_read_rejected(clients):
    a,start=make_booking(clients)
    assert clients['zhou'].get(f"/api/appointments/{a['appointment_id']}").status_code==404
    bad=clients['customer'].post('/api/appointments',json={'requested_start_at':start,'items':[{'pet_id':3,'service_id':3}]})
    assert bad.status_code==409
    assert clients['zhou'].put('/api/catalog/pets/1',json={'pet_name':'stolen','species':'dog'}).status_code==404

def test_species_and_duplicate_items(clients):
    _,start=make_booking(clients)
    for items in [[{'pet_id':1,'service_id':3}],[{'pet_id':1,'service_id':1}]*2]:
        r=clients['customer'].post('/api/appointments',json={'requested_start_at':start,'items':items})
        assert r.status_code==409

def test_multi_pet_multi_service_atomic_confirmation(clients):
    a,start=make_booking(clients,items=[{'pet_id':1,'service_id':1},{'pet_id':1,'service_id':2},{'pet_id':2,'service_id':3}])
    p=plans(a,start);p['items'][2]['workstation_id']=3
    bad=clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/confirm",json=p)
    assert bad.status_code==409
    assert all(i['state']=='requested' and i['agreed_price'] is None for i in detail(clients,a)['items'])
    confirm(clients,a,start)
    assert float(detail(clients,a)['charge_total'])==170

def test_qualification_shift_and_station_validation(clients):
    a,start=make_booking(clients);p=plans(a,start)
    p['items'][0]['employee_id']=2
    assert clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/confirm",json=p).status_code==409
    p=plans(a,start);p['items'][0]['planned_start_at']=start.replace('T10:00','T17:45')
    assert clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/confirm",json=p).status_code==409
    future=datetime.now(SYDNEY).date()+timedelta(days=60)
    p=plans(a,start);p['items'][0]['planned_start_at']=datetime.combine(future,time(10),SYDNEY).isoformat()
    assert clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/confirm",json=p).status_code==409

def test_concurrent_reservations_one_wins(clients):
    offset=next(days);a,start=make_booking(clients,offset=offset);b,_=make_booking(clients,offset=offset)
    def reserve(pair):
        booking,client=pair
        return client.post(f"/api/appointments/{booking['appointment_id']}/confirm",json=plans(booking,start)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,[(a,clients['frontdesk']),(b,clients['manager'])]))
    assert sorted(results)==[200,409]

def test_end_to_end_and_price_snapshot(clients):
    a,start=make_booking(clients);confirm(clients,a,start);iid=a['items'][0]['appointment_item_id']
    assert clients['mia'].post(f'/api/items/{iid}/start').status_code in (404,409)
    assert clients['groomer'].post(f'/api/items/{iid}/start').status_code==200
    before=clients['manager'].get('/api/bootstrap').json()['consumables'][0]['quantity_on_hand']
    r=clients['groomer'].post(f'/api/items/{iid}/complete',json={'result_notes':'Coat cleaned. Brush regularly.','weight_at_visit_kg':'6.35','consumptions':[{'consumable_id':1,'quantity':'25'}]})
    assert r.status_code==200,r.text
    after=clients['manager'].get('/api/bootstrap').json()['consumables'][0]['quantity_on_hand']
    assert float(before)-float(after)==25
    assert detail(clients,a)['overall_state']=='completed'
    assert any(x['appointment_item_id']==iid for x in clients['customer'].get('/api/care-history/1').json())
    assert clients['frontdesk'].post(f'/api/items/{iid}/cancel').status_code==409
    payload={'amount':'55','method':'card','request_key':key()}
    first=clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/payments",json=payload)
    assert first.status_code==200,first.text
    second=clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/payments",json=payload)
    assert second.json()['payment_id']==first.json()['payment_id']
    assert float(detail(clients,a)['amount_due'])==0
    assert clients['frontdesk'].post(f"/api/appointments/{a['appointment_id']}/payments",json={**payload,'request_key':key()}).status_code==409
    svc=clients['manager'].get('/api/bootstrap').json()['services'][0]
    new={k:svc[k] for k in ['service_code','service_name','species','workstation_type','base_price','default_duration_minutes','is_active']};new['base_price']='59'
    assert clients['manager'].put('/api/catalog/services/1',json=new).status_code==200
    assert float(detail(clients,a)['charge_total'])==55
    new['base_price']='55';assert clients['manager'].put('/api/catalog/services/1',json=new).status_code==200

def test_completion_stock_failure_rolls_back_all_steps(clients):
    a,start=make_booking(clients);confirm(clients,a,start);iid=a['items'][0]['appointment_item_id']
    assert clients['groomer'].post(f'/api/items/{iid}/start').status_code==200
    before=clients['manager'].get('/api/bootstrap').json()['consumables']
    r=clients['groomer'].post(f'/api/items/{iid}/complete',json={'result_notes':'should roll back','consumptions':[{'consumable_id':1,'quantity':1},{'consumable_id':2,'quantity':100000}]})
    assert r.status_code==409,r.text
    after=clients['manager'].get('/api/bootstrap').json()['consumables']
    assert before==after
    i=detail(clients,a)['items'][0]
    assert i['state']=='in_progress' and i['actual_end_at'] is None and not i['result_notes']
    with transaction() as c:assert one(c,'SELECT COUNT(*) AS n FROM service_consumption WHERE service_record_id=%s',(iid,))['n']==0

def test_partial_payment_cancel_and_refund_caps(clients):
    a,start=make_booking(clients);confirm(clients,a,start);aid=a['appointment_id'];iid=a['items'][0]['appointment_item_id']
    pay=clients['frontdesk'].post(f'/api/appointments/{aid}/payments',json={'amount':'30','method':'cash','request_key':key()})
    assert pay.status_code==200
    assert float(detail(clients,a)['amount_due'])==25
    assert clients['customer'].post(f'/api/items/{iid}/cancel').status_code==200
    assert float(detail(clients,a)['refund_due'])==30
    body={'payment_id':pay.json()['payment_id'],'amount':'31','reason':'Cancel an unstarted service','request_key':key()}
    assert clients['manager'].post(f'/api/appointments/{aid}/refunds',json=body).status_code==409
    body['amount']='30'
    assert clients['frontdesk'].post(f'/api/appointments/{aid}/refunds',json=body).status_code==403
    first=clients['manager'].post(f'/api/appointments/{aid}/refunds',json=body)
    assert first.status_code==200,first.text
    assert clients['manager'].post(f'/api/appointments/{aid}/refunds',json=body).json()['refund_id']==first.json()['refund_id']
    assert float(detail(clients,a)['refund_due'])==0

def test_concurrent_payments_cannot_overcollect(clients):
    a,start=make_booking(clients);confirm(clients,a,start)
    def pay(client):return client.post(f"/api/appointments/{a['appointment_id']}/payments",json={'amount':'40','method':'card','request_key':key()}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pay,[clients['frontdesk'],clients['manager']]))
    assert sorted(results)==[200,409]
    assert float(detail(clients,a)['paid_total'])==40

def test_inventory_negative_and_immutable_ledger(clients):
    bad=clients['manager'].post('/api/inventory/movements',json={'consumable_id':1,'movement_kind':'waste','quantity_delta':-100000,'reason':'Test stock lower limit','request_key':key()})
    assert bad.status_code==409
    with pytest.raises(psycopg.errors.CheckViolation):
        with transaction() as c:c.execute('UPDATE inventory_movement SET quantity_delta=999 WHERE movement_id=1')
    with transaction() as c:assert one(c,'SELECT quantity_delta FROM inventory_movement WHERE movement_id=1')['quantity_delta']==800

def test_catalog_and_employee_lifecycle(clients):
    manager=clients['manager']
    e=manager.post('/api/employees',json={'employee_code':'EMP-TEST','display_name':'Test groomer','staff_role':'groomer','email':'newstaff@pawcare.local','password':'Testing2026!'}).json()
    assert e.get('employee_id'),e
    assert manager.put(f"/api/employees/{e['employee_id']}/skills",json={'service_ids':[1,2]}).status_code==200
    date=(datetime.now(SYDNEY).date()+timedelta(days=4)).isoformat()
    s=manager.post('/api/shifts',json={'employee_id':e['employee_id'],'starts_at':date+'T09:00','ends_at':date+'T18:00'})
    assert s.status_code==200,s.text
    assert manager.post('/api/shifts',json={'employee_id':e['employee_id'],'starts_at':date+'T10:00','ends_at':date+'T12:00'}).status_code==409
    assert manager.delete('/api/shifts/'+str(s.json()['shift_id'])).status_code==200
    assert manager.put('/api/employees/1',json={'employee_code':'EMP01','display_name':'Li (Manager)','staff_role':'groomer','email':'manager@pawcare.local'}).status_code==409

def test_registration_login_logout_and_origin(clients):
    from fastapi.testclient import TestClient
    from backend.api import app
    with TestClient(app,headers={'X-PawCare-Client':'web'}) as c:
        r=c.post('/api/auth/register',json={'email':'NEW@EXAMPLE.COM','password':'Testing2026!','display_name':'New customer','phone':'0400000999'})
        assert r.status_code==200,r.text
        assert r.json()['email']=='new@example.com'
        assert c.get('/api/bootstrap').json()['pets']==[]
        assert c.post('/api/auth/logout').status_code==200
        assert c.get('/api/auth/me').status_code==401
        assert c.post('/api/auth/login',headers={'Origin':'https://example.com'},json={'email':'customer@pawcare.local','password':'PawCare2026!'}).status_code==403

def test_report_aggregates_match_source(clients):
    r=clients['manager'].get('/api/reports').json()
    assert sum(float(x['received']) for x in r['cash'])==float(r['totals']['received'])
    assert sum(float(x['refunded']) for x in r['cash'])==float(r['totals']['refunded'])
    with transaction() as c:
        actual=one(c,"SELECT SUM(amount) AS n FROM payment WHERE (received_at AT TIME ZONE 'Australia/Sydney')::date BETWEEN %s AND %s",(r['start'],r['end']))['n']
        assert float(actual or 0)==float(r['totals']['received'])

def test_partial_completion_is_not_a_completed_appointment(clients):
    before=clients['manager'].get('/api/reports').json()['totals']
    a,start=make_booking(clients,items=[{'pet_id':1,'service_id':1},{'pet_id':1,'service_id':2}])
    confirm(clients,a,start)
    for index,item in enumerate(a['items']):
        iid=item['appointment_item_id']
        assert clients['groomer'].post(f'/api/items/{iid}/start').status_code==200
        result=clients['groomer'].post(f'/api/items/{iid}/complete',json={'result_notes':'Partial completion test','consumptions':[]})
        assert result.status_code==200,result.text
        totals=clients['manager'].get('/api/reports').json()['totals']
        assert totals['service_items']==before['service_items']+index+1
        assert totals['completed_appointments']==before['completed_appointments']+index

def test_database_protects_history_identity_and_account_roles(clients):
    with transaction() as c:
        completed=one(c,"SELECT appointment_item_id FROM appointment_item WHERE state='completed' ORDER BY appointment_item_id LIMIT 1")['appointment_item_id']
        staff=one(c,'SELECT account_id FROM employee WHERE employee_id=1')['account_id']
    statements=[
        ('UPDATE service_record SET result_notes=%s WHERE appointment_item_id=%s',('overwritten',completed)),
        ('UPDATE pet SET customer_id=2 WHERE pet_id=1',()),
        ("UPDATE service SET species='cat' WHERE service_id=1",()),
        ('INSERT INTO customer_account(customer_id,account_id) VALUES(3,%s)',(staff,)),
    ]
    for query,params in statements:
        with pytest.raises(psycopg.errors.CheckViolation):
            with transaction() as c:c.execute(query,params)
