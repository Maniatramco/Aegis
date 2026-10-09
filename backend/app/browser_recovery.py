"""Direct desktop password reset and legacy private-link redemption.

Local-only mode deliberately trusts people using the installation's computer.
There is no unauthenticated reset for network or PostgreSQL deployments.
"""
import hashlib
import hmac
import ipaddress
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, delete, inspect, text
from . import core, password_recovery

router = APIRouter()
COOKIE = 'aegis_recovery_csrf'
PREFIX = '/api/auth/recovery'
_lock = threading.Lock()
_attempts = []
_csrf_key = secrets.token_bytes(32)
CSRF_LIFETIME = 300


def loopback_host(host):
    return host in ('127.0.0.1', 'localhost', '::1')


def guard(request):
    if os.getenv('AEGIS_LOCAL_ONLY') != 'true' or core.engine.url.get_backend_name() != 'sqlite':
        raise HTTPException(404, 'Not found')
    try:
        local = request.client and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    host = request.headers.get('host', '').lower()
    origin = request.headers.get('origin', '')
    allowed = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    try:
        api = urlsplit(os.getenv('API_INTERNAL_URL', 'http://127.0.0.1:8000'))
        target = urlsplit('http://' + host)
        source = urlsplit(origin)
        endpoint_matches = (loopback_host(api.hostname) and loopback_host(target.hostname)
                            and target.port == (api.port or 80)
                            and source.hostname == target.hostname
                            and source.scheme in ('http', 'https') and origin in allowed)
    except ValueError:
        endpoint_matches = False
    forwarded = any(k in request.headers for k in ('forwarded','x-forwarded-for','x-forwarded-host','x-forwarded-proto'))
    if (not local or not endpoint_matches or forwarded
            or request.headers.get('sec-fetch-site','same-site') not in ('same-site','same-origin')):
        raise HTTPException(403, 'Open password recovery on the computer running Aegis.')
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
    if not isinstance(body, dict):
        raise HTTPException(400, 'Invalid recovery form')
    if 'token' in body and (not isinstance(body['token'],str) or not 40 <= len(body['token']) <= 100):
        raise HTTPException(403, 'This recovery link is invalid or expired. Open a new private link.')
    return body


def csrf_for(token):
    return hashlib.sha256(('aegis-recovery-csrf:'+token).encode()).hexdigest()


def local_csrf():
    payload = f'{int(time.time())}.{secrets.token_urlsafe(32)}'
    signature = hmac.new(_csrf_key, payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_local_csrf(value):
    try:
        issued, nonce, signature = value.split('.')
        age = time.time() - int(issued)
        expected = hmac.new(_csrf_key, f'{issued}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        return 0 <= age <= CSRF_LIFETIME and len(nonce) == 43 and secrets.compare_digest(expected, signature)
    except (ValueError, AttributeError):
        return False


@router.post(PREFIX+'/prepare')
async def prepare(request: Request, response: Response):
    body = await read_form(request)
    with _lock:
        now=time.time();_attempts[:]=[t for t in _attempts if t>now-60]
        if len(_attempts)>=30:raise HTTPException(429,'Too many requests; try again in one minute.')
        _attempts.append(now)
    if 'token' in body:
        try:
            username=password_recovery.grant_username(Path(core.engine.url.database),body['token'])
        except Exception:
            raise HTTPException(403, 'This recovery link is invalid or expired. Open a new private link.')
        csrf=csrf_for(body['token'])
        mode = 'private'
    else:
        with core.Session() as session:
            administrator = session.scalar(select(core.User).where(core.User.id == 'administrator'))
            if not administrator:
                raise HTTPException(409, 'No account is configured. Return to first-run setup.')
            username = administrator.username
        csrf = local_csrf()
        mode = 'local'
    response.set_cookie(COOKIE,csrf,httponly=True,samesite='strict',secure=False,max_age=300,path=PREFIX)
    response.headers['Cache-Control']='no-store'
    return {'username':username,'csrf_token':csrf,'mode':mode}


def apply_reset(body):
    # Login holds the same lock, so a login cannot retain a session for the old hash.
    password_recovery.validate_password(body['password'], body['confirmation'])
    with core.document_lock('administrator-auth'):
        if 'token' in body:
            password_recovery.recover(
                Path(core.engine.url.database), None, body['password'],
                body['confirmation'], grant_token=body['token'])
            return
        # Direct reset uses the normal account transaction; no offline script,
        # service shutdown, account recreation or database restore is involved.
        with core.Session.begin() as session:
            account = session.scalar(select(core.User).where(
                core.User.id == 'administrator', core.User.username == body['username']))
            if not account:
                raise password_recovery.RecoveryError('Existing administrator not found; nothing changed.')
            account.password_hash = core.password_hash(body['password'])
            session.execute(delete(core.Login).where(core.Login.owner == account.id))
            if inspect(session.connection()).has_table('recovery_grants'):
                session.execute(text('DELETE FROM recovery_grants WHERE owner=:owner'), {'owner': account.id})


@router.post(PREFIX+'/reset')
async def reset(request: Request, response: Response):
    body=await read_form(request)
    csrf = request.headers.get('x-csrf-token', '')
    cookie = request.cookies.get(COOKIE, '')
    valid = secrets.compare_digest(csrf, cookie) and bool(csrf)
    valid = valid and (secrets.compare_digest(csrf, csrf_for(body['token']))
                      if 'token' in body else valid_local_csrf(csrf))
    if not valid:
        raise HTTPException(403,'Recovery form expired or could not be verified. Reload the page and try again.')
    if any(not isinstance(body.get(k),str) for k in ('password','confirmation')):
        raise HTTPException(400,'Enter and confirm your new password.')
    if 'token' not in body and (not isinstance(body.get('username'), str)
                              or not 1 <= len(body['username']) <= 120):
        raise HTTPException(400, 'Enter your existing username.')
    try:
        await run_in_threadpool(apply_reset, body)
    except password_recovery.RecoveryError as error:
        raise HTTPException(400,str(error))
    except Exception:
        raise HTTPException(503,'Password could not be changed. Nothing was committed; try again.')
    response.delete_cookie(COOKIE,path=PREFIX)
    response.delete_cookie('aegis_session',path='/')
    response.headers['Cache-Control']='no-store'
    return {'ok':True}
