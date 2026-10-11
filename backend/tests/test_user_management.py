"""Real cookie/CSRF auth, account isolation, audit and password revocation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import core, main, user_management
from test_dataset_models import system

OLD='Synthetic account password 123!'
NEW='Synthetic replacement password 456!'


@pytest.fixture
def accounts(system):
    main.app.dependency_overrides.clear()
    user_management._attempts.clear()
    with core.Session.begin() as session:
        session.add(core.User(id='administrator',username='Admin',password_hash=core.password_hash(OLD),role='administrator'))
        session.add(core.User(id='colleague',username='Colleague',password_hash=core.password_hash(OLD)))
    return system.api


def login(client,username='Admin',password=OLD):
    result=client.post('/api/auth/login',json={'username':username,'password':password})
    assert result.status_code==200
    client.headers['X-CSRF-Token']=result.json()['csrf_token']
    return result.json()


def body(**extra):
    return {'password':NEW,'confirmation':NEW,**extra}


def test_administrator_creates_account_without_exposing_hash_and_records_actor(accounts):
    client=accounts
    assert login(client)['user']['is_admin']
    result=client.post('/api/users',json=body(username='User3'))
    assert result.status_code==200
    user=result.json()
    assert user['created_by']==user['updated_by']=='administrator'
    assert user['created_at']<=user['updated_at'] and not user['is_admin']
    assert 'password_hash' not in user and NEW not in result.text
    duplicate=client.post('/api/users',json=body(username='User3'))
    assert duplicate.status_code==409
    rows=client.get('/api/users').json()
    assert len(rows)==3 and all('password_hash' not in row for row in rows)
    assert not login(client,'User3',NEW)['user']['is_admin']
    assert client.get('/api/datasets').json()==[]


def test_ordinary_user_and_anonymous_cannot_manage_accounts(accounts):
    client=accounts
    assert client.get('/api/users').status_code==401
    login(client,'Colleague')
    for result in (client.get('/api/users'),client.post('/api/users',json=body(username='No')),
                   client.post('/api/users/administrator/password',json=body(current_password=OLD))):
        assert result.status_code==403
    assert client.get('/api/auth/me').json()['user']['is_admin'] is False


def test_admin_reset_revokes_only_target_sessions_and_preserves_workspace(accounts):
    client=accounts
    login(client)
    dataset=client.post('/api/datasets',json={'name':'Preserved workspace'}).json()
    assert client.put('/api/users/colleague/datasets',json={'dataset_ids':[dataset['id']]}).status_code==200
    with TestClient(main.app) as other:
        login(other,'Colleague')
        login(client)
        bad=client.post('/api/users/colleague/password',json=body(current_password='incorrect'))
        assert bad.status_code==400 and other.get('/api/auth/me').status_code==200
        assert client.post('/api/users/colleague/password',json=body(current_password=OLD)).status_code==200
        assert other.get('/api/auth/me').status_code==401
        assert client.get('/api/auth/me').status_code==200
        assert other.post('/api/auth/login',json={'username':'Colleague','password':OLD}).status_code==401
        login(other,'Colleague',NEW)
        assert other.get('/api/datasets/'+dataset['id']).status_code==200
    with core.Session() as session:
        user=session.get(core.User,'colleague')
        assert user.updated_by=='administrator' and user.updated_via=='user_management'
        assert core.password_valid(NEW,user.password_hash)


def test_own_password_change_requires_old_password_and_revokes_all_devices(accounts):
    client=accounts
    login(client,'Colleague')
    with TestClient(main.app) as other:
        login(other,'Colleague')
        assert client.post('/api/auth/password',json=body(current_password='incorrect')).status_code==400
        assert client.post('/api/auth/password',json=body(current_password=OLD)).status_code==200
        assert client.get('/api/auth/me').status_code==other.get('/api/auth/me').status_code==401
    login(client,'Colleague',NEW)
    with core.Session() as session:
        assert session.get(core.User,'colleague').updated_by=='colleague'


@pytest.mark.parametrize('changes',[{'password':'short'}, {'confirmation':'different password 123'},
                                  {'password':123}, {'username':' user '}, {'username':'a'*121},
                                  {'is_admin':True}, {'unexpected':'private-input-value'}])
def test_invalid_create_rejects_without_echoing_password_or_writing(accounts,changes):
    login(accounts)
    result=accounts.post('/api/users',json=body(username='Rejected')|changes)
    assert result.status_code in (400,422)
    assert NEW not in result.text and 'private-input-value' not in result.text
    assert len(accounts.get('/api/users').json())==2


def test_csrf_is_required_and_admin_changes_own_password_via_self_route(accounts):
    login(accounts)
    accounts.headers.pop('X-CSRF-Token')
    assert accounts.post('/api/users',json=body(username='Rejected')).status_code==403
    login(accounts)
    assert accounts.post('/api/users/administrator/password',json=body(current_password=OLD)).status_code==400
    assert accounts.post('/api/auth/password',json=body(current_password=OLD)).status_code==200
    login(accounts,password=NEW)


def test_repeated_incorrect_current_password_is_throttled(accounts):
    login(accounts,'Colleague')
    for _ in range(10):
        assert accounts.post('/api/auth/password',json=body(current_password='incorrect')).status_code==400
    assert accounts.post('/api/auth/password',json=body(current_password=OLD)).status_code==429
    with core.Session() as session:
        assert core.password_valid(OLD,session.get(core.User,'colleague').password_hash)
