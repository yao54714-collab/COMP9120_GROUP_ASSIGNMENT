from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from pydantic import ValidationError
from psycopg import sql
from . import models as m
from .auth import get_user,email_address
from .common import require,check,found,aware
from .db import transaction,one,all_rows,schedule_lock
from .security import password_hash

router=APIRouter(prefix='/api')
TABLES={'customers':('customer','customer_id',m.CustomerInput),'pets':('pet','pet_id',m.PetInput),
        'services':('service','service_id',m.ServiceInput),'stations':('workstation','workstation_id',m.StationInput),
        'consumables':('consumable','consumable_id',m.ConsumableInput)}
PET_QUERY='''SELECT p.*,c.display_name AS owner_name,
    EXISTS(SELECT 1 FROM appointment_item i WHERE i.pet_id=p.pet_id) AS has_booking_history,
    EXISTS(SELECT 1 FROM appointment_item i WHERE i.pet_id=p.pet_id
           AND i.state IN ('requested','scheduled','in_progress')) AS has_unfinished_bookings
    FROM pet p JOIN customer c USING(customer_id)'''

def write(c,table,key,data,id=None):
    fields=list(data)
    if id is None:
        query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(sql.Placeholder() for _ in fields))
        return one(c,query,list(data.values()))
    query=sql.SQL('UPDATE {} SET {} WHERE {}=%s RETURNING *').format(sql.Identifier(table),sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in fields),sql.Identifier(key))
    return found(one(c,query,[*data.values(),id]))

@router.get('/bootstrap')
def bootstrap(user=Depends(get_user)):
    with transaction() as c:
        if user['role']=='customer':
            customers=all_rows(c,'SELECT * FROM customer WHERE customer_id=%s',(user['customer_id'],))
            pets=all_rows(c,PET_QUERY+' WHERE p.customer_id=%s ORDER BY pet_id',(user['customer_id'],))
        elif user['role']=='groomer':
            customers=[]
            pets=all_rows(c,PET_QUERY+'''
              WHERE EXISTS(SELECT 1 FROM appointment_item i WHERE i.pet_id=p.pet_id AND i.employee_id=%s) ORDER BY pet_id''',(user['employee_id'],))
        else:
            customers=all_rows(c,'SELECT * FROM customer ORDER BY customer_id DESC')
            pets=all_rows(c,PET_QUERY+' ORDER BY pet_id DESC')
        staff=user['role']!='customer'
        return {'user':user,'customers':customers,'pets':pets,
            'services':all_rows(c,'SELECT * FROM service'+('' if user['role']=='manager' else ' WHERE is_active')+' ORDER BY service_id'),
            'stations':all_rows(c,'SELECT * FROM workstation ORDER BY workstation_id') if staff else [],
            'employees':all_rows(c,'SELECT e.*,u.email FROM employee e JOIN user_account u USING(account_id) ORDER BY employee_id') if staff else [],
            'skills':all_rows(c,'SELECT * FROM employee_service WHERE is_active') if staff else [],
            'consumables':all_rows(c,'SELECT c.*,b.quantity_on_hand FROM consumable c JOIN inventory_balance b USING(consumable_id) ORDER BY consumable_id') if staff else [],
            'recipes':all_rows(c,'SELECT * FROM service_consumable') if staff else []}

