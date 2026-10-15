from datetime import timedelta
import re
import secrets
import time
from collections import defaultdict,deque
from threading import Lock
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from .models import Login, Register
from .db import transaction,one
from .security import password_hash,verify_password,token_hash
from .common import check,now

router=APIRouter(prefix='/api/auth')
_attempts=defaultdict(deque)
_attempts_lock=Lock()

USER_QUERY='''SELECT u.account_id,u.email,COALESCE(e.display_name,c.display_name) AS display_name,
 CASE WHEN e.employee_id IS NOT NULL THEN e.staff_role ELSE 'customer' END AS role,
 e.employee_id,c.customer_id FROM user_account u
 LEFT JOIN employee e ON e.account_id=u.account_id AND e.is_active
 LEFT JOIN customer_account ca ON ca.account_id=u.account_id
 LEFT JOIN customer c ON c.customer_id=ca.customer_id AND c.is_active
 WHERE u.is_active AND (e.employee_id IS NOT NULL OR c.customer_id IS NOT NULL)'''

def get_user(request:Request):
    token=request.cookies.get('pawcare_session')
    if not token:raise HTTPException(401,'Please sign in first.')
    with transaction() as c:
        session=one(c,'SELECT account_id FROM auth_session WHERE token_hash=%s AND expires_at>CURRENT_TIMESTAMP',(token_hash(token),))
        user=one(c,USER_QUERY+' AND u.account_id=%s',(session['account_id'],)) if session else None
    if not user:raise HTTPException(401,'Your session has expired. Please sign in again.')
    return user

def email_address(email):
    email=email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Enter a valid email address.')
    return email

def create_session(c,response,account_id):
    token=secrets.token_urlsafe(32)
    c.execute('DELETE FROM auth_session WHERE expires_at<CURRENT_TIMESTAMP')
    c.execute('INSERT INTO auth_session(token_hash,account_id,expires_at) VALUES(%s,%s,%s)',(token_hash(token),account_id,now()+timedelta(hours=12)))
    response.set_cookie('pawcare_session',token,httponly=True,samesite='strict',max_age=43200,path='/')

@router.post('/login')
def login(data:Login,response:Response,request:Request):
    email=email_address(data.email)
    key=(request.client.host if request.client else 'local',email)
    with _attempts_lock:
        attempts=_attempts[key]
        while attempts and attempts[0]<time.monotonic()-300:attempts.popleft()
        if len(attempts)>=10:raise HTTPException(429,'Too many sign-in attempts. Try again in five minutes.')
        attempts.append(time.monotonic())
    with transaction() as c:
        account=one(c,'SELECT * FROM user_account WHERE email=%s AND is_active',(email,))
        if not account or not verify_password(data.password,account['password_hash']):raise HTTPException(401,'Incorrect email or password.')
        user=one(c,USER_QUERY+' AND u.account_id=%s',(account['account_id'],))
        if not user:raise HTTPException(403,'This account is inactive.')
        create_session(c,response,user['account_id'])
    with _attempts_lock:_attempts.pop(key,None)
    return user

@router.post('/register')
def register(data:Register,response:Response):
    email=email_address(data.email)
    check(len(data.password)>=8,'Password must contain at least 8 characters.')
    with transaction() as c:
        aid=one(c,'INSERT INTO user_account(email,password_hash) VALUES(%s,%s) RETURNING account_id',(email,password_hash(data.password)))['account_id']
        cid=one(c,'INSERT INTO customer(display_name,phone) VALUES(%s,%s) RETURNING customer_id',(data.display_name,data.phone))['customer_id']
        c.execute('INSERT INTO customer_account VALUES(%s,%s)',(cid,aid))
        create_session(c,response,aid)
        return one(c,USER_QUERY+' AND u.account_id=%s',(aid,))

@router.get('/me')
def me(user=Depends(get_user)):return user

@router.post('/logout')
def logout(request:Request,response:Response):
    token=request.cookies.get('pawcare_session')
    if token:
        with transaction() as c:c.execute('DELETE FROM auth_session WHERE token_hash=%s',(token_hash(token),))
    response.delete_cookie('pawcare_session',path='/')
    return {'ok':True}
