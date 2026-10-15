"""Account removal revokes access atomically and preserves shared content."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from ags_app import core, main, relational
from test_dataset_models import system
from test_user_management import accounts, login, OLD


def remove(client, user_id='colleague', username='Colleague', password=OLD):
    return client.request('DELETE', '/api/users/' + user_id,
                          json={'username': username, 'current_password': password})


def test_delete_revokes_every_session_and_assignment_preserving_shared_data_and_archive(accounts):
    client = accounts
    login(client)
    dataset = client.post('/api/datasets', json={'name': 'Preserved dataset'}).json()
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [dataset['id']]}).status_code == 200
    private = main.new_record('conversation', 'colleague', parent=dataset['id'], data={'messages': []})
    with core.Session.begin() as session:
        # Exercise actual audit FKs, including references from another account.
        session.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
        session.connection().execute(core.User.__table__.update().where(core.User.id == 'administrator').values(updated_by='colleague'))
    with TestClient(main.app) as first, TestClient(main.app) as second:
        login(first, 'Colleague'); login(second, 'Colleague')
        result = remove(client)
        assert result.status_code == 200, result.text
        assert result.json()['sessions_revoked'] == 2
        assert result.json()['assignments_removed'] == 1
        assert result.json()['private_records_archived'] == 1
        assert first.get('/api/auth/me').status_code == second.get('/api/auth/me').status_code == 401
        assert first.post('/api/auth/login', json={'username': 'Colleague', 'password': OLD}).status_code == 401
        assert client.get('/api/auth/me').status_code == 200
        assert client.get('/api/datasets/' + dataset['id']).status_code == 200
    assert all(user['id'] != 'colleague' for user in client.get('/api/users').json())
    with core.Session() as session:
        assert session.get(core.User, 'colleague') is None
        assert session.get(core.Record, private.id) is None
        assert session.get(core.Record, dataset['id']) is not None
        assert session.scalar(select(func.count()).select_from(relational.UserDataset).where(relational.UserDataset.user_id == 'colleague')) == 0
        assert session.get(core.User, 'administrator').updated_by is None
    archives = list((core.DATA / 'account-archives/colleague').glob('*.json'))
    assert len(archives) == 1
    archive = json.loads(archives[0].read_text())
    assert archive['user']['username'] == 'Colleague' and archive['deleted_by'] == 'administrator'
    assert archive['records'][0]['id'] == private.id
    assert 'password_hash' not in archives[0].read_text() and OLD not in archives[0].read_text()
    assert core.store.json(private.ref) == {'messages': []}


@pytest.mark.parametrize('username,password,status', [('wrong', OLD, 400), ('Colleague', 'incorrect', 400)])
def test_bad_confirmation_preserves_account_access_and_creates_no_archive(accounts, username, password, status):
    login(accounts)
    assert remove(accounts, username=username, password=password).status_code == status
    with core.Session() as session:
        assert session.get(core.User, 'colleague') is not None
    assert not (core.DATA / 'account-archives').exists()


def test_only_admin_with_csrf_can_delete_and_last_admin_and_self_are_protected(accounts):
    assert remove(accounts).status_code == 401
    login(accounts, 'Colleague')
    assert remove(accounts, 'administrator', 'Admin').status_code == 403
    login(accounts)
    accounts.headers.pop('X-CSRF-Token')
    assert remove(accounts).status_code == 403
    login(accounts)
    assert remove(accounts, 'administrator', 'Admin').status_code == 409
    with core.Session.begin() as session:
        session.get(core.User, 'colleague').role = 'administrator'
    assert remove(accounts, 'administrator', 'Admin').status_code == 400
    assert remove(accounts, 'missing', 'Missing').status_code == 404
    assert accounts.get('/api/auth/me').status_code == 200


def test_owned_shared_content_blocks_deletion_without_removing_grants(accounts):
    login(accounts)
    main.new_record('knowledge_base', 'colleague', name='Owned dataset', data={})
    result = remove(accounts)
    assert result.status_code == 409 and 'ownership' in result.text
    with core.Session() as session:
        assert session.get(core.User, 'colleague') is not None
        assert session.scalar(select(relational.UserDataset).where(relational.UserDataset.user_id == 'colleague')) is not None
    assert not (core.DATA / 'account-archives').exists()


def test_archive_failure_rolls_back_account_and_access_changes(accounts, monkeypatch):
    login(accounts)
    def fail(*args, **kwargs):
        raise OSError('Protected archive unavailable')
    monkeypatch.setattr(core.local_store, 'put_json', fail)
    with pytest.raises(OSError, match='archive unavailable'):
        remove(accounts)
    with core.Session() as session:
        assert session.get(core.User, 'colleague') is not None
    assert accounts.get('/api/auth/me').status_code == 200
