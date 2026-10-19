"""Offline SQL guard, complete metadata scope, revocation and opt-in contracts."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from ags_app import core, main, relational, local_select_ai as lab, user_features
from test_dataset_models import system, dataset
from test_governance import admin

URL = '/api/governance/local-sql/'


def local_config(tmp_path, monkeypatch, **changes):
    value = {'host': '127.0.0.1', 'port': 1523, 'service': 'FREEPDB1',
             'user': lab.SCHEMA, 'profile': lab.PROFILE, 'password': 'Private-local-test-password'}
    path = tmp_path / 'connection.json'
    path.write_text(json.dumps(value | changes))
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'true')
    monkeypatch.setenv('AEGIS_LOCAL_SQL_ENABLED', 'true')
    monkeypatch.setenv('AEGIS_LOCAL_SQL_CONNECTION_FILE', str(path))
    return path


def local_engine(monkeypatch, generate=None, execute=None):
    captured = {}

    @contextmanager
    def connect(config):
        yield SimpleNamespace()

    monkeypatch.setattr(lab, 'connect', connect)
    monkeypatch.setattr(lab, 'model_health', lambda: None)
    monkeypatch.setattr(lab, 'verify_profile', lambda c: None)
    monkeypatch.setattr(lab, 'stage', lambda c, rows: captured.update(rows=rows))
    monkeypatch.setattr(lab, 'generate', generate or (lambda c, question: 'SELECT COUNT(*) AS DOCUMENT_COUNT FROM LOCAL_DOCUMENTS'))
    monkeypatch.setattr(lab, 'execute', execute or (lambda c, sql: {'columns': ['DOCUMENT_COUNT'],
        'rows': [[len(captured['rows']['LOCAL_DOCUMENTS'])]], 'row_limit': 200, 'has_more': False}))
    return captured


@pytest.mark.parametrize('sql', [
    'SELECT COUNT(*) FROM LOCAL_DOCUMENTS',
    'SELECT d.DATASET_NAME, COUNT(x.DOCUMENT_ID) AS n FROM "AEGIS_LOCAL_AI"."LOCAL_DATASETS" d LEFT JOIN LOCAL_DOCUMENTS x ON d.DATASET_ID=x.DATASET_ID GROUP BY d.DATASET_ID,d.DATASET_NAME ORDER BY n DESC',
    "SELECT DATASET_NAME FROM LOCAL_DATASETS WHERE STEWARD IS NULL OR TRIM(STEWARD) = ''",
    "SELECT REVIEW_STATUS, COUNT(*) FROM LOCAL_EXTRACTIONS GROUP BY REVIEW_STATUS",
    'SELECT * FROM LOCAL_DOCUMENTS FETCH FIRST 20 ROWS ONLY',
])
def test_accepts_only_supported_metadata_selects(sql):
    assert lab.validate_sql(sql).startswith('SELECT')


@pytest.mark.parametrize('sql', [
    'DELETE FROM LOCAL_DOCUMENTS',
    'SELECT * FROM LOCAL_DOCUMENTS; DROP TABLE LOCAL_DOCUMENTS',
    'SELECT * FROM SYS.USER$',
    'SELECT * FROM USER_CREDENTIALS',
    'SELECT * FROM LOCAL_DOCUMENTS@external',
    "SELECT UTL_HTTP.REQUEST('https://example.com') FROM LOCAL_DATASETS",
    "SELECT DBMS_CLOUD_AI.GENERATE('prompt') FROM LOCAL_DATASETS",
    'SELECT * FROM LOCAL_DOCUMENTS FOR UPDATE',
    'SELECT /*+ PARALLEL(100) */ * FROM LOCAL_DOCUMENTS',
    'SELECT * FROM LOCAL_DOCUMENTS -- concealed instruction',
    "SELECT XMLTYPE('<x/>') FROM LOCAL_DATASETS",
    'SELECT * FROM LOCAL_DOCUMENTS UNION SELECT * FROM LOCAL_DOCUMENTS',
    'WITH FUNCTION f RETURN NUMBER IS BEGIN RETURN 1; END; SELECT f FROM LOCAL_DATASETS',
    "SELECT * FROM OTHER.LOCAL_DATASETS",
    'SELECT * INTO new_table FROM LOCAL_DOCUMENTS',
    'SELECT 1 FROM DUAL',
    'Here is your SQL: SELECT * FROM LOCAL_DATASETS',
])
def test_rejects_writes_systems_networks_packages_and_unparsed_text(sql):
    with pytest.raises(HTTPException) as error:
        lab.validate_sql(sql)
    assert error.value.status_code == 422


def test_disabled_and_nonlocal_configuration_never_connect(system, tmp_path, monkeypatch):
    admin(system)
    monkeypatch.delenv('AEGIS_LOCAL_SQL_ENABLED', raising=False)
    monkeypatch.setattr(lab, 'connect', lambda *_: pytest.fail('Disabled pilot connected'))
    assert system.api.get(URL + 'status').json() == {'enabled': False}
    path = local_config(tmp_path, monkeypatch)
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'false')
    assert not system.api.get(URL + 'status').json()['ready']
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'true')
    path.write_text(path.read_text().replace('127.0.0.1', 'paid-provider.example'))
    assert not system.api.get(URL + 'status').json()['ready']
    assert 'Private-local-test-password' not in system.api.get(URL + 'status').text


def test_module_and_dataset_denial_precede_any_model_call(system, tmp_path, monkeypatch):
    s = system
    local_config(tmp_path, monkeypatch)
    d = dataset(s, mapped=False)
    with s.session.begin() as db:
        db.add(core.User(id='alice', username='other-admin', role='administrator', password_hash='unused'))
    monkeypatch.setattr(lab, 'model_health', lambda: pytest.fail('Denied request touched inference'))
    body = {'dataset_ids': [d['id']], 'question': 'How many documents?'}
    assert s.api.get(URL + 'status').status_code == 403
    assert s.api.post(URL + 'query', json=body).status_code == 403
    with s.session.begin() as db:
        db.add(core.User(id='mani-id', username='mani', role='user', password_hash='unused'))
    s.owner = 'mani-id'
    assert s.api.post(URL + 'query', json=body).status_code == 404


def test_full_scoped_snapshot_excludes_source_and_result_values(system, tmp_path, monkeypatch):
    s = system
    admin(s)
    a, b = dataset(s, 'Selected', mapped=False), dataset(s, 'Private other dataset', mapped=False)
    for number in range(45):
        main.new_record('document', 'alice', f'selected-{number}.txt', parent=a['id'], data={'text': 'SECRET_SOURCE_VALUE'})
    main.new_record('document', 'alice', 'SECRET_OTHER_DOCUMENT', parent=b['id'], data={'text': 'SECRET_OTHER_TEXT'})
    main.new_record('extraction', 'alice', 'Metadata run', parent=a['id'],
                    data={'result': {'private': 'SECRET_EXTRACTED_VALUE'}, 'review_status': 'unreviewed'})
    with s.session.begin() as db:
        db.add(core.User(id='mani-id', username='mani', role='user', password_hash='unused'))
        db.add(relational.UserDataset(user_id='mani-id', dataset_id=a['id'], enabled=True))
    s.owner = 'mani-id'
    local_config(tmp_path, monkeypatch)
    captured = local_engine(monkeypatch)
    response = s.api.post(URL + 'query', json={'dataset_ids': [a['id']], 'question': 'How many documents?'})
    assert response.status_code == 200, response.text
    assert response.json()['rows'] == [[45]]
    assert response.json()['metadata_rows']['LOCAL_DOCUMENTS'] == 45
    assert len(captured['rows']['LOCAL_DATASETS']) == 1
    assert all(row[1] == a['id'] for row in captured['rows']['LOCAL_DOCUMENTS'])
    combined = json.dumps(captured) + response.text
    assert 'SECRET_' not in combined and b['id'] not in combined
    assert response.json()['cloud_inference'] is False
    assert all(step['status'] == 'completed' for step in response.json()['steps'])


@pytest.mark.parametrize('revoke', ['module', 'dataset'])
def test_revocation_during_generation_prevents_query_execution(system, tmp_path, monkeypatch, revoke):
    s = system
    admin(s)
    a = dataset(s, mapped=False)
    with s.session.begin() as db:
        db.add(core.User(id='mani-id', username='mani', role='user', password_hash='unused'))
        db.add(relational.UserDataset(user_id='mani-id', dataset_id=a['id'], enabled=True))
    s.owner = 'mani-id'
    local_config(tmp_path, monkeypatch)

    def generate(*_):
        if revoke == 'module':
            user_features.save('alice', 'mani-id', {'data_governance': False}, 0)
        else:
            with s.session.begin() as db:
                db.get(relational.UserDataset, ('mani-id', a['id'])).enabled = False
        return 'SELECT * FROM LOCAL_DOCUMENTS'

    local_engine(monkeypatch, generate=generate, execute=lambda *_: pytest.fail('Revoked request executed SQL'))
    response = s.api.post(URL + 'query', json={'dataset_ids': [a['id']], 'question': 'List documents'})
    assert response.status_code == (403 if revoke == 'module' else 404)
    assert 'LOCAL_DOCUMENTS' not in response.text


def test_invalid_generated_sql_stops_before_execution(system, tmp_path, monkeypatch):
    admin(system)
    d = dataset(system, mapped=False)
    local_config(tmp_path, monkeypatch)
    local_engine(monkeypatch, generate=lambda *_: 'DROP TABLE LOCAL_DOCUMENTS',
                 execute=lambda *_: pytest.fail('Unsafe SQL executed'))
    response = system.api.post(URL + 'query', json={'dataset_ids': [d['id']], 'question': 'Remove all documents'})
    assert response.status_code == 422


def test_profile_changes_fail_before_generation():
    rows = [('provider', 'openai'), ('provider_endpoint', 'https://paid.example'), ('model', lab.MODEL)]
    class Connection:
        def cursor(self):
            return iter_cursor

    class Cursor:
        def execute(self, *_args, **_kwargs):
            return self
        def __iter__(self):
            return iter(rows)
    iter_cursor = Cursor()
    with pytest.raises(HTTPException) as error:
        lab.verify_profile(Connection())
    assert error.value.status_code == 503
