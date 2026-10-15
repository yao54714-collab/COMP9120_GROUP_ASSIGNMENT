"""Repeat-safe, synthetic demonstration data relative to the first setup date."""
from datetime import datetime, timedelta, time
from .config import SYDNEY
from .db import transaction, one
from .security import password_hash

DEMO_PASSWORD='PawCare2026!'

def seed():
    with transaction() as c:
        c.execute('SELECT pg_advisory_xact_lock(9120,99)')
        if one(c,'SELECT COUNT(*) AS n FROM user_account')['n']:
            return
        hashed=password_hash(DEMO_PASSWORD)
        accounts={}
        for key in ['manager','frontdesk','groomer','mia','customer','zhou']:
            accounts[key]=one(c,'INSERT INTO user_account(email,password_hash) VALUES(%s,%s) RETURNING account_id',(key+'@pawcare.local',hashed))['account_id']
        staff={}
        for key,code,name,role in [('manager','EMP01','Li (Manager)','manager'),('frontdesk','EMP02','Chen (Reception)','receptionist'),('groomer','EMP03','Emma','groomer'),('mia','EMP04','Mia','groomer')]:
            staff[key]=one(c,'INSERT INTO employee(account_id,employee_code,display_name,staff_role) VALUES(%s,%s,%s,%s) RETURNING employee_id',(accounts[key],code,name,role))['employee_id']
        customers=[]
        for idx,(name,phone,key) in enumerate([('Lin Xiaoyu','0400000101','customer'),('Zhou Ming','0400000102','zhou'),('Chen Xiao','0400000103',None),('Wang Chen','0400000104',None),('Li An','0400000105',None)]):
            cid=one(c,'INSERT INTO customer(display_name,phone) VALUES(%s,%s) RETURNING customer_id',(name,phone))['customer_id'];customers.append(cid)
            if key:c.execute('INSERT INTO customer_account VALUES(%s,%s)',(cid,accounts[key]))
        pets=[]
        for cid,name,species,breed,weight,notes in [(customers[0],'Mochi','dog','Bichon Frise',6.2,'Sensitive to dryer noise. Start with a low setting.'),(customers[0],'Luna','cat','Ragdoll',4.1,'May become anxious during brushing. Reassure gently.'),(customers[1],'Nori','cat','British Shorthair',5.0,''),(customers[2],'Cookie','dog','Corgi',11.8,'Brush the belly gently.'),(customers[3],'Doubao','dog','Poodle',5.3,''),(customers[4],'Max','dog','Shiba Inu',9.6,'')]:
            pid=one(c,'INSERT INTO pet(customer_id,pet_name,species,breed,birth_date,sex,latest_weight_kg,care_notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING pet_id',(cid,name,species,breed,'2023-03-16','female',weight,notes))['pet_id'];pets.append(pid)
        services=[]
        for code,name,sp,typ,price,duration in [('DOG-BATH','Dog bath','dog','wash',55,45),('DOG-TRIM','Dog trim','dog','groom',40,30),('CAT-BATH','Gentle cat bath','cat','wash',75,60),('CAT-COMB','Cat brushing','cat','groom',35,30)]:
            sid=one(c,'INSERT INTO service(service_code,service_name,species,workstation_type,base_price,default_duration_minutes) VALUES(%s,%s,%s,%s,%s,%s) RETURNING service_id',(code,name,sp,typ,price,duration))['service_id'];services.append(sid)
            for eid in [staff['groomer'],staff['mia']]:c.execute('INSERT INTO employee_service(employee_id,service_id) VALUES(%s,%s)',(eid,sid))
        stations=[]
        for code,name,typ in [('WASH-A','Wash station A','wash'),('WASH-B','Wash station B','wash'),('GROOM-A','Grooming station A','groom')]:
            stations.append(one(c,'INSERT INTO workstation(station_code,station_name,workstation_type) VALUES(%s,%s,%s) RETURNING workstation_id',(code,name,typ))['workstation_id'])
        today=datetime.now(SYDNEY).date()
        for day in range(-14,46):
            d=today+timedelta(days=day)
            for eid in [staff['groomer'],staff['mia']]:
                c.execute('INSERT INTO employee_shift(employee_id,starts_at,ends_at) VALUES(%s,%s,%s)',(eid,datetime.combine(d,time(9),SYDNEY),datetime.combine(d,time(18),SYDNEY)))
        consumables=[]
        for sku,name,unit,threshold,qty in [('SHAMP-01','Gentle shampoo','ml',1000,800),('COND-01','Conditioner','ml',500,3000),('COT-01','Cotton pads','unit',30,200)]:
            cid=one(c,'INSERT INTO consumable(sku,consumable_name,base_unit,reorder_level) VALUES(%s,%s,%s,%s) RETURNING consumable_id',(sku,name,unit,threshold))['consumable_id'];consumables.append(cid)
            c.execute("INSERT INTO inventory_movement(consumable_id,movement_kind,quantity_delta,recorded_by_employee_id,reason,request_key) VALUES(%s,'receipt',%s,%s,'Initial demo stock',%s)",(cid,qty,staff['manager'],'seed-stock-'+sku))
        for sid in [services[0],services[2]]:
            c.execute('INSERT INTO service_consumable VALUES(%s,%s,30),(%s,%s,15)',(sid,consumables[0],sid,consumables[1]))
        c.execute('INSERT INTO service_consumable VALUES(%s,%s,2)',(services[1],consumables[2]))
        specs=[(-7,0,0,0,10,'completed'),(-6,2,2,1,11,'completed'),(-5,3,0,0,10,'completed'),(-4,4,0,1,14,'completed'),(-3,1,2,1,11,'completed'),(-2,5,0,0,15,'completed'),(-1,0,0,0,10,'completed'),(0,5,0,1,9,'completed'),(0,0,0,0,10,'scheduled'),(0,2,2,1,10,'in_progress'),(0,3,0,0,11,'scheduled'),(0,4,0,1,13,'requested'),(1,1,2,1,11,'requested'),(2,0,0,0,10,'scheduled')]
        for idx,(offset,pi,si,ei,hour,state) in enumerate(specs):
            pet=one(c,'SELECT * FROM pet WHERE pet_id=%s',(pets[pi],));svc=one(c,'SELECT * FROM service WHERE service_id=%s',(services[si],))
            start=datetime.combine(today+timedelta(days=offset),time(hour),SYDNEY);end=start+timedelta(minutes=svc['default_duration_minutes'])
            aid=one(c,'INSERT INTO appointment(booking_code,customer_id,created_by_account_id,requested_start_at,customer_note) VALUES(%s,%s,%s,%s,%s) RETURNING appointment_id',(f'PC-DEMO-{idx+1:04}',pet['customer_id'],accounts['frontdesk'],start,pet['care_notes']))['appointment_id']
            if state=='requested':
                one(c,'INSERT INTO appointment_item(appointment_id,item_no,pet_id,service_id) VALUES(%s,1,%s,%s) RETURNING appointment_item_id',(aid,pets[pi],services[si]))
                continue
            employee=[staff['groomer'],staff['mia']][ei]
            iid=one(c,'INSERT INTO appointment_item(appointment_id,item_no,pet_id,service_id,employee_id,workstation_id,planned_start_at,planned_end_at,agreed_price,state) VALUES(%s,1,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING appointment_item_id',(aid,pets[pi],services[si],employee,stations[ei],start,end,svc['base_price'],state))['appointment_item_id']
            if state in ['completed','in_progress']:
                c.execute('INSERT INTO service_record(appointment_item_id,actual_start_at,actual_end_at,weight_at_visit_kg,care_notes,result_notes) VALUES(%s,%s,%s,%s,%s,%s)',(iid,start,end if state=='completed' else None,pet['latest_weight_kg'],pet['care_notes'],'Bathing and brushing completed. Gentle regular brushing is recommended.' if state=='completed' else None))
            if state=='completed':
                movement=one(c,"INSERT INTO inventory_movement(consumable_id,movement_kind,quantity_delta,recorded_by_employee_id,reason,request_key,recorded_at) VALUES(%s,'use',-30,%s,'Care completed',%s,%s) RETURNING movement_id",(consumables[0],employee,f'seed-use-{idx}',end))['movement_id']
                c.execute('INSERT INTO service_consumption VALUES(%s,%s)',(movement,iid))
                if offset<0:c.execute("INSERT INTO payment(appointment_id,receipt_code,amount,method,received_by_employee_id,request_key,received_at) VALUES(%s,%s,%s,'card',%s,%s,%s)",(aid,f'RC-DEMO-{idx+1:04}',svc['base_price'],staff['frontdesk'],f'seed-pay-{idx}',end))
