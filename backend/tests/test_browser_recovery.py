"""Protected browser recovery on a disposable Dottie SQLite workspace."""
import hashlib
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app import core, main, browser_recovery as web, password_recovery as recovery
from test_dataset_models import system

OLD='synthetic-Dottie-old-password'
NEW='synthetic-Dottie-new-password'
HEADERS={'Origin':'http://127.0.0.1:3000','Sec-Fetch-Site':'same-site'}

@pytest.fixture
def local(system, monkeypatch):
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    main.app.dependency_overrides.clear()
    web._attempts.clear();main._login_attempts.clear()
    with system.session.begin() as s:
        s.add(core.User(id='administrator',username='Dottie',password_hash=core.password_hash(OLD)))
    with TestClient(main.app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',41000),headers=HEADERS) as client:
        yield client,core.DATA/'control.db'

def prepare(client,path):
    token=recovery.issue_grant(path,'Dottie')
    result=client.post(web.PREFIX+'/prepare',json={'token':token})
    assert result.status_code==200,result.text
    assert result.json()['username']=='Dottie'
    client.headers['X-CSRF-Token']=result.json()['csrf_token']
    return token

def redeem(client,token,**body):
    return client.post(web.PREFIX+'/reset',json={'token':token,'password':NEW,'confirmation':NEW}|body)

def test_reset_login_replay_and_data_preservation(local):
    client,path=local
    signed=client.post('/api/auth/login',json={'username':'Dottie','password':OLD})
    assert signed.status_code==200
    old_cookie=client.cookies.get('aegis_session')
    with sqlite3.connect(path) as db:
        before=db.execute('SELECT * FROM records ORDER BY id').fetchall()
    original=core.DATA/'documents'/'disposable'/'original';original.parent.mkdir(parents=True);original.write_bytes(b'Public test fixture')
    token=prepare(client,path)
    with sqlite3.connect(path) as db:
        grant=db.execute('SELECT id,owner FROM recovery_grants').fetchone()
        assert grant==(hashlib.sha256(token.encode()).hexdigest(),'administrator')
    assert redeem(client,token).status_code==200
    assert client.get('/api/auth/me',headers={'Cookie':'aegis_session='+old_cookie}).status_code==401
    assert redeem(client,token).status_code in (400,403)
    assert client.post('/api/auth/login',json={'username':'Dottie','password':OLD}).status_code==401
    assert client.post('/api/auth/login',json={'username':'Dottie','password':NEW}).status_code==200
    assert client.get('/api/auth/me').json()['user']=={'id':'administrator','username':'Dottie'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM records ORDER BY id').fetchall()==before
        assert db.execute('SELECT COUNT(*) FROM recovery_grants').fetchone()==(0,)
    assert original.read_bytes()==b'Public test fixture'
    backup=next(path.parent.glob('password-recovery-*/control-before-reset.db'))
    with sqlite3.connect(backup) as db:
        assert core.password_valid(OLD,db.execute('SELECT password_hash FROM users').fetchone()[0])

def test_expired_replaced_unknown_and_revoked_grants(local):
    client,path=local
    first=prepare(client,path);second=recovery.issue_grant(path,'Dottie')
    for token in (first,'x'*43):
        assert client.post(web.PREFIX+'/prepare',json={'token':token}).status_code==403
    with sqlite3.connect(path) as db:db.execute('UPDATE recovery_grants SET expires=0')
    assert client.post(web.PREFIX+'/prepare',json={'token':second}).status_code==403
    token=recovery.issue_grant(path,'Dottie');recovery.revoke_grant(path,token)
    assert client.post(web.PREFIX+'/prepare',json={'token':token}).status_code==403
    with pytest.raises(recovery.RecoveryError):recovery.issue_grant(path,'missing')

@pytest.mark.parametrize('headers',[{'Origin':'https://example.invalid'},{'Host':'example.invalid'},{'Sec-Fetch-Site':'cross-site'},{'X-Forwarded-For':'127.0.0.1'},{'Forwarded':'for=127.0.0.1'}])
def test_origin_host_and_proxy_rejected(local,headers):
    client,path=local;token=recovery.issue_grant(path,'Dottie')
    assert client.post(web.PREFIX+'/prepare',json={'token':token},headers=headers).status_code==403

def test_csrf_required_and_no_secret_validation_echo(local):
    client,path=local;token=prepare(client,path)
    assert redeem(client,token,confirmation='different').status_code==400
    client.headers.pop('X-CSRF-Token')
    assert redeem(client,token).status_code==403
    client.headers['X-CSRF-Token']=web.csrf_for(token);client.cookies.clear()
    assert redeem(client,token).status_code==403
    result=client.post(web.PREFIX+'/prepare',json={'token':{'secret':NEW}})
    assert result.status_code==403 and NEW not in result.text

def test_backup_failure_rolls_back_and_grant_remains(local,monkeypatch):
    client,path=local;token=prepare(client,path)
    def fail(_):raise PermissionError('synthetic failure')
    monkeypatch.setattr(recovery,'private_backup_directory',fail)
    assert redeem(client,token).status_code==503
    assert recovery.grant_username(path,token)=='Dottie'
    assert client.post('/api/auth/login',json={'username':'Dottie','password':OLD}).status_code==200

def test_disabled_and_remote_peer(local,monkeypatch):
    client,path=local;token=recovery.issue_grant(path,'Dottie')
    monkeypatch.delenv('AEGIS_LOCAL_ONLY')
    assert client.post(web.PREFIX+'/prepare',json={'token':token}).status_code==404
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    with TestClient(main.app,base_url='http://127.0.0.1:8000',client=('192.0.2.1',1234),headers=HEADERS) as remote:
        assert remote.post(web.PREFIX+'/prepare',json={'token':token}).status_code==403