def catalog_write(kind,id,body,user):
    if kind not in TABLES:raise HTTPException(404,'Catalogue not found.')
    table,key,model=TABLES[kind]
    try:data=model.model_validate(body).model_dump()
    except ValidationError as exc:raise HTTPException(422,str(exc.errors()[0]['msg']))
    if kind in ['services','stations','consumables']:require(user,'manager')
    elif kind=='customers':require(user,'manager','receptionist','customer')
    else:require(user,'manager','receptionist','customer')
    with transaction() as c:
        schedule_lock(c)
        old=found(one(c,sql.SQL('SELECT * FROM {} WHERE {}=%s FOR UPDATE').format(sql.Identifier(table),sql.Identifier(key)),(id,))) if id else None
        if kind=='customers' and user['role']=='customer':
            check(id==user['customer_id'],'You can only edit your own profile.')
            data['is_active']=True
        if kind=='pets':
            if user['role']=='customer':
                if old and old['customer_id']!=user['customer_id']:raise HTTPException(404,'Pet not found.')
                data['customer_id']=user['customer_id']
            check(data['customer_id'] is not None,'Select the pet owner.')
            owner=found(one(c,'SELECT * FROM customer WHERE customer_id=%s',(data['customer_id'],)))
            check(owner['is_active'],'The customer profile is inactive.')
            if old and (old['customer_id']!=data['customer_id'] or old['species']!=data['species']):
                check(not one(c,'SELECT 1 FROM appointment_item WHERE pet_id=%s',(id,)),'Pets with booking history cannot change owner or species.')
        if old:
            reference={'pets':'pet_id','services':'service_id','stations':'workstation_id'}.get(kind)
            if reference and not data['is_active']:
                check(not one(c,sql.SQL("SELECT 1 FROM appointment_item WHERE {}=%s AND state IN ('requested','scheduled','in_progress')").format(sql.Identifier(reference)),(id,)),'This profile has unfinished bookings and cannot be deactivated.')
            if kind=='customers' and not data['is_active']:
                check(not one(c,"SELECT 1 FROM appointment a JOIN appointment_item i USING(appointment_id) WHERE a.customer_id=%s AND i.state IN ('requested','scheduled','in_progress')",(id,)),'This customer has unfinished bookings.')
            if kind=='services' and (old['species'],old['workstation_type'])!=(data['species'],data['workstation_type']):
                check(not one(c,'SELECT 1 FROM appointment_item WHERE service_id=%s',(id,)),'This service has booking history. Create a new service to change its species or station type.')
            if kind=='stations' and old['workstation_type']!=data['workstation_type']:
                check(not one(c,'SELECT 1 FROM appointment_item WHERE workstation_id=%s',(id,)),'The station has booking history. Its type cannot be changed.')
            if kind=='consumables' and old['base_unit']!=data['base_unit']:
                check(not one(c,'SELECT 1 FROM inventory_movement WHERE consumable_id=%s',(id,)),'Units cannot be changed for consumables with stock movements.')
        return write(c,table,key,data,id)

@router.post('/catalog/{kind}')
def create(kind:str,body:dict,user=Depends(get_user)):return catalog_write(kind,None,body,user)

@router.put('/catalog/{kind}/{id}')
def edit(kind:str,id:int,body:dict,user=Depends(get_user)):return catalog_write(kind,id,body,user)

def pet_for_removal(c,id,user):
    # Use the same lock as booking creation, so a new booking cannot race deletion.
    schedule_lock(c)
    pet=found(one(c,'SELECT * FROM pet WHERE pet_id=%s FOR UPDATE',(id,)),'Pet not found.')
    if user['role']=='customer' and pet['customer_id']!=user['customer_id']:
        raise HTTPException(404,'Pet not found.')
    return pet


@router.delete('/catalog/pets/{id}')
def delete_pet(id:int,user=Depends(get_user)):
    require(user,'manager','receptionist','customer')
    with transaction() as c:
        pet_for_removal(c,id,user)
        check(not one(c,'SELECT 1 FROM appointment_item WHERE pet_id=%s',(id,)),
              'This pet has booking history and cannot be deleted. Deactivate the profile instead to keep its records.')
        c.execute('DELETE FROM pet WHERE pet_id=%s',(id,))
    return {'ok':True}


@router.post('/catalog/pets/{id}/deactivate')
def deactivate_pet(id:int,user=Depends(get_user)):
    require(user,'manager','receptionist','customer')
    with transaction() as c:
        pet_for_removal(c,id,user)
        check(not one(c,"SELECT 1 FROM appointment_item WHERE pet_id=%s AND state IN ('requested','scheduled','in_progress')",(id,)),
              'This pet has unfinished bookings. Finish or cancel them before deactivating the profile.')
        c.execute('UPDATE pet SET is_active=false WHERE pet_id=%s',(id,))
    return {'ok':True}


def employee_write(id,data,user):
    require(user,'manager')
    with transaction() as c:
        schedule_lock(c)
        old=found(one(c,'SELECT * FROM employee WHERE employee_id=%s FOR UPDATE',(id,))) if id else None
        if old:
            if id==user['employee_id']:check(data.is_active and data.staff_role=='manager','You cannot deactivate yourself or remove your own manager role.')
            if data.staff_role not in ('groomer','manager'):
                check(not one(c,"SELECT 1 FROM appointment_item WHERE employee_id=%s AND state IN ('scheduled','in_progress')",(id,)),'Finish or reassign outstanding care tasks before changing this employee to a receptionist.')
            if not data.is_active:
                check(not one(c,"SELECT 1 FROM appointment_item WHERE employee_id=%s AND state IN ('scheduled','in_progress')",(id,)),'This employee has unfinished tasks.')
            c.execute('UPDATE user_account SET email=%s,is_active=%s WHERE account_id=%s',(email_address(data.email),data.is_active,old['account_id']))
            account_id=old['account_id']
        else:
            check(len(data.password)>=8,'New employee password must contain at least 8 characters.')
            account_id=one(c,'INSERT INTO user_account(email,password_hash) VALUES(%s,%s) RETURNING account_id',(email_address(data.email),password_hash(data.password)))['account_id']
        if data.password:
            check(len(data.password)>=8,'Password must contain at least 8 characters.')
            c.execute('UPDATE user_account SET password_hash=%s WHERE account_id=%s',(password_hash(data.password),account_id))
            c.execute('DELETE FROM auth_session WHERE account_id=%s',(account_id,))
        fields=data.model_dump(exclude={'email','password'});fields['account_id']=account_id
        return write(c,'employee','employee_id',fields,id)

