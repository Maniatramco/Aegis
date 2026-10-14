"""Google Cloud wire contracts and Aegis routing, with no paid API calls."""
import asyncio
import json

import httpx
import pytest

from app import core, providers, worker, gcp_models
from test_dataset_models import system, dataset, upload, conversation, message, template, post, model, mapping


def config():
    return core.DEFAULTS | {'model_provider': 'gcp', 'model': 'gemini-3.5-flash-lite', 'gcp_api_mode': 'cloud', 'gcp_project_id': 'aegis-test-project', 'gcp_location': 'global'}


def reply(text='Alice [1]', finish='STOP'):
    return {'candidates': [{'content': {'parts': [{'thought': True, 'text': 'private reasoning'}, {'text': text}]}, 'finishReason': finish}]}


def test_native_chat_and_extraction_contract():
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.host == 'aiplatform.googleapis.com'
        assert request.url.path.endswith('/models/gemini-3.5-flash-lite:generateContent')
        assert request.headers['x-goog-api-key'] == 'test-secret'
        assert 'test-secret' not in str(request.url)
        payload = json.loads(request.content)
        assert payload['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'MINIMAL'}
        assert 'tools' not in payload
        is_extract = 'responseJsonSchema' in payload['generationConfig']
        assert payload['generationConfig']['maxOutputTokens'] == (2048 if is_extract else 512)
        return httpx.Response(200, json=reply('{"total":42}' if is_extract else '42 dollars [1]'))
    client = gcp_models.GCPModelAdapter(config(), 'test-secret', httpx.MockTransport(handle))
    sources = [{'document_name': 'Invoice', 'text': 'Invoice total 42.'}]
    assert client.chat('Total?', sources) == '42 dollars [1]'
    schema = {'type': 'object', 'properties': {'total': {'type': 'number'}}, 'required': ['total'], 'additionalProperties': False}
    assert client.extract('Invoice total 42.', schema) == {'total': 42}
    assert len(calls) == 2


@pytest.mark.parametrize('field,value', [('gcp_project_id', 'https://evil.example'), ('gcp_location', 'global/../evil'), ('model', 'gemini-test?key=secret'), ('gcp_output_tokens', True), ('gcp_output_tokens', 999999), ('gcp_extraction_tokens', 0)])
def test_invalid_destinations_and_unbounded_output_rejected(field, value):
    with pytest.raises(providers.ProviderError):
        gcp_models.GCPModelAdapter(config() | {field: value}, 'test-secret')


@pytest.mark.parametrize('data', [reply('partial', 'MAX_TOKENS'), {'promptFeedback': {'blockReason': 'SAFETY'}}, {'candidates': []}, reply('{"total":"wrong type"}')])
def test_incomplete_blocked_and_invalid_extractions_fail(data):
    client = gcp_models.GCPModelAdapter(config(), 'test-secret', httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    schema = {'type': 'object', 'properties': {'total': {'type': 'number'}}, 'required': ['total']}
    with pytest.raises(providers.ProviderError):
        client.extract('Total 42.', schema)


def test_errors_hide_provider_secrets_and_documents():
    client = gcp_models.GCPModelAdapter(config(), 'test-secret', httpx.MockTransport(lambda r: httpx.Response(403, json={'error': 'test-secret private document'})))
    with pytest.raises(providers.ProviderError) as error:
        client.generate('Answer', 'private document')
    assert 'test-secret' not in str(error.value) and 'private document' not in str(error.value)
    with pytest.raises(providers.ProviderError, match='256 KiB'):
        client.generate('Answer', 'x' * 262145)


def test_developer_api_uses_free_tier_endpoint_without_cloud_project():
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.url.path == '/v1beta/models/gemini-3.5-flash-lite:generateContent'
        assert request.headers['x-goog-api-key'] == 'gemini-test-key'
        return httpx.Response(200, json=reply('42 [1]'))
    client = gcp_models.GCPModelAdapter(config() | {'gcp_api_mode': 'developer', 'gcp_project_id': ''}, 'gemini-test-key', httpx.MockTransport(handle))
    assert client.chat('Total?', [{'document_name': 'Invoice', 'text': 'Total 42.'}]) == '42 [1]'
    assert len(calls) == 1


def test_unknown_api_mode_rejected():
    with pytest.raises(providers.ProviderError):
        gcp_models.GCPModelAdapter(config() | {'gcp_api_mode': 'https://evil.example'}, 'test-secret')


@pytest.mark.parametrize('finish', ['STOP', 'MAX_TOKENS', None])
def test_stream_requires_successful_completion(finish):
    data = reply('42 [1]', finish)
    client = gcp_models.GCPModelAdapter(config(), 'test-secret', httpx.MockTransport(lambda r: httpx.Response(200, text='data: ' + json.dumps(data) + '\n\n')))
    async def collect():
        return ''.join([part async for part in client.chat_stream('Total?', [{'document_name': 'Invoice', 'text': 'Total 42.'}])])
    if finish == 'STOP':
        assert asyncio.run(collect()) == '42 [1]'
    else:
        with pytest.raises(providers.ProviderError):
            asyncio.run(collect())


@pytest.mark.parametrize('api_mode', ['cloud', 'developer'])
def test_encrypted_profile_consent_chat_stream_and_pinned_worker(system, monkeypatch, api_mode):
    s = system
    d = dataset(s)
    document = upload(s, d)['documents'][0]
    body = {k: v for k, v in config().items() if k.startswith('gcp_') or k in ('model', 'model_provider')}
    body['gcp_api_mode'] = api_mode
    saved = s.api.patch('/api/settings', json=body | {'gcp_api_key': 'pinned-secret'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['gcp_api_key_configured']
    assert 'pinned-secret' not in saved.text
    assert b'pinned-secret' not in core.local_store.get('secrets/gcp-provider.enc')
    profile = post(s, '/api/settings/profiles', {'name': 'Google Cloud test'})
    g = model(s, profile['id'], 'Small Gemini', provider_model='gemini-3.5-flash-lite')
    assert g['credential_configured']
    mapping(s, d, mappings=d['mappings'] + [{'model_id': g['id'], 'enabled': True}], default_chat_model_id=g['id'], default_extraction_model_id=g['id'])
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.host == ('aiplatform.googleapis.com' if api_mode == 'cloud' else 'generativelanguage.googleapis.com')
        assert request.headers['x-goog-api-key'] == 'pinned-secret'
        payload = json.loads(request.content)
        text = json.dumps({'data': {'owner': 'Alice'}, 'evidence': []}) if 'responseJsonSchema' in payload['generationConfig'] else 'Alice [1]'
        data = reply(text)
        if request.url.path.endswith(':streamGenerateContent'):
            return httpx.Response(200, text='data: ' + json.dumps(data) + '\n\n')
        return httpx.Response(200, json=data)
    real_init = gcp_models.GCPModelAdapter.__init__
    def initialize(self, cfg=None, key=None, transport=None):
        real_init(self, cfg, key, httpx.MockTransport(handle))
    monkeypatch.setattr(gcp_models.GCPModelAdapter, '__init__', initialize)
    c = conversation(s, d, [document['id']])
    assert message(s, c, allow_external=False).status_code == 409
    assert not calls
    assert message(s, c).json()['message']['text'] == 'Alice [1]'
    streamed = s.api.post('/api/conversations/' + c['id'] + '/messages/stream', json={'text': 'Owner?', 'allow_external': True})
    assert 'event: done' in streamed.text and 'Alice [1]' in streamed.text
    ex = post(s, '/api/extractions', {'dataset_id': d['id'], 'document_ids': [document['id']], 'template_id': template(s)['id'], 'allow_external': True})
    assert s.api.put('/api/settings/profiles/' + profile['id'], json={'name': 'New profile version'}).status_code == 200
    # A queued run must keep its original encrypted credential reference.
    core.local_store.put('secrets/gcp-provider.enc', core.secret_cipher().encrypt(b'new-global-secret'))
    assert worker.run_once()
    result = s.api.get('/api/extractions/' + ex['id']).json()
    assert result['status'] == 'ready' and result['result'] == {'owner': 'Alice'}
    for endpoint in ('/api/settings/export', '/api/settings/profiles/' + profile['id'] + '/export'):
        assert 'pinned-secret' not in s.api.get(endpoint).text
    assert s.api.patch('/api/settings', json={'gcp_api_key': ''}).status_code == 200
    assert not s.api.get('/api/settings').json()['gcp_api_key_configured']
