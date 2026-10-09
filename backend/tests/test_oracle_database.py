"""Offline Oracle contracts plus an opt-in test against Oracle Database Free."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.dialects import oracle, postgresql, sqlite
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable
from app import core, main, worker
from app.database import database_url, engine_options, StoredString
from app.provision_account import create_account


def test_oracle_connection_keeps_password_separate_from_url_parsing(tmp_path):
    secret = 'Private@password:/with?#characters'
    url = database_url(tmp_path, {'DATABASE_PROVIDER': 'oracle', 'ORACLE_HOST': 'oracle',
                                 'ORACLE_USER': 'AEGIS', 'ORACLE_PASSWORD': secret})
    assert url.drivername == 'oracle+oracledb' and url.password == secret
    assert url.query['service_name'] == 'FREEPDB1' and url.port == 1521
    assert secret not in str(url) and '***' in str(url)
    assert engine_options(url) == {'pool_pre_ping': True}


def test_oracle_can_read_password_from_a_mounted_secret(tmp_path):
    path = tmp_path / 'password'; path.write_text('Private_password_123\n')
    env = {'DATABASE_PROVIDER': 'oracle', 'ORACLE_HOST': 'oracle', 'ORACLE_USER': 'AEGIS',
           'ORACLE_PASSWORD_FILE': str(path)}
    assert database_url(tmp_path, env).password == 'Private_password_123'
    path.unlink()
    with pytest.raises(ValueError, match='Cannot read'):
        database_url(tmp_path, env)


@pytest.mark.parametrize('value', ['', 'zero', '-1', '65536'])
def test_bad_oracle_ports_fail_without_revealing_password(tmp_path, value):
    with pytest.raises(ValueError, match='ORACLE_PORT') as error:
        database_url(tmp_path, {'DATABASE_PROVIDER': 'oracle', 'ORACLE_HOST': 'oracle',
                     'ORACLE_USER': 'AEGIS', 'ORACLE_PASSWORD': 'Secret_for_test', 'ORACLE_PORT': value})
    assert 'Secret_for_test' not in str(error.value)


def test_existing_database_urls_and_sqlite_defaults_remain_supported(tmp_path):
    url = database_url(tmp_path, {'DATABASE_URL': 'postgresql+psycopg://aegis:private@db/aegis', 'DATABASE_PROVIDER': 'oracle'})
    assert url.drivername == 'postgresql+psycopg'
    local = database_url(tmp_path, {})
    assert local.database == str(tmp_path / 'control.db')
    assert engine_options(local)['connect_args'] == {'check_same_thread': False}


@pytest.mark.parametrize('value', ['', ' ', 'normal', '中文', '\x01', '\x01marker', None])
def test_oracle_empty_strings_and_literal_markers_round_trip(value):
    kind = StoredString(80); dialect = oracle.dialect()
    bound = kind.process_bind_param(value, dialect)
    if value is not None:
        assert bound != ''
    assert kind.process_result_value(bound, dialect) == value
    assert kind.process_bind_param(value, sqlite.dialect()) == value
    assert kind.process_bind_param(value, postgresql.dialect()) == value


def test_oracle_schema_uses_precise_timestamps_and_preserves_nonnullable_defaults():
    for table in core.Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=oracle.dialect()))
        assert 'CREATE TABLE' in sql
    sql = str(CreateTable(core.Job.__table__).compile(dialect=oracle.dialect()))
    assert 'BINARY_DOUBLE' in sql
    assert 'lease_token VARCHAR2(81 CHAR) NOT NULL' in sql


def test_oracle_claim_does_not_combine_fetch_first_and_for_update():
    query = worker.claim_query(100, dialect='oracle')
    sql = str(query.compile(dialect=oracle.dialect()))
    assert 'FETCH FIRST' in sql and 'FOR UPDATE' not in sql
    pg = str(worker.claim_query(100, dialect='postgresql').compile(dialect=postgresql.dialect()))
    assert 'FOR UPDATE SKIP LOCKED' in pg


def test_colleague_account_logs_in_and_duplicate_never_changes_password(system, monkeypatch):
    # The existing harness overrides auth; remove it to exercise actual sessions.
    monkeypatch.setenv('AEGIS_BOOTSTRAP_TOKEN', 'private-test-bootstrap')
    main.app.dependency_overrides.pop(main.auth)
    create_account('colleague', 'Colleague-test-password-123')
    login = system.api.post('/api/auth/login', json={'username': 'colleague', 'password': 'Colleague-test-password-123'})
    assert login.status_code == 200
    system.api.headers['X-CSRF-Token'] = login.json()['csrf_token']
    d = system.api.post('/api/datasets', json={'name': 'Colleague data'})
    assert d.status_code == 200
    with pytest.raises(ValueError, match='already exists'):
        create_account('colleague', 'Replacement-password-123')
    bad = system.api.post('/api/auth/login', json={'username': 'colleague', 'password': 'Replacement-password-123'})
    assert bad.status_code == 401
    assert system.api.post('/api/auth/login', json={'username': 'colleague', 'password': 'Colleague-test-password-123'}).status_code == 200
    create_account('another-colleague', 'Another-test-password-123')
    assert system.api.post('/api/auth/login', json={'username': 'another-colleague', 'password': 'Another-test-password-123'}).status_code == 200
    assert system.api.get('/api/datasets').json() == []


from test_dataset_models import system


def test_container_ollama_requires_explicit_host_approval(monkeypatch):
    from app.model_connections import validate_endpoint, ConnectionError
    from app.ollama_provider import base_url
    monkeypatch.delenv('AEGIS_OLLAMA_ENDPOINT_HOSTS', raising=False)
    with pytest.raises(ConnectionError):
        validate_endpoint('http://ollama:11434', 'ollama')
    monkeypatch.setenv('AEGIS_OLLAMA_ENDPOINT_HOSTS', 'ollama')
    monkeypatch.setenv('AEGIS_OLLAMA_URL', 'http://ollama:11434')
    assert base_url() == 'http://ollama:11434'
    for url in ('http://evil:11434', 'http://ollama:1234', 'http://user:password@ollama:11434', 'http://ollama:11434/path'):
        with pytest.raises(ConnectionError):
            validate_endpoint(url, 'ollama')


def test_private_setup_preserves_existing_credentials(tmp_path):
    location = Path(__file__).resolve().parents[2] / 'scripts/setup_oracle.py'
    spec = importlib.util.spec_from_file_location('oracle_setup', location)
    setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
    (tmp_path / '.env.oracle.example').write_text((location.parents[1] / '.env.oracle.example').read_text())
    assert setup.prepare(tmp_path)
    files = [tmp_path / '.env.oracle', *(tmp_path / 'secrets/oracle' / name for name in ('admin-password', 'app-password', 'test-password'))]
    original = [path.read_bytes() for path in files]
    assert not setup.prepare(tmp_path)
    assert [path.read_bytes() for path in files] == original
    assert original[1] != original[2]
    assert all(b'\r\n' not in value for value in original)
    for path in files[1:]:
        os.chmod(path, 0o600)
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    assert not setup.prepare(tmp_path)
    assert [path.read_bytes() for path in files] == original
    files[-1].unlink()
    with pytest.raises(ValueError, match='Restore'):
        setup.prepare(tmp_path)


@pytest.mark.skipif(not os.getenv('AEGIS_TEST_ORACLE_URL'), reason='Live Oracle Free database not configured')
def test_live_oracle_login_upload_extract_review_and_second_worker(tmp_path, monkeypatch):
    """Only disposable owner records are removed; no existing tables/data are dropped."""
    from fastapi.testclient import TestClient
    from app import provision_account
    from test_dataset_models import dataset, upload, template, conversation
    url = os.environ['AEGIS_TEST_ORACLE_URL']
    engine = create_engine(url, **engine_options(url))
    assert engine.dialect.name == 'oracle'
    session = sessionmaker(engine, expire_on_commit=False)
    for module in (core, main, worker):
        monkeypatch.setattr(module, 'Session', session)
    for module in (core, main):
        monkeypatch.setattr(module, 'engine', engine)
    monkeypatch.setattr(core, 'DATA', tmp_path)
    storage = core.FileStorage()
    for module in (core, main, worker):
        monkeypatch.setattr(module, 'store', storage)
    monkeypatch.setattr(core, 'local_store', storage)
    cfg = core.DEFAULTS | {'model_provider': 'mock', 'embedding_provider': 'mock', 'search_provider': 'local', 'storage_provider': 'local'}
    monkeypatch.setattr(core, 'DEFAULTS', cfg); monkeypatch.setattr(main, 'DEFAULTS', cfg)
    monkeypatch.setenv('AEGIS_ALLOW_MOCK', 'true'); monkeypatch.delenv('AEGIS_LOCAL_ONLY', raising=False)
    from cryptography.fernet import Fernet
    monkeypatch.setenv('AEGIS_MASTER_KEY', Fernet.generate_key().decode())
    name = 'oracle-test-' + uuid.uuid4().hex
    owner = None
    try:
        core.init()
        with session() as db:
            if db.scalar(select(core.Record).limit(1)) or db.scalar(select(core.Job).limit(1)):
                pytest.skip('Use an empty Oracle test schema, separate from the application schema.')
        provision_account.create_account(name, 'Disposable-test-password-123')
        with session() as db:
            owner = db.scalar(select(core.User).where(core.User.username == name)).id
        with TestClient(main.app) as client:
            login = client.post('/api/auth/login', json={'username': name, 'password': 'Disposable-test-password-123'})
            assert login.status_code == 200
            client.headers['X-CSRF-Token'] = login.json()['csrf_token']
            s = SimpleNamespace(api=client)
            d = dataset(s); doc = upload(s, d)['documents'][0]; t = template(s)
            assert worker.claim() is None  # indexing completed and cannot be claimed again
            result = client.post('/api/extractions', json={'dataset_id': d['id'], 'document_ids': [doc['id']], 'template_id': t['id']})
            assert result.status_code == 200
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(lambda _: worker.claim(), range(2)))
            winners = [value for value in claims if value is not None]
            assert len(winners) == 1
            worker.process(*winners[0])
            assert worker.claim() is None
            url = '/api/extractions/' + result.json()['id']
            assert client.get(url).json()['status'] == 'ready'
            saved = client.patch(url, json={'version': 1, 'result': {'owner': 'Reviewed Alice'}})
            assert saved.status_code == 200 and saved.json()['version'] == 2
            assert client.get(url + '/export?format=json').json()['result']['owner'] == 'Reviewed Alice'
            c = conversation(s, d, [doc['id']])
            assert client.post('/api/conversations/' + c['id'] + '/messages', json={'text': 'Who is the owner?', 'allow_external': True}).status_code == 200
            assert client.post('/api/auth/logout').status_code == 200
    finally:
        if owner:
            with session.begin() as db:
                for table in (core.Job, core.Record, core.Login):
                    db.execute(delete(table).where(table.owner == owner))
                db.execute(delete(core.User).where(core.User.id == owner))
        engine.dispose()