@router.post('/employees')
def employee_create(data:m.EmployeeInput,user=Depends(get_user)):return employee_write(None,data,user)
@router.put('/employees/{id}')
def employee_edit(id:int,data:m.EmployeeInput,user=Depends(get_user)):return employee_write(id,data,user)

@router.put('/employees/{id}/skills')
def skills(id:int,data:m.SkillInput,user=Depends(get_user)):
    require(user,'manager')
    with transaction() as c:
        schedule_lock(c);employee=found(one(c,'SELECT * FROM employee WHERE employee_id=%s',(id,)))
        check(not data.service_ids or employee['staff_role'] in ('groomer','manager'),'Only groomers and managers can hold care qualifications.')
        check(not one(c,"SELECT 1 FROM appointment_item WHERE employee_id=%s AND state IN ('scheduled','in_progress') AND NOT(service_id=ANY(%s))",(id,data.service_ids)),'Qualifications required by unfinished tasks cannot be removed.')
        c.execute('UPDATE employee_service SET is_active=false WHERE employee_id=%s',(id,))
        for sid in set(data.service_ids):c.execute('INSERT INTO employee_service(employee_id,service_id) VALUES(%s,%s) ON CONFLICT(employee_id,service_id) DO UPDATE SET is_active=true',(id,sid))
    return {'ok':True}

@router.put('/services/{id}/recipe')
def recipe(id:int,data:m.RecipeInput,user=Depends(get_user)):
    require(user,'manager')
    with transaction() as c:
        schedule_lock(c)
        found(one(c,'SELECT 1 FROM service WHERE service_id=%s FOR UPDATE',(id,)))
        check(len({x.consumable_id for x in data.consumptions})==len(data.consumptions),'Combine quantities for the same consumable.')
        for row in data.consumptions:
            supply=found(one(c,'SELECT is_active FROM consumable WHERE consumable_id=%s',(row.consumable_id,)))
            check(supply['is_active'],'Default quantities include an inactive consumable. Replace or remove it.')
        c.execute('DELETE FROM service_consumable WHERE service_id=%s',(id,))
        for row in data.consumptions:c.execute('INSERT INTO service_consumable VALUES(%s,%s,%s)',(id,row.consumable_id,row.quantity))
    return {'ok':True}

@router.get('/shifts')
def shifts(start:date,end:date,user=Depends(get_user)):
    require(user,'manager','receptionist','groomer')
    if start>end or (end-start).days>366:
        raise HTTPException(422,'Choose a shift range of no more than one year, with start on or before end.')
    with transaction() as c:
        return all_rows(c,'''SELECT sh.*,e.display_name FROM employee_shift sh JOIN employee e USING(employee_id)
         WHERE starts_at<(%s::date+1) AT TIME ZONE 'Australia/Sydney' AND ends_at> %s::date AT TIME ZONE 'Australia/Sydney'
         AND (%s OR sh.employee_id=%s) ORDER BY starts_at,e.display_name''',(end,start,user['role']!='groomer',user['employee_id']))

@router.post('/shifts')
def add_shift(data:m.ShiftInput,user=Depends(get_user)):
    require(user,'manager')
    start,end=aware(data.starts_at),aware(data.ends_at)
    check(end>start and (end-start).total_seconds()<=16*3600,'A shift must be longer than zero and no longer than 16 hours.')
    with transaction() as c:
        schedule_lock(c)
        return one(c,'INSERT INTO employee_shift(employee_id,starts_at,ends_at) VALUES(%s,%s,%s) RETURNING *',(data.employee_id,start,end))

@router.delete('/shifts/{id}')
def delete_shift(id:int,user=Depends(get_user)):
    require(user,'manager')
    with transaction() as c:
        schedule_lock(c);row=found(one(c,'SELECT * FROM employee_shift WHERE shift_id=%s',(id,)))
        check(not one(c,"SELECT 1 FROM appointment_item WHERE employee_id=%s AND state IN ('scheduled','in_progress') AND planned_start_at>=%s AND planned_end_at<=%s",(row['employee_id'],row['starts_at'],row['ends_at'])),'This shift has assigned tasks. Reschedule them first.')
        c.execute('DELETE FROM employee_shift WHERE shift_id=%s',(id,))
    return {'ok':True}
