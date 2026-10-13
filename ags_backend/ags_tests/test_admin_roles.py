"""Persistent roles, real authentication, scope and last-admin protection."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, create_engine
from ags_app import core, main, relational
from test_dataset_models import system, dataset
from test_user_management import accounts, login, body, OLD, NEW
from types import SimpleNamespace


def change(client, user='colleague', role='administrator', password=OLD):
    return client.patch('/api/users/'+user+'/role',json={'role':role,'current_password':password})


def test_promotion_grants_admin_scope_and_demoting_bootstrap_is_persistent(accounts):
    client=accounts;login(client)
    d=dataset(SimpleNamespace(api=client),name='Original administrator dataset')
    assert change(client).status_code==200
    info=login(client,'Colleague')['user']
    assert info['is_admin'] and info['role']=='administrator'
    assert client.get('/api/users').status_code==200
    assert client.get('/api/datasets/'+d['id']).status_code==200
    assert client.get('/api/models').json()
    assert client.get('/api/settings/profiles').json()
    mappings=client.get('/api/datasets/'+d['id']+'/models').json()
    mapping_body={key:mappings[key] for key in ('mappings','default_chat_model_id','default_extraction_model_id','embedding_model_id')}
    assert client.put('/api/datasets/'+d['id']+'/models',json=mapping_body).status_code==200
    model=next(item for item in client.get('/api/models').json() if 'chat' in item['capabilities'])
    registration={key:model[key] for key in ('connection_profile_id','provider_model','capabilities')}|{'name':'Second admin model'}
    assert client.post('/api/models',json=registration).status_code==409  # Equivalent registrations are intentionally rejected.
    registration['provider_model']='gpt-4.1'
    assert client.post('/api/models',json=registration).status_code==200
    assert client.patch('/api/datasets/'+d['id']+'/status',json={'active':False}).status_code==200
    assert client.patch('/api/datasets/'+d['id']+'/status',json={'active':True}).status_code==200
    assert client.post('/api/users',json=body(username='CreatedBySecondAdmin')).status_code==200
    assert client.put('/api/users/colleague/datasets',json={'dataset_ids':[]}).status_code==400
    assert client.get('/api/users/colleague/datasets').json()['all_datasets'] is True
    assert change(client,'administrator','user').status_code==200
    core.init()
    with core.Session() as session:
        assert session.get(core.User,'administrator').role=='user'
        assert session.get(core.User,'colleague').role=='administrator'
    login(client)
    assert client.get('/api/users').status_code==403
    assert client.get('/api/auth/me').json()['user']['is_admin'] is False
    assert client.get('/api/datasets').json()==[]
    assert change(client,'administrator').status_code==403


def test_role_change_revokes_all_target_sessions_preserves_assignments_and_audits(accounts):
    client=accounts;login(client)
    d=dataset(SimpleNamespace(api=client));other=dataset(SimpleNamespace(api=client),name='Other')
    assert client.put('/api/users/colleague/datasets',json={'dataset_ids':[d['id']]}).status_code==200
    with TestClient(main.app) as device1, TestClient(main.app) as device2:
        login(device1,'Colleague');login(device2,'Colleague')
        result=change(client);assert result.status_code==200
        assert result.json()['sessions_revoked'] is True
        assert device1.get('/api/auth/me').status_code==device2.get('/api/auth/me').status_code==401
        login(device1,'Colleague');assert device1.get('/api/datasets/'+other['id']).status_code==200
        assert change(client,role='user').status_code==200
        assert device1.get('/api/auth/me').status_code==401
        login(device1,'Colleague')
        assert [x['id'] for x in device1.get('/api/datasets').json()]==[d['id']]
        assert device1.get('/api/datasets/'+other['id']).status_code==404
        assert device1.get('/api/models').json()
        assert device1.post('/api/datasets',json={'name':'Not allowed'}).status_code==403
        assert device1.get('/api/users').status_code==403
    with core.Session() as session:
        user=session.get(core.User,'colleague')
        assert user.updated_by=='administrator' and user.updated_via=='user_management'
        assert core.password_valid(OLD,user.password_hash)


def test_last_admin_rejected_and_self_demotion_signs_out_when_another_exists(accounts):
    client=accounts;login(client)
    denied=change(client,'administrator','user')
    assert denied.status_code==409 and 'at least one administrator' in denied.text
    assert client.get('/api/auth/me').status_code==200
    assert change(client).status_code==200
    result=change(client,'administrator','user');assert result.status_code==200
    assert client.get('/api/auth/me').status_code==401
    login(client,'Colleague')
    assert change(client,'colleague','user').status_code==409


def test_role_permissions_password_csrf_and_noop(accounts):
    client=accounts
    assert change(client).status_code==401
    login(client,'Colleague');assert change(client).status_code==403
    login(client)
    client.headers.pop('X-CSRF-Token');assert change(client).status_code==403
    login(client)
    assert change(client,password='incorrect').status_code==400
    assert change(client,'missing').status_code==404
    noop=change(client,'administrator');assert noop.status_code==200
    assert noop.json()['sessions_revoked'] is False
    assert client.get('/api/auth/me').status_code==200
    assert change(client).status_code==200
    login(client,'Colleague')
    assert client.post('/api/users/administrator/password',json=body(current_password=OLD)).status_code==200
    assert login(client,'Admin',NEW)['user']['is_admin']


@pytest.mark.parametrize('value',[{'role':'owner'},{'role':True},{'role':None},{'is_admin':True},{'current_password':''}])
def test_invalid_roles_do_not_echo_password_or_change_account(accounts,value):
    login(accounts)
    result=accounts.patch('/api/users/colleague/role',json={'role':'administrator','current_password':OLD}|value)
    assert result.status_code==422 and OLD not in result.text
    with core.Session() as session:assert session.get(core.User,'colleague').role=='user'


def test_concurrent_self_demotions_leave_one_administrator(accounts):
    login(accounts);assert change(accounts).status_code==200
    def demote(name,id):
        with TestClient(main.app) as client:
            login(client,name)
            return change(client,id,'user').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(demote,'Admin','administrator'),pool.submit(demote,'Colleague','colleague')]
        assert sorted(f.result() for f in futures)==[200,409]
    with core.Session() as session:assert len(list(session.scalars(select(core.User).where(core.User.role=='administrator'))))==1


def test_legacy_role_migration_promotes_original_once_and_keeps_other_users(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'legacy-role.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id VARCHAR(80) PRIMARY KEY, username VARCHAR(120) UNIQUE NOT NULL, password_hash TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO users VALUES ('administrator','Original','unchanged'), ('second','Other','unchanged')"))
    core.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        relational.upgrade_legacy(conn)
        assert dict(conn.execute(text('SELECT id, role FROM users')).all())=={'administrator':'administrator','second':'user'}
        conn.execute(text("UPDATE users SET role='administrator' WHERE id='second'"))
        conn.execute(text("UPDATE users SET role='user' WHERE id='administrator'"))
        relational.upgrade_legacy(conn)
        assert dict(conn.execute(text('SELECT id, role FROM users')).all())=={'administrator':'user','second':'administrator'}
        assert conn.scalar(text("SELECT password_hash FROM users WHERE id='administrator'"))=='unchanged'
    engine.dispose()
