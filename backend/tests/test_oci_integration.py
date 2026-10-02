"""Route -> settings -> provider factory -> worker tests with only HTTP mocked."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import core, main, providers, worker, oci_models


@pytest.fixture
def system(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'test.db'), connect_args={'check_same_thread': False})
    session = sessionmaker(engine, expire_on_commit=False)
    for module in (core, main, worker):
        monkeypatch.setattr(module, 'Session', session)
    for module in (core, main):
        monkeypatch.setattr(module, 'engine', engine)
    monkeypatch.setattr(core, 'DATA', tmp_path)
    monkeypatch.setenv('AEGIS_MASTER_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('AEGIS_ALLOW_MOCK', 'true')
    monkeypatch.setattr(core, 'DEFAULTS', core.DEFAULTS | {'model_provider': 'mock', 'embedding_provider': 'mock', 'search_provider': 'local', 'storage_provider': 'local'})
    monkeypatch.setattr(main, 'DEFAULTS', core.DEFAULTS)
    state = SimpleNamespace(calls=[], files=[], reply='Total is 42 [1].', extraction={'total': 42}, error=False, owner='alice')
    def handle(req):
        state.calls.append(req)
        assert req.url.host == 'inference.generativeai.us-chicago-1.oci.oraclecloud.com'
        assert req.headers['authorization'] == 'Bearer oci-test-secret'
        path = req.url.path
        if state.error:
            return httpx.Response(403, json={'error': {'message': 'oci-test-secret private provider text'}})
        if req.method == 'DELETE':
            return httpx.Response(200, json={'deleted': True})
        if path.endswith('/v1/files'):
            fid = 'file-' + str(len(state.files)+1)
            state.files.append(fid)
            return httpx.Response(200, json={'id': fid})
        if path.endswith('/vs-1/files'):
            return httpx.Response(200, json={'status': 'completed'})
        if path.endswith('/search'):
            return httpx.Response(200, json={'data': [{'file_id': fid, 'score': .9, 'content': [{'text': 'FORGED REMOTE EXCERPT'}]} for fid in state.files]})
        if path.endswith('/responses'):
            payload = json.loads(req.content)
            text = json.dumps({'data':state.extraction,'evidence':[]}) if 'text' in payload else state.reply
            if payload.get('stream'):
                events = [{'type': 'response.output_text.delta', 'delta': text}, {'type': 'response.completed'}]
                return httpx.Response(200, text=''.join('data: '+json.dumps(e)+'\n\n' for e in events), headers={'Content-Type': 'text/event-stream'})
            return httpx.Response(200, json={'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': text}]}]})
        if path.endswith('/vs-1'):
            return httpx.Response(200, json={'id': 'vs-1', 'status': 'completed'})
        raise AssertionError((req.method, path))
    real_init = oci_models.OCIClient.__init__
    def init(self, cfg, api_key='', **kwargs):
        real_init(self, cfg, api_key, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(oci_models.OCIClient, '__init__', init)
    main.app.dependency_overrides[main.auth] = lambda: state.owner
    with TestClient(main.app, raise_server_exceptions=False) as api:
        state.api = api
        state.session = session
        yield state
    main.app.dependency_overrides.clear()
    engine.dispose()


def configure(state):
    r = state.api.patch('/api/settings', json={'model_provider': 'oci', 'search_provider': 'oci', 'oci_region': 'us-chicago-1', 'oci_project_id': 'ocid1.generativeaiproject.oc1.us-chicago-1.test', 'oci_model': 'openai.gpt-oss-120b', 'oci_vector_store_id': 'vs-1', 'oci_api_key': 'oci-test-secret'})
    assert r.status_code == 200, r.text
    assert 'oci-test-secret' not in r.text
    assert 'oci-test-secret' not in state.api.get('/api/settings/export').text
    assert b'oci-test-secret' not in core.store.get('secrets/oci-provider.enc')


def upload(state, consent=True):
    r = state.api.post('/api/documents/upload', files={'files': ('invoice.txt', b'Invoice total is 42 dollars. Canonical source evidence.', 'text/plain')}, data={'allow_external': str(consent).lower()})
    assert r.status_code == 200, r.text
    data = r.json()
    assert worker.run_once()
    return data['documents'][0]['id'], data['jobs'][0]['id']


def test_settings_ingestion_search_chat_and_extraction(system):
    configure(system)
    did, job = upload(system)
    assert system.api.get('/api/documents/'+did).json()['status'] == 'ready'
    assert core.store.get('documents/'+did+'/original').startswith(b'Invoice total')
    index = core.store.json('documents/'+did+'/index.json')
    assert index['dimensions'] is None  # No fabricated local vector compatibility.
    assert not any('/embeddings' in str(r.url) for r in system.calls)
    conv = system.api.post('/api/conversations', json={'document_ids': [did]}).json()['id']
    r = system.api.post('/api/conversations/'+conv+'/messages', json={'text': 'What is the total?', 'allow_external': True})
    assert r.status_code == 200, r.text
    citation = r.json()['message']['citations'][0]
    assert citation['document_id'] == did and citation['page'] == 1
    assert 'Canonical source evidence' in citation['excerpt']
    assert 'FORGED' not in r.text
    stream = system.api.post('/api/conversations/'+conv+'/messages/stream', json={'text': 'Again?', 'allow_external': True})
    assert stream.status_code == 200 and 'event: done' in stream.text, stream.text
    schema = {'type': 'object', 'properties': {'total': {'type': 'number'}}, 'required': ['total'], 'additionalProperties': False}
    tid = system.api.post('/api/templates', json={'name': 'Invoice', 'schema': schema}).json()['id']
    ex = system.api.post('/api/extractions', json={'document_ids': [did], 'template_id': tid, 'allow_external': True}).json()
    assert worker.run_once()
    result = system.api.get('/api/extractions/'+ex['id']).json()
    assert result['status'] == 'ready' and result['result'] == {'total': 42}
    assert result['sources'][0]['document_id'] == did
    assert 'Canonical source evidence' in result['sources'][0]['excerpt']
    # Real ownership checks at route boundaries: stored originals and excerpts.
    system.owner = 'bob'
    for suffix in ('download', 'preview'):
        assert system.api.get('/api/documents/'+did+'/'+suffix).status_code == 404
    assert system.api.get('/api/extractions/'+ex['id']).status_code == 404


def test_oci_external_consent_enforced_before_transmission(system):
    configure(system)
    before = len(system.calls)
    r = system.api.post('/api/documents/upload', files={'files': ('x.txt', b'text', 'text/plain')})
    assert r.status_code == 409
    assert len(system.calls) == before
    did, _ = upload(system)
    conv = system.api.post('/api/conversations', json={'document_ids': [did]}).json()['id']
    before = len(system.calls)
    for path in ('/messages', '/messages/stream'):
        assert system.api.post('/api/conversations/'+conv+path, json={'text': 'Query'}).status_code == 409
    tid = system.api.post('/api/templates', json={'name': 'Empty', 'schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}}).json()['id']
    assert system.api.post('/api/extractions', json={'document_ids': [did], 'template_id': tid}).status_code == 409
    assert len(system.calls) == before


def test_provider_errors_and_schema_fail_closed(system):
    configure(system)
    did, _ = upload(system)
    conv = system.api.post('/api/conversations', json={'document_ids': [did]}).json()['id']
    system.error = True
    response = system.api.post('/api/conversations/'+conv+'/messages', json={'text': 'Query', 'allow_external': True})
    assert response.status_code == 502, response.text
    assert 'oci-test-secret' not in response.text and 'private provider' not in response.text
    system.error = False
    system.extraction = {'total': 'invalid number'}
    tid = system.api.post('/api/templates', json={'name': 'Numbers', 'schema': {'type': 'object', 'properties': {'total': {'type': 'number'}}, 'required': ['total'], 'additionalProperties': False}}).json()['id']
    ex = system.api.post('/api/extractions', json={'document_ids': [did], 'template_id': tid, 'allow_external': True}).json()
    assert worker.run_once()
    result = system.api.get('/api/extractions/'+ex['id']).json()
    assert result['status'] == 'failed' and result['result'] is None
    assert 'invalid number' not in (result.get('error') or '')


def test_oci_cancelled_job_does_not_transmit(system):
    configure(system)
    r = system.api.post('/api/documents/upload', files={'files': ('x.txt', b'Cancel this processing.', 'text/plain')}, data={'allow_external': 'true'}).json()
    before = len(system.calls)
    job = r['jobs'][0]['id']
    assert system.api.post('/api/jobs/'+job+'/cancel').status_code == 200
    assert worker.run_once() is False
    assert len(system.calls) == before
    assert system.api.get('/api/documents/'+r['documents'][0]['id']).json()['status'] == 'cancelled'
