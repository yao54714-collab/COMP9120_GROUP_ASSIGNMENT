from datetime import timedelta
import uuid
from fastapi import APIRouter,Depends,HTTPException
from . import models as m
from .auth import get_user
from .common import require,found,check,aware,now,appointment_access
from .db import transaction,one,all_rows,schedule_lock

router=APIRouter(prefix='/api')

ITEM_QUERY='''SELECT i.*,p.pet_name,p.species,p.breed,p.care_notes AS pet_notes,p.latest_weight_kg,
 s.service_name,s.workstation_type,s.base_price,s.default_duration_minutes,
 e.display_name AS employee_name,w.station_name,r.actual_start_at,r.actual_end_at,
 r.care_notes,r.result_notes,r.weight_at_visit_kg
 FROM appointment_item i JOIN pet p USING(pet_id) JOIN service s USING(service_id)
 LEFT JOIN employee e USING(employee_id) LEFT JOIN workstation w USING(workstation_id)
 LEFT JOIN service_record r USING(appointment_item_id)'''

def list_bookings(c,user):
    where='TRUE';params=[]
    if user['role']=='customer':where='a.customer_id=%s';params=[user['customer_id']]
    if user['role']=='groomer':where='EXISTS(SELECT 1 FROM appointment_item x WHERE x.appointment_id=a.appointment_id AND x.employee_id=%s)';params=[user['employee_id']]
    bookings=all_rows(c,f'''SELECT a.*,c.display_name AS customer_name,c.phone,o.overall_state,
      f.charge_total,f.paid_total,f.refunded_total,f.amount_due,f.refund_due,f.net_paid
      FROM appointment a JOIN customer c USING(customer_id)
      JOIN appointment_overview o USING(appointment_id) JOIN appointment_financials f USING(appointment_id)
      WHERE {where} ORDER BY a.requested_start_at DESC,a.appointment_id DESC''',params)
    if not bookings:return []
    items=all_rows(c,ITEM_QUERY+' WHERE i.appointment_id=ANY(%s) ORDER BY i.item_no',([a['appointment_id'] for a in bookings],))
    by_id={a['appointment_id']:a for a in bookings}
    for a in bookings:a['items']=[]
    for item in items:
        if user['role']!='groomer' or item['employee_id']==user['employee_id']:
            by_id[item['appointment_id']]['items'].append(item)
    return bookings

@router.get('/appointments')
def appointments(user=Depends(get_user)):
    with transaction() as c:return list_bookings(c,user)

@router.get('/appointments/{id}')
def appointment(id:int,user=Depends(get_user)):
    with transaction() as c:
        appointment_access(c,user,id)
        booking=next(a for a in list_bookings(c,user) if a['appointment_id']==id)
        if user['role']!='groomer':
            booking['payments']=all_rows(c,'''SELECT p.*,p.amount-COALESCE((SELECT SUM(r.amount) FROM refund r WHERE r.payment_id=p.payment_id),0) AS remaining_refundable
              FROM payment p WHERE appointment_id=%s ORDER BY received_at''',(id,))
            booking['refunds']=all_rows(c,'SELECT r.* FROM refund r JOIN payment p USING(payment_id) WHERE p.appointment_id=%s ORDER BY refunded_at',(id,))
        booking['consumptions']=all_rows(c,'''SELECT sc.service_record_id,m.quantity_delta,c.consumable_name,c.base_unit
           FROM service_consumption sc JOIN inventory_movement m USING(movement_id) JOIN consumable c USING(consumable_id)
           JOIN appointment_item i ON i.appointment_item_id=sc.service_record_id WHERE i.appointment_id=%s''',(id,))
        return booking

