"""Browser redemption of a privately issued, short-lived local capability."""
import hashlib
import ipaddress
import os
from pathlib import Path
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request, Response
from . import core, password_recovery

router = APIRouter()
COOKIE = 'aegis_recovery_csrf'
PREFIX = '/api/auth/recovery'
_lock = threading.Lock()
_attempts = []


def guard(request):
    if os.getenv('AEGIS_LOCAL_ONLY') != 'true' or core.engine.url.get_backend_name() != 'sqlite':
        raise HTTPException(404, 'Not found')
    try:
        local = request.client and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    allowed = {'127.0.0.1:8000': 'http://127.0.0.1:3000', 'localhost:8000': 'http://localhost:3000'}
    host = request.headers.get('host', '').lower()
    forwarded = any(k in request.headers for k in ('forwarded','x-forwarded-for','x-forwarded-host','x-forwarded-proto'))
    if (not local or host not in allowed or request.headers.get('origin') != allowed.get(host) or forwarded
            or request.headers.get('sec-fetch-site','same-site') not in ('same-site','same-origin')):
        raise HTTPException(403, 'Use the private recovery page on this computer.')
    if request.headers.get('content-type','').split(';')[0].strip() != 'application/json':
        raise HTTPException(415, 'Use JSON')


async def read_form(request):
    guard(request)
    raw = await request.body()
    if len(raw) > 4096:
        raise HTTPException(413, 'Recovery form is too large')
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, 'Invalid recovery form')
    if not isinstance(body,dict) or not isinstance(body.get('token'),str) or not 40 <= len(body['token']) <= 100:
        raise HTTPException(403, 'This recovery link is invalid or expired. Open a new private link.')
    return body


def csrf_for(token):
    return hashlib.sha256(('aegis-recovery-csrf:'+token).encode()).hexdigest()


@router.post(PREFIX+'/prepare')
async def prepare(request: Request, response: Response):
    body = await read_form(request)
    with _lock:
        now=time.time();_attempts[:]=[t for t in _attempts if t>now-60]
        if len(_attempts)>=30:raise HTTPException(429,'Too many requests; try again in one minute.')
        _attempts.append(now)
    try:
        username=password_recovery.grant_username(Path(core.engine.url.database),body['token'])
    except Exception:
        raise HTTPException(403, 'This recovery link is invalid or expired. Open a new private link.')
    csrf=csrf_for(body['token'])
    response.set_cookie(COOKIE,csrf,httponly=True,samesite='strict',secure=False,max_age=300,path=PREFIX)
    response.headers['Cache-Control']='no-store'
    return {'username':username,'csrf_token':csrf}


@router.post(PREFIX+'/reset')
async def reset(request: Request, response: Response):
    body=await read_form(request)
    expected=csrf_for(body['token'])
    if (not secrets.compare_digest(expected,request.headers.get('x-csrf-token',''))
            or not secrets.compare_digest(expected,request.cookies.get(COOKIE,''))):
        raise HTTPException(403,'Recovery form could not be verified. Open the private link again.')
    if any(not isinstance(body.get(k),str) for k in ('password','confirmation')):
        raise HTTPException(400,'Enter and confirm your new password.')
    try:
        with core.document_lock('administrator-auth'):
            password_recovery.recover(Path(core.engine.url.database),None,body['password'],body['confirmation'],grant_token=body['token'])
    except password_recovery.RecoveryError as error:
        raise HTTPException(400,str(error))
    except Exception:
        raise HTTPException(503,'Recovery could not complete. Check private backup permissions and try again.')
    response.delete_cookie(COOKIE,path=PREFIX)
    response.delete_cookie('aegis_session',path='/')
    response.headers['Cache-Control']='no-store'
    return {'ok':True}
