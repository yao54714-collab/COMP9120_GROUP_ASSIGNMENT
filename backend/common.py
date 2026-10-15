from datetime import datetime
from fastapi import HTTPException
from .config import SYDNEY
from .db import one

def require(user,*roles):
    if user['role'] not in roles:raise HTTPException(403,'You do not have permission for this action.')

def found(value, message='Record not found.'):
    if not value:raise HTTPException(404,message)
    return value

def check(condition,message):
    if not condition:raise HTTPException(409,message)

def aware(value):
    if value.tzinfo is None:
        value=value.replace(tzinfo=SYDNEY)
        # Round-trip rejects nonexistent wall times across DST jumps.
        from datetime import timezone
        check(value.astimezone(timezone.utc).astimezone(SYDNEY).replace(tzinfo=None)==value.replace(tzinfo=None),'This Sydney local time does not exist due to a daylight saving transition.')
    return value.astimezone(SYDNEY)

def appointment_access(c,user,aid,lock=False):
    row=found(one(c,'SELECT * FROM appointment WHERE appointment_id=%s'+(' FOR UPDATE' if lock else ''),(aid,)))
    if user['role']=='customer' and row['customer_id']!=user['customer_id']:raise HTTPException(404,'Booking not found.')
    if user['role']=='groomer' and not one(c,'SELECT 1 FROM appointment_item WHERE appointment_id=%s AND employee_id=%s',(aid,user['employee_id'])):raise HTTPException(404,'Booking not found.')
    return row

def now():return datetime.now(SYDNEY)