@router.post('/appointments')
def create(data:m.BookingInput,user=Depends(get_user)):
    require(user,'customer','manager','receptionist')
    start=aware(data.requested_start_at)
    check(start>now()-timedelta(minutes=5),'Choose a current or future visit time.')
    check(start<now()+timedelta(days=90),'Bookings are available up to 90 days ahead.')
    check(9<=start.hour<18,'Booking hours are 09:00–18:00 Sydney time.')
    pairs={(i.pet_id,i.service_id) for i in data.items}
    check(len(pairs)==len(data.items),'The same service cannot be added twice for the same pet.')
    customer_id=user['customer_id'] if user['role']=='customer' else data.customer_id
    check(customer_id is not None,'Select a customer.')
    with transaction() as c:
        schedule_lock(c)
        customer=found(one(c,'SELECT * FROM customer WHERE customer_id=%s',(customer_id,)))
        check(customer['is_active'],'This customer is inactive.')
        a=one(c,'INSERT INTO appointment(booking_code,customer_id,created_by_account_id,requested_start_at,customer_note) VALUES(%s,%s,%s,%s,%s) RETURNING *',('PC-'+uuid.uuid4().hex[:16].upper(),customer_id,user['account_id'],start,data.customer_note))
        for idx,item in enumerate(data.items,1):
            pet=found(one(c,'SELECT * FROM pet WHERE pet_id=%s',(item.pet_id,)))
            check(pet['customer_id']==customer_id,'Only pets belonging to this customer can be booked.')
            c.execute('INSERT INTO appointment_item(appointment_id,item_no,pet_id,service_id) VALUES(%s,%s,%s,%s)',(a['appointment_id'],idx,item.pet_id,item.service_id))
        return a

@router.post('/appointments/{id}/confirm')
def confirm(id:int,data:m.PlanInput,user=Depends(get_user)):
    require(user,'manager','receptionist')
    with transaction() as c:
        schedule_lock(c);appointment_access(c,user,id,True)
        items=all_rows(c,'SELECT * FROM appointment_item WHERE appointment_id=%s ORDER BY appointment_item_id FOR UPDATE',(id,))
        planned={i.appointment_item_id for i in data.items}
        check(len(planned)==len(data.items),'A service cannot be scheduled twice.')
        check(planned=={i['appointment_item_id'] for i in items if i['state'] in ['requested','scheduled']},'Schedule all requested or scheduled services in this booking together.')
        existing={i['appointment_item_id']:i for i in items}
        paid=one(c,'SELECT paid_total FROM appointment_financials WHERE appointment_id=%s',(id,))['paid_total']
        # Exclusions are immediate: conflicting slot swaps are rejected atomically.
        for p in data.items:
            start=aware(p.planned_start_at);end=start+timedelta(minutes=p.duration_minutes)
            check(start.date()>=now().date(),'Services cannot be scheduled on past dates.')
            check(start.date()==end.date() and start.hour>=9 and (end.hour<18 or end.hour==18 and end.minute==0),'The entire service must fit within opening hours, 09:00–18:00.')
            old=existing[p.appointment_item_id]
            if paid>0:check(old['agreed_price']==p.agreed_price,'A payment exists, so prices cannot be changed. Unstarted services may be cancelled and refunded.')
            c.execute("UPDATE appointment_item SET employee_id=%s,workstation_id=%s,planned_start_at=%s,planned_end_at=%s,agreed_price=%s,state='scheduled' WHERE appointment_item_id=%s",(p.employee_id,p.workstation_id,start,end,p.agreed_price,p.appointment_item_id))
    return {'ok':True}

@router.get('/availability')
def availability(service_id:int,pet_id:int,starts_at:str,duration:int=45,exclude_appointment:int=0,user=Depends(get_user)):
    require(user,'manager','receptionist')
    from datetime import datetime
    try:start=aware(datetime.fromisoformat(starts_at))
    except ValueError:raise HTTPException(422,'Invalid start time format.')
    check(0<duration<=480,'Service duration must be 1–480 minutes.')
    end=start+timedelta(minutes=duration)
    with transaction() as c:
        return all_rows(c,'''SELECT e.employee_id,e.display_name,w.workstation_id,w.station_name
          FROM service s JOIN employee_service es USING(service_id) JOIN employee e USING(employee_id)
          JOIN workstation w ON w.workstation_type=s.workstation_type JOIN pet p ON p.pet_id=%s AND p.species=s.species
          WHERE s.service_id=%s AND s.is_active AND p.is_active AND es.is_active AND e.is_active AND e.staff_role IN ('groomer','manager') AND w.is_active
          AND EXISTS(SELECT 1 FROM employee_shift sh WHERE sh.employee_id=e.employee_id AND sh.starts_at<=%s AND sh.ends_at>=%s)
          AND NOT EXISTS(SELECT 1 FROM appointment_item i WHERE i.appointment_id<>%s AND i.state IN ('scheduled','in_progress')
             AND (i.employee_id=e.employee_id OR i.workstation_id=w.workstation_id OR i.pet_id=p.pet_id)
             AND i.planned_start_at<%s AND i.planned_end_at>%s) ORDER BY e.employee_id,w.workstation_id''',(pet_id,service_id,start,end,exclude_appointment,end,start))

