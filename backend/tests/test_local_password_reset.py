"""Direct reset is a desktop trust policy, never a network recovery endpoint."""
import sqlite3
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import core, main, browser_recovery as web
from test_browser_recovery import local, OLD, NEW, HEADERS
from test_dataset_models import system


def prepare_local(client):
    response = client.post(web.PREFIX + '/prepare', json={})
    assert response.status_code == 200, response.text
    assert response.json()['mode'] == 'local'
    assert response.json()['username'] == 'Dottie'
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return response.json()['csrf_token']


def reset_local(client, **values):
    return client.post(web.PREFIX + '/reset', json={
        'username': 'Dottie', 'password': NEW, 'confirmation': NEW, **values})


def test_no_link_or_code_required_reset_revokes_sessions_preserves_data(local):
    client, path = local
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': OLD}).status_code == 200
    previous = client.cookies.get('aegis_session')
    original = core.DATA / 'documents/local-reset/original'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'Synthetic original retained during direct recovery')
    with sqlite3.connect(path) as database:
        records = database.execute('SELECT * FROM records ORDER BY id').fetchall()
        database.execute("INSERT INTO sessions (id,owner,expires,csrf) VALUES ('other','different-owner',9999999999,'other-csrf')")
    prepare_local(client)
    assert reset_local(client).status_code == 200
    assert client.get('/api/auth/me', headers={'Cookie': 'aegis_session=' + previous}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': OLD}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': NEW}).status_code == 200
    with sqlite3.connect(path) as database:
        assert database.execute('SELECT id,username FROM users').fetchall() == [('administrator', 'Dottie')]
        assert database.execute('SELECT * FROM records ORDER BY id').fetchall() == records
        assert database.execute("SELECT owner FROM sessions WHERE id='other'").fetchone() == ('different-owner',)
    assert original.read_bytes() == b'Synthetic original retained during direct recovery'
    assert not list(path.parent.glob('password-recovery-*'))


def test_custom_ports_and_localhost_work(local, monkeypatch):
    _, _path = local
    monkeypatch.setenv('API_INTERNAL_URL', 'http://127.0.0.1:8001')
    monkeypatch.setenv('ALLOWED_ORIGINS', 'http://127.0.0.1:3001,http://localhost:3001')
    for host in ('127.0.0.1', 'localhost'):
        with TestClient(main.app, base_url=f'http://{host}:8001', client=('127.0.0.1', 41000),
                        headers={'Origin': f'http://{host}:3001', 'Sec-Fetch-Site': 'same-site'}) as client:
            prepare_local(client)
            assert reset_local(client).status_code == 200


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://attacker.invalid'}, {'Origin': ''},
    {'Origin': 'http://localhost:3000'}, {'Host': 'attacker.invalid'},
    {'Host': '127.0.0.1:8001'}, {'Sec-Fetch-Site': 'cross-site'},
    {'X-Forwarded-For': '127.0.0.1'}, {'X-Forwarded-Host': '127.0.0.1:8000'},
    {'X-Forwarded-Proto': 'http'}, {'Forwarded': 'for=127.0.0.1'},
])
def test_direct_reset_rejects_untrusted_browser_or_proxy(local, headers):
    client, path = local
    prepare_local(client)
    before = path.read_bytes()
    assert reset_local_with_headers(client, headers).status_code == 403
    assert path.read_bytes() == before


def reset_local_with_headers(client, headers):
    return client.post(web.PREFIX + '/reset', headers=headers,
                       json={'username': 'Dottie', 'password': NEW, 'confirmation': NEW})


@pytest.mark.parametrize('kind', ['missing-header', 'missing-cookie', 'tampered', 'expired', 'future'])
def test_csrf_required_signed_and_time_limited(local, monkeypatch, kind):
    client, _ = local
    value = prepare_local(client)
    if kind == 'missing-header':
        client.headers.pop('X-CSRF-Token')
    elif kind == 'missing-cookie':
        client.cookies.clear()
    elif kind == 'tampered':
        altered = value[:-1] + ('0' if value[-1] != '0' else '1')
        client.headers['X-CSRF-Token'] = altered
        client.cookies.set(web.COOKIE, altered, domain='127.0.0.1', path=web.PREFIX)
    else:
        issued = int(value.split('.')[0])
        monkeypatch.setattr(web.time, 'time', lambda: issued + (301 if kind == 'expired' else -1))
    assert reset_local(client).status_code == 403


@pytest.mark.parametrize('values', [
    {'username': ''}, {'username': 'missing'}, {'username': 42},
    {'password': 'short', 'confirmation': 'short'},
    {'password': 'x' * 201, 'confirmation': 'x' * 201},
    {'confirmation': 'mismatch'}, {'password': {'secret': NEW}},
])
def test_invalid_form_does_not_change_password(local, values):
    client, path = local
    prepare_local(client)
    response = reset_local(client, **values)
    assert response.status_code == 400
    assert NEW not in response.text
    assert not list(path.parent.glob('password-recovery-*'))
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': OLD}).status_code == 200


def test_session_revocation_failure_rolls_back_password(local):
    client, path = local
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': OLD}).status_code == 200
    with sqlite3.connect(path) as database:
        database.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    prepare_local(client)
    assert reset_local(client).status_code == 503
    assert client.post('/api/auth/login', json={'username': 'Dottie', 'password': OLD}).status_code == 200


def test_remote_mode_peer_and_postgresql_never_allow_direct_reset(local, monkeypatch):
    client, _ = local
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'false')
    assert client.post(web.PREFIX + '/prepare', json={}).status_code == 404
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'true')
    with TestClient(main.app, base_url='http://127.0.0.1:8000', client=('192.0.2.1', 1234), headers=HEADERS) as remote:
        assert remote.post(web.PREFIX + '/prepare', json={}).status_code == 403
    monkeypatch.setattr(core, 'engine', SimpleNamespace(url=SimpleNamespace(get_backend_name=lambda: 'postgresql')))
    assert client.post(web.PREFIX + '/prepare', json={}).status_code == 404


def test_unconfigured_installation_and_prepare_rate_limit(local):
    client, _ = local
    with core.Session.begin() as session:
        session.query(core.User).delete()
    assert client.post(web.PREFIX + '/prepare', json={}).status_code == 409
    web._attempts[:] = [web.time.time()] * 30
    assert client.post(web.PREFIX + '/prepare', json={}).status_code == 429
