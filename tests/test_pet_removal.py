from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time
from threading import Barrier
import uuid

import pytest
from fastapi.testclient import TestClient
from backend.api import app
from backend.config import SYDNEY
from backend.db import transaction, one, all_rows


def new_pet(clients, customer_id=1):
    response=clients['frontdesk'].post('/api/catalog/pets',json={
        'customer_id':customer_id,'pet_name':'Removal '+uuid.uuid4().hex[:8],'species':'cat'})
    assert response.status_code==200,response.text
    return response.json()


def book(clients,pet):
    start=datetime.combine(datetime.now(SYDNEY).date()+timedelta(days=3),time(15),SYDNEY).isoformat()
    response=clients['customer'].post('/api/appointments',json={
        'requested_start_at':start,'items':[{'pet_id':pet['pet_id'],'service_id':3}]})
    return response


def bootstrap_pet(client,pid):
    return next((p for p in client.get('/api/bootstrap').json()['pets'] if p['pet_id']==pid),None)


@pytest.mark.parametrize('role,owner',[('customer',1),('frontdesk',3),('manager',3)])
def test_delete_unused_pet_and_repeated_delete(clients,role,owner):
    pet=new_pet(clients,owner);pid=pet['pet_id']
    assert bootstrap_pet(clients[role],pid)['has_booking_history'] is False
    result=clients[role].delete(f'/api/catalog/pets/{pid}')
    assert result.status_code==200,result.text
    assert bootstrap_pet(clients['manager'],pid) is None
    assert clients[role].delete(f'/api/catalog/pets/{pid}').status_code==404
    assert clients[role].get(f'/api/care-history/{pid}').status_code==404
    with transaction() as c:
        assert one(c,'SELECT 1 FROM pet WHERE pet_id=%s',(pid,)) is None
        assert one(c,'SELECT 1 FROM customer WHERE customer_id=%s',(owner,))


@pytest.mark.parametrize('operation',['delete','deactivate'])
def test_removal_permissions_and_missing_pet(clients,operation):
    pet=new_pet(clients);pid=pet['pet_id']
    def attempt(client,id):
        return client.delete(f'/api/catalog/pets/{id}') if operation=='delete' else client.post(f'/api/catalog/pets/{id}/deactivate')
    with TestClient(app,headers={'X-PawCare-Client':'web'}) as anonymous:
        assert attempt(anonymous,pid).status_code==401
    assert attempt(clients['zhou'],pid).status_code==404
    assert attempt(clients['groomer'],pid).status_code==403
    assert attempt(clients['manager'],999999999).status_code==404
    assert bootstrap_pet(clients['customer'],pid)['is_active'] is True


def test_unfinished_and_cancelled_booking_history_protected(clients):
    pet=new_pet(clients);pid=pet['pet_id']
    booking=book(clients,pet);assert booking.status_code==200,booking.text
    aid=booking.json()['appointment_id']
    current=bootstrap_pet(clients['customer'],pid)
    assert current['has_booking_history'] and current['has_unfinished_bookings']
    assert clients['customer'].delete(f'/api/catalog/pets/{pid}').status_code==409
    result=clients['customer'].post(f'/api/catalog/pets/{pid}/deactivate')
    assert result.status_code==409 and 'unfinished bookings' in result.json()['detail']
    detail=clients['customer'].get(f'/api/appointments/{aid}').json()
    iid=detail['items'][0]['appointment_item_id']
    assert clients['customer'].post(f'/api/items/{iid}/cancel').status_code==200
    assert clients['customer'].delete(f'/api/catalog/pets/{pid}').status_code==409
    assert clients['customer'].post(f'/api/catalog/pets/{pid}/deactivate').status_code==200
    current=bootstrap_pet(clients['customer'],pid)
    assert not current['is_active'] and current['has_booking_history'] and not current['has_unfinished_bookings']
    assert clients['customer'].get(f'/api/appointments/{aid}').json()['items'][0]['state']=='cancelled'
    assert book(clients,pet).status_code==409
    # Restore via the existing profile editor and book again.
    editable={k:pet[k] for k in ['customer_id','pet_name','species','breed','birth_date','sex','latest_weight_kg','care_notes','is_active']}
    assert clients['customer'].put(f'/api/catalog/pets/{pid}',json=editable).status_code==200
    assert book(clients,pet).status_code==200


def test_completed_pet_preserves_care_finance_and_profile_fields(clients):
    # Isolated seed pet Max has completed history and no unfinished bookings.
    pid=6
    history=clients['manager'].get(f'/api/care-history/{pid}').json()
    assert history
    with transaction() as c:
        before=one(c,'SELECT * FROM pet WHERE pet_id=%s',(pid,))
        related=all_rows(c,'SELECT * FROM appointment_item WHERE pet_id=%s ORDER BY appointment_item_id',(pid,))
        finances=all_rows(c,'SELECT * FROM appointment_financials WHERE appointment_id=ANY(%s) ORDER BY appointment_id',([r['appointment_id'] for r in related],))
    assert clients['manager'].delete(f'/api/catalog/pets/{pid}').status_code==409
    assert clients['frontdesk'].post(f'/api/catalog/pets/{pid}/deactivate').status_code==200
    assert clients['manager'].get(f'/api/care-history/{pid}').json()==history
    with transaction() as c:
        assert one(c,'SELECT * FROM pet WHERE pet_id=%s',(pid,))=={**before,'is_active':False}
        assert all_rows(c,'SELECT * FROM appointment_item WHERE pet_id=%s ORDER BY appointment_item_id',(pid,))==related
        assert all_rows(c,'SELECT * FROM appointment_financials WHERE appointment_id=ANY(%s) ORDER BY appointment_id',([r['appointment_id'] for r in related],))==finances
        # Leave the shared isolated seed state unchanged for unrelated tests.
        c.execute('UPDATE pet SET is_active=%s WHERE pet_id=%s',(before['is_active'],pid))


@pytest.mark.parametrize('pid',[1,3])
def test_scheduled_and_in_progress_pet_cannot_be_deactivated(clients,pid):
    assert clients['manager'].delete(f'/api/catalog/pets/{pid}').status_code==409
    assert clients['manager'].post(f'/api/catalog/pets/{pid}/deactivate').status_code==409
    assert bootstrap_pet(clients['manager'],pid)['is_active'] is True


@pytest.mark.parametrize('operation',['delete','deactivate'])
def test_booking_racing_removal_is_atomic(clients,operation):
    pet=new_pet(clients);pid=pet['pet_id'];barrier=Barrier(2)
    def remove():
        barrier.wait()
        return clients['frontdesk'].delete(f'/api/catalog/pets/{pid}') if operation=='delete' else clients['frontdesk'].post(f'/api/catalog/pets/{pid}/deactivate')
    def reserve():
        barrier.wait()
        return book(clients,pet)
    with ThreadPoolExecutor(max_workers=2) as pool:
        removed=pool.submit(remove);booked=pool.submit(reserve)
        deletion,booking=removed.result(),booked.result()
    assert (deletion.status_code,booking.status_code) in ([(200,404),(409,200)] if operation=='delete' else [(200,409),(409,200)])
    with transaction() as c:
        row=one(c,'SELECT * FROM pet WHERE pet_id=%s',(pid,))
        count=one(c,'SELECT COUNT(*) AS n FROM appointment_item WHERE pet_id=%s',(pid,))['n']
        if booking.status_code==200:
            assert row['is_active'] and count==1
        else:
            assert count==0
            assert row is None if operation=='delete' else row['is_active'] is False