@router.post('/items/{id}/cancel')
def cancel(id:int,user=Depends(get_user)):
    require(user,'customer','manager','receptionist')
    with transaction() as c:
        schedule_lock(c)
        item=found(one(c,'SELECT * FROM appointment_item WHERE appointment_item_id=%s',(id,)))
        appointment_access(c,user,item['appointment_id'],True)
        check(item['state'] in ['requested','scheduled'],'Only services that have not started can be cancelled.')
        if user['role']=='customer' and item['planned_start_at']:check(item['planned_start_at']>now(),'The booking time has arrived. Please contact reception.')
        c.execute("UPDATE appointment_item SET state='cancelled' WHERE appointment_item_id=%s",(id,))
    return {'ok':True}

@router.post('/items/{id}/no-show')
def no_show(id:int,user=Depends(get_user)):
    require(user,'manager','receptionist')
    with transaction() as c:
        schedule_lock(c);item=found(one(c,'SELECT * FROM appointment_item WHERE appointment_item_id=%s',(id,)))
        appointment_access(c,user,item['appointment_id'],True)
        check(item['state']=='scheduled' and item['planned_start_at']<=now(),'Only scheduled services whose start time has arrived can be marked as no-show.')
        c.execute("UPDATE appointment_item SET state='no_show' WHERE appointment_item_id=%s",(id,))
    return {'ok':True}

def care_item(c,user,id):
    require(user,'manager','groomer')
    schedule_lock(c)
    item=found(one(c,'SELECT * FROM appointment_item WHERE appointment_item_id=%s',(id,)))
    appointment_access(c,user,item['appointment_id'],True)
    if user['role']=='groomer':check(item['employee_id']==user['employee_id'],'You can only handle services assigned to you.')
    return item

@router.post('/items/{id}/start')
def start_care(id:int,user=Depends(get_user)):
    with transaction() as c:
        item=care_item(c,user,id)
        check(item['state']=='scheduled','Only scheduled services can be started.')
        c.execute('INSERT INTO service_record(appointment_item_id,actual_start_at) VALUES(%s,CURRENT_TIMESTAMP)',(id,))
        c.execute("UPDATE appointment_item SET state='in_progress' WHERE appointment_item_id=%s",(id,))
    return {'ok':True}

@router.post('/items/{id}/complete')
def complete(id:int,data:m.CompleteInput,user=Depends(get_user)):
    with transaction() as c:
        item=care_item(c,user,id)
        check(item['state']=='in_progress','Only services in progress can be completed.')
        check(len({x.consumable_id for x in data.consumptions})==len(data.consumptions),'Combine quantities for the same consumable.')
        # Sort stock locks consistently; two concurrent completions cannot overspend stock.
        for use in sorted(data.consumptions,key=lambda x:x.consumable_id):
            supply=found(one(c,'SELECT * FROM consumable WHERE consumable_id=%s FOR UPDATE',(use.consumable_id,)))
            check(supply['is_active'],'Inactive consumables cannot be used.')
            movement=one(c,"INSERT INTO inventory_movement(consumable_id,movement_kind,quantity_delta,recorded_by_employee_id,reason,request_key) VALUES(%s,'use',%s,%s,%s,%s) RETURNING movement_id",(use.consumable_id,-use.quantity,user['employee_id'],f'Care completed #{id}',f'care-{id}-{use.consumable_id}'))
            c.execute('INSERT INTO service_consumption(movement_id,service_record_id) VALUES(%s,%s)',(movement['movement_id'],id))
        c.execute('UPDATE service_record SET actual_end_at=GREATEST(CURRENT_TIMESTAMP,actual_start_at),weight_at_visit_kg=%s,care_notes=%s,result_notes=%s WHERE appointment_item_id=%s',(data.weight_at_visit_kg,data.care_notes,data.result_notes,id))
        c.execute("UPDATE appointment_item SET state='completed' WHERE appointment_item_id=%s",(id,))
        if data.weight_at_visit_kg:c.execute('UPDATE pet SET latest_weight_kg=%s WHERE pet_id=%s',(data.weight_at_visit_kg,item['pet_id']))
    return {'ok':True}

