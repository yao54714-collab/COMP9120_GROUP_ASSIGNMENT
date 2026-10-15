import logging
import html
import json
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from fastapi import FastAPI,Depends,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .auth import router as auth_router,get_user
from .catalog import router as catalog_router
from .bookings import router as bookings_router
from .accounts import router as accounts_router
from .common import require,check,now
from .config import ROOT
from .db import transaction,one,all_rows

app=FastAPI(title='PawCare',version='1.0.0',docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def same_origin(request:Request,call_next):
    if request.method in ['POST','PUT','PATCH','DELETE']:
        origin=request.headers.get('origin')
        if request.headers.get('x-pawcare-client')!='web' or (origin and urlparse(origin).netloc!=request.headers.get('host')):
            return JSONResponse({'detail':'Invalid request origin. Please use the PawCare website.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith('/api/') or response.headers.get('content-type','').startswith('text/html'):
        # The HTML chooses hashed assets; stale HTML can load an older language/build.
        response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    error=exc.errors()[0]
    return JSONResponse({'detail':f"Please check {'.'.join(str(v) for v in error['loc'][1:])}: {error['msg']}"},status_code=422)

@app.exception_handler(psycopg.Error)
async def database_error(request,exc):
    if isinstance(exc,psycopg.errors.ExclusionViolation):message='Schedule conflict: an employee, station, pet or shift overlaps. Adjust the time and retry.'
    elif isinstance(exc,psycopg.errors.UniqueViolation):message='This email, code, relationship or transaction already exists.'
    elif isinstance(exc,psycopg.errors.ForeignKeyViolation):message='A related record is missing or still referenced. Refresh and check the details.'
    elif isinstance(exc,psycopg.errors.CheckViolation):
        raw=str(exc)
        translations={'Insufficient inventory':'Insufficient stock. Care completion was rolled back; no stock was deducted.','Payment exceeds':'Payment exceeds the outstanding balance.','Refund exceeds':'Refund exceeds the refundable balance or the remaining original payment.','outside employee shift':'The service falls outside the employee shift.','species does not match':'The service does not match the pet species.','Pet does not belong':'The pet does not belong to this booking customer.','qualification':'The employee does not have an active qualification for this service.','Workstation type':'The workstation type does not match or the station is inactive.','Inactive pet':'The pet or service is inactive.','state transition':'This service status transition is not allowed.','Final service':'Finished services cannot be edited.','immutable':'Historical transactions cannot be edited or deleted.'}
        message=next((v for k,v in translations.items() if k in raw),'The data violates a business rule. Check the details; no changes were saved.')
    elif isinstance(exc,(psycopg.errors.LockNotAvailable,psycopg.errors.DeadlockDetected,psycopg.errors.SerializationFailure)):
        message='Another employee is updating these records. Please try again shortly.'
    else:
        logging.exception('Database operation failed')
        return JSONResponse({'detail':'Database unavailable. Check the local database service.'},status_code=503)
    return JSONResponse({'detail':message},status_code=409)

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(bookings_router)
app.include_router(accounts_router)

@app.get('/api/health')
def health():
    with transaction() as c:
        value=one(c,'SELECT current_database() AS database,version FROM schema_version ORDER BY version DESC LIMIT 1')
    return {'status':'ok',**value}

@app.get('/api/reports')
def reports(start:date|None=None,end:date|None=None,user=Depends(get_user)):
    require(user,'manager')
    end=end or now().date();start=start or end-timedelta(days=6)
    check(start<=end and (end-start).days<=366,'Choose a valid date range of no more than one year.')
    with transaction() as c:
        cash=all_rows(c,'''WITH days AS (SELECT generate_series(%s::date,%s::date,'1 day')::date AS day),
          receipts AS (SELECT (received_at AT TIME ZONE 'Australia/Sydney')::date AS day,SUM(amount) AS amount FROM payment GROUP BY 1),
          refunds AS (SELECT (refunded_at AT TIME ZONE 'Australia/Sydney')::date AS day,SUM(amount) AS amount FROM refund GROUP BY 1)
          SELECT d.day,COALESCE(p.amount,0) AS received,COALESCE(r.amount,0) AS refunded,
          COALESCE(p.amount,0)-COALESCE(r.amount,0) AS net FROM days d LEFT JOIN receipts p USING(day) LEFT JOIN refunds r USING(day) ORDER BY d.day''',(start,end))
        services=all_rows(c,'''SELECT s.service_id,s.service_name,COUNT(*) AS count,SUM(i.agreed_price) AS value
          FROM service_record r JOIN appointment_item i USING(appointment_item_id) JOIN service s USING(service_id)
          WHERE i.state='completed' AND (r.actual_end_at AT TIME ZONE 'Australia/Sydney')::date BETWEEN %s AND %s
          GROUP BY s.service_id ORDER BY count DESC''',(start,end))
        totals=one(c,'''SELECT COUNT(DISTINCT pet_id) AS pets,
          COUNT(*) AS service_items FROM appointment_item i JOIN service_record r USING(appointment_item_id)
          WHERE i.state='completed' AND (r.actual_end_at AT TIME ZONE 'Australia/Sydney')::date BETWEEN %s AND %s''',(start,end))
        totals.update(one(c,'''SELECT COUNT(*) AS completed_appointments FROM (
          SELECT i.appointment_id FROM appointment_item i JOIN service_record r USING(appointment_item_id)
          JOIN appointment_overview o USING(appointment_id) WHERE o.overall_state='completed' AND i.state='completed'
          GROUP BY i.appointment_id HAVING (MAX(r.actual_end_at) AT TIME ZONE 'Australia/Sydney')::date BETWEEN %s AND %s
          ) finished''',(start,end)))
        employees=all_rows(c,'''SELECT e.employee_id,e.display_name,COUNT(r.appointment_item_id) AS count,
          COALESCE(ROUND(SUM(EXTRACT(EPOCH FROM(r.actual_end_at-r.actual_start_at)))/3600,2),0) AS hours
          FROM employee e LEFT JOIN appointment_item i USING(employee_id)
          LEFT JOIN service_record r ON r.appointment_item_id=i.appointment_item_id AND i.state='completed'
          AND (r.actual_end_at AT TIME ZONE 'Australia/Sydney')::date BETWEEN %s AND %s
          WHERE e.staff_role='groomer' GROUP BY e.employee_id ORDER BY e.employee_id''',(start,end))
        low=all_rows(c,'SELECT b.* FROM inventory_balance b JOIN consumable c USING(consumable_id) WHERE c.is_active AND quantity_on_hand<=b.reorder_level ORDER BY quantity_on_hand-b.reorder_level')
        return {'start':start,'end':end,'cash':cash,'services':services,'employees':employees,'low_stock':low,
                'totals':{**totals,'received':sum(x['received'] for x in cash),'refunded':sum(x['refunded'] for x in cash),'net':sum(x['net'] for x in cash)}}

@app.get('/api/care-history/{pet_id}')
def history(pet_id:int,user=Depends(get_user)):
    with transaction() as c:
        pet=one(c,'SELECT * FROM pet WHERE pet_id=%s',(pet_id,))
        if not pet:raise HTTPException(404,'Pet not found.')
        if user['role']=='customer' and pet['customer_id']!=user['customer_id']:raise HTTPException(404,'Pet not found.')
        if user['role']=='groomer' and not one(c,'SELECT 1 FROM appointment_item WHERE pet_id=%s AND employee_id=%s',(pet_id,user['employee_id'])):raise HTTPException(404,'Pet not found.')
        return all_rows(c,'''SELECT r.*,s.service_name,e.display_name AS employee_name FROM service_record r
         JOIN appointment_item i USING(appointment_item_id) JOIN service s USING(service_id) JOIN employee e USING(employee_id)
         WHERE i.pet_id=%s AND i.state='completed' ORDER BY r.actual_end_at DESC''',(pet_id,))

DIST=ROOT/'frontend/dist'
if (DIST/'assets').exists():app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')

@app.get('/api/docs',response_class=HTMLResponse,include_in_schema=False)
def api_reference():
    # A local reference works offline and respects the app's same-origin CSP.
    schema=app.openapi()
    rows=[]
    for path,operations in schema['paths'].items():
        for method,operation in operations.items():
            escaped=html.escape(json.dumps(operation,ensure_ascii=False,indent=2))
            rows.append(f'<details><summary><b>{html.escape(method.upper())}</b> {html.escape(path)}</summary><pre>{escaped}</pre></details>')
    models=html.escape(json.dumps(schema.get('components',{}),ensure_ascii=False,indent=2))
    return '''<!doctype html><html lang="en-AU"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>PawCare API Reference</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;color:#263b32;background:#faf9f5}a{color:#416650}details{background:white;border:1px solid #deded7;border-radius:10px;padding:14px;margin:10px 0}summary{cursor:pointer}b{display:inline-block;min-width:80px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}</style>
    <h1>PawCare API Reference</h1><p>Offline API reference. Sign in through the website to obtain a session. Writes require the same origin and the <code>X-PawCare-Client: web</code>  header. Role permissions are enforced.</p>
    <p><a href="/">Back to the website</a> · <a href="/openapi.json">OpenAPI JSON</a></p>'''+''.join(rows)+f'<details><summary>Data models</summary><pre>{models}</pre></details></html>'

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith('api/'):raise HTTPException(404,'API endpoint not found.')
    if not (DIST/'index.html').exists():raise HTTPException(503,'Frontend not built. Run python run.py first.')
    return FileResponse(DIST/'index.html')