@router.post('/appointments/{id}/payments')
def pay(id:int,data:m.PaymentInput,user=Depends(get_user)):
    require(user,'manager','receptionist')
    with transaction() as c:
        appointment_access(c,user,id,True)
        existing=one(c,'SELECT * FROM payment WHERE request_key=%s',(data.request_key,))
        if existing:
            check((existing['appointment_id'],existing['amount'],existing['method'])==(id,data.amount,data.method),'A request key cannot be reused for a different payment.')
            return existing
        return one(c,'INSERT INTO payment(appointment_id,receipt_code,amount,method,received_by_employee_id,request_key) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(id,'RC-'+uuid.uuid4().hex[:16].upper(),data.amount,data.method,user['employee_id'],data.request_key))

@router.post('/appointments/{id}/refunds')
def refund(id:int,data:m.RefundInput,user=Depends(get_user)):
    require(user,'manager')
    with transaction() as c:
        appointment_access(c,user,id,True)
        payment=found(one(c,'SELECT * FROM payment WHERE payment_id=%s AND appointment_id=%s',(data.payment_id,id)))
        existing=one(c,'SELECT * FROM refund WHERE request_key=%s',(data.request_key,))
        if existing:
            check((existing['payment_id'],existing['amount'],existing['reason'])==(payment['payment_id'],data.amount,data.reason),'A request key cannot be reused for a different refund.')
            return existing
        return one(c,'INSERT INTO refund(payment_id,refund_code,amount,reason,processed_by_employee_id,request_key) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(data.payment_id,'RF-'+uuid.uuid4().hex[:16].upper(),data.amount,data.reason,user['employee_id'],data.request_key))

@router.get('/inventory/movements')
def movements(user=Depends(get_user)):
    require(user,'manager')
    with transaction() as c:return all_rows(c,'''SELECT m.*,c.consumable_name,c.base_unit,e.display_name FROM inventory_movement m
      JOIN consumable c USING(consumable_id) JOIN employee e ON e.employee_id=m.recorded_by_employee_id ORDER BY movement_id DESC LIMIT 300''')

@router.post('/inventory/movements')
def move_inventory(data:m.MovementInput,user=Depends(get_user)):
    require(user,'manager')
    check(data.quantity_delta!=0,'Stock movement quantity cannot be zero.')
    check(data.movement_kind!='receipt' or data.quantity_delta>0,'Receipt quantity must be positive.')
    check(data.movement_kind!='waste' or data.quantity_delta<0,'Waste quantity must be negative.')
    with transaction() as c:
        found(one(c,'SELECT * FROM consumable WHERE consumable_id=%s FOR UPDATE',(data.consumable_id,)))
        old=one(c,'SELECT * FROM inventory_movement WHERE request_key=%s',(data.request_key,))
        if old:
            check(all(old[k]==v for k,v in data.model_dump().items()),'A request key cannot be reused for a different stock movement.')
            return old
        return one(c,'INSERT INTO inventory_movement(consumable_id,movement_kind,quantity_delta,recorded_by_employee_id,reason,request_key) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(data.consumable_id,data.movement_kind,data.quantity_delta,user['employee_id'],data.reason,data.request_key))
