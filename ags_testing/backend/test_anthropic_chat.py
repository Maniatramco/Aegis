"""Direct Claude contracts through real registrations/routing, with mock HTTP only."""
import json
import httpx
import pytest
from ags_app import core, agent_model, token_usage, providers
from ags_app.ags_models.validation import ConnectionError, credentials, validate_endpoint
from test_dataset_models import system, dataset, upload, conversation, message
from test_model_registration import body, register, select, routing, cloud_transport
from test_native_agent_providers import MESSAGES, TOOL


def response(content=None, stop='end_turn', **extra):
    return {'role': 'assistant', 'type': 'message', 'content': content or [{'type': 'text', 'text': 'Ready.'}],
            'stop_reason': stop, 'usage': {'input_tokens': 10, 'output_tokens': 3}, **extra}


def call(**values):
    return {'type': 'tool_use', 'id': 'toolu_test', 'name': 'connection_status', 'input': {'status': 'ready'}, **values}


def snapshot(s, model):
    return routing.profile_snapshot(routing.owned(model['connection_profile_id'], s.owner, 'config_profile'), model['connection_profile_version'])


def test_catalog_and_chat_only_registration(system, monkeypatch):
    monkeypatch.delenv('AEGIS_MODEL_ENDPOINT_HOSTS', raising=False)
    choice = next(p for p in system.api.get('/api/model-providers').json() if p['id'] == 'anthropic')
    assert choice['categories'] == ['chat'] and choice['auth_modes'] == ['api_key']
    assert validate_endpoint(choice['endpoint'], 'anthropic') == choice['endpoint']
    model = register(system, body(protocol='anthropic'))
    assert model['capabilities'] == ['chat'] and model['connection']['protocol'] == 'anthropic'
    assert model['credential_configured'] and 'synthetic-secret' not in json.dumps(model)
    for category in ('embedding', 'extraction'):
        result = system.api.post('/api/model-registrations', json=body(category, 'anthropic'))
        assert result.status_code == 400 and 'Chat' in result.text


@pytest.mark.parametrize('endpoint', ['http://api.anthropic.com/v1', 'https://api.anthropic.com',
    'https://api.anthropic.com/v1/messages', 'https://approved.example/v1',
    'https://api.anthropic.com.evil.example/v1', 'https://api.anthropic.com/v1?key=private'])
def test_native_key_cannot_be_redirected_to_another_endpoint(monkeypatch, endpoint):
    monkeypatch.setenv('AEGIS_MODEL_ENDPOINT_HOSTS', 'approved.example,api.anthropic.com.evil.example')
    with pytest.raises(ConnectionError):
        validate_endpoint(endpoint, 'anthropic')


@pytest.mark.parametrize('workspace', ['', 'wrkspc_synthetic'])
def test_tool_roundtrip_private_state_headers_and_usage(system, monkeypatch, workspace):
    value = body(protocol='anthropic', max_output_tokens=256)
    value['connection']['workspace_id'] = workspace
    snap = snapshot(system, register(system, value))
    snap['settings']['_agent_require_tool'] = True
    requests = []
    thinking = {'type': 'thinking', 'thinking': 'private reasoning', 'signature': 'opaque-signature'}
    def handle(req):
        assert str(req.url) == 'https://api.anthropic.com/v1/messages'
        assert req.headers['x-api-key'] == 'synthetic-secret'
        assert req.headers['anthropic-version'] == '2026-10-21'
        assert 'authorization' not in req.headers
        assert req.headers.get('anthropic-workspace-id', '') == workspace
        requests.append(json.loads(req.content))
        return httpx.Response(200, json=response([thinking, call()], 'tool_use') if len(requests) == 1 else response())
    cloud_transport(monkeypatch, handle)
    with core.execution_context(snap), token_usage.collect() as usage:
        first = agent_model.complete(MESSAGES, [TOOL])
        c = first['calls'][0]
        assistant = {'role': 'assistant', 'content': first['text'], '_provider_state': first['_provider_state'],
            'tool_calls': [{'id': c['id'], 'function': {'name': c['name'], 'arguments': c['arguments']}}]}
        follow = MESSAGES + [assistant, {'role': 'tool', 'tool_call_id': c['id'], 'content': '{"status":"ready"}'}]
        snap['settings']['_agent_require_tool'] = False
        pieces = []
        result = agent_model.complete(follow, [TOOL], on_token=pieces.append)
        assert result['text'] == 'Ready.' and not result['calls'] and pieces == ['Ready.']
        assert token_usage.summary(usage)['input_tokens'] == 20
        assert token_usage.summary(usage)['output_tokens'] == 6
    assert requests[0]['max_tokens'] == 256 and requests[0]['model'] == value['provider_model']
    assert requests[0]['tools'][0]['input_schema'] == TOOL['function']['parameters']
    assert requests[0]['tool_choice'] == {'type': 'auto'}
    assert not any(key in requests[0] for key in ('temperature', 'top_p', 'top_k'))
    assert requests[1]['messages'][-2]['content'][0] == thinking
    assert requests[1]['messages'][-1] == {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': c['id'], 'content': '{"status":"ready"}'}]}
    assert credentials() == {}


@pytest.mark.parametrize('bad', [False, True])
def test_registration_probe_requires_a_valid_actual_tool_and_saves_nothing(system, monkeypatch, bad):
    requests = []
    def handle(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200, json=response() if bad else response([call()], 'tool_use'))
    cloud_transport(monkeypatch, handle)
    result = system.api.post('/api/model-registrations/test', json=body(protocol='anthropic', allow_external=True))
    assert result.status_code == (400 if bad else 200), result.text
    if not bad:
        assert result.json()['agent_tool_call_validated'] is True
    assert len(requests) == 1 and requests[0]['tools'][0]['name'] == 'connection_status'
    assert system.api.get('/api/models').json() == []
    assert system.api.get('/api/settings/profiles').json() == [] and credentials() == {}


@pytest.mark.parametrize('data', [response(stop='max_tokens'), response(stop='refusal'),
    response(stop_details={'type': 'refusal'}), response([call(input='invalid')], 'tool_use'),
    response([call(input={'status': 'invented'})], 'tool_use'), response([call(name='unregistered_tool')], 'tool_use'),
    response([call(), call()], 'tool_use'), response([call()], 'end_turn'),
    response([{'type': 'thinking', 'thinking': 'private'}]), response([{'type': 'unknown_block'}])])
def test_invalid_and_incomplete_responses_fail_closed(system, monkeypatch, data):
    snap = snapshot(system, register(system, body(protocol='anthropic')))
    cloud_transport(monkeypatch, lambda req: httpx.Response(200, json=data))
    with core.execution_context(snap), pytest.raises(providers.ProviderError):
        agent_model.complete(MESSAGES, [TOOL])


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_provider_errors_do_not_echo_keys_or_response_bodies(system, monkeypatch, status):
    snap = snapshot(system, register(system, body(protocol='anthropic')))
    cloud_transport(monkeypatch, lambda req: httpx.Response(status, json={'error': 'synthetic-secret private prompt'}))
    with core.execution_context(snap), pytest.raises(providers.ProviderError) as error:
        agent_model.complete(MESSAGES, [TOOL])
    assert str(status) in str(error.value) and 'synthetic-secret' not in str(error.value) and 'private prompt' not in str(error.value)


def test_next_mapped_chat_uses_new_model_and_pinned_key_without_global_change(system, monkeypatch):
    s = system
    d = dataset(s); doc = upload(s, d)['documents'][0]; c = conversation(s, d, [doc['id']])
    value = body(protocol='anthropic', provider_model='claude-provided-model')
    model = register(s, value); select(s, d, model, 'chat')
    old_snapshot = snapshot(s, model)
    sent = []
    def handle(req):
        payload = json.loads(req.content)
        sent.append((payload['model'], req.headers['x-api-key']))
        assert 'Sources:' in payload['messages'][0]['content'][0]['text']
        return httpx.Response(200, json=response([{'type': 'text', 'text': 'Alice [1].'}]))
    cloud_transport(monkeypatch, handle)
    assert message(s, c, allow_external=False).status_code == 409
    assert not sent
    assert message(s, c).status_code == 200
    updated = s.api.put('/api/model-registrations/'+model['id'], json=value | {'provider_model': 'claude-revised-model', 'credentials': {'api_key': 'new-synthetic-key'}})
    assert updated.status_code == 200, updated.text
    assert message(s, c).status_code == 200
    with core.execution_context(old_snapshot):
        assert credentials()['api_key'] == 'synthetic-secret'
    assert sent == [('claude-provided-model', 'synthetic-secret'), ('claude-revised-model', 'new-synthetic-key')]
    assert core.settings()['model_provider'] == 'mock'


def test_workspace_and_sampling_validation_prevent_unusable_headers_and_options(system):
    value = body(protocol='anthropic')
    value['connection']['workspace_id'] = 'wrkspc_test\r\nx-api-key: private'
    assert system.api.post('/api/model-registrations', json=value).status_code == 400
    value['connection']['workspace_id'] = ''
    assert system.api.post('/api/model-registrations', json=value | {'extra_parameters': {'temperature': 0.2}}).status_code == 400


def test_anthropic_token_usage_includes_reported_cached_input_only():
    with token_usage.collect() as usage:
        token_usage.record({'usage': {'input_tokens': 10, 'cache_creation_input_tokens': 2, 'cache_read_input_tokens': 4, 'output_tokens': 3}}, 'anthropic')
        assert token_usage.summary(usage)['input_tokens'] == 16
        assert token_usage.summary(usage)['output_tokens'] == 3
        assert token_usage.summary(usage)['complete']


def test_dashboard_general_claude_reply_discloses_no_knowledge_lookup(system, monkeypatch):
    from ags_app import knowledge, reranker
    s = system; d = dataset(s)
    model = register(s, body(protocol='anthropic')); select(s, d, model, 'chat')
    def forbidden(*args, **kwargs):
        pytest.fail('Self-contained Dashboard greeting must not resolve embeddings, retrieve or rerank.')
    monkeypatch.setattr(knowledge, 'search', forbidden)
    monkeypatch.setattr(reranker, 'rank', forbidden)
    cloud_transport(monkeypatch, lambda req: httpx.Response(200, json=response([{'type': 'text', 'text': '{"route":"general","answer":"Hello. How can I help?"}'}])))
    result = s.api.post('/api/dataset-chat/messages', json={'text': 'Hello', 'dataset_ids': [d['id']], 'model_id': model['id']})
    assert result.status_code == 200, result.text
    answer = result.json()['message']
    assert answer['text'] == 'Hello. How can I help?' and answer['citations'] == []
    assert answer['source_summary']['knowledge_used'] is False


@pytest.mark.parametrize('surface', ['agent', 'dashboard'])
def test_grounded_chat_uses_native_claude_after_scoped_hybrid_and_rerank(system, monkeypatch, surface):
    from ags_app import knowledge, reranker, main
    from test_agent_workspace import plan
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    other = dataset(s, 'Other private dataset'); other_doc = upload(s, other)['documents'][0]
    model = register(s, body(protocol='anthropic', context_limit=65536))
    select(s, d, model, 'chat'); knowledge.sync(s.owner, d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE', 'langgraph')
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY', 'true')
    monkeypatch.setenv('AEGIS_RERANKER', 'local')
    ranked, requests = [], []
    def rank(query, items, limit):
        ranked.append(items)
        return items[:limit]
    monkeypatch.setattr(reranker, 'rank', rank)
    def handle(req):
        payload = json.loads(req.content); requests.append(payload)
        assert req.headers['x-api-key'] == 'synthetic-secret'
        if payload.get('tools'):
            assert payload['tools'][0]['name'] == 'route_aegis'
            return httpx.Response(200, json=response([call(name='route_aegis', input={'agent': 'chat', 'query': 'original', 'request_evidence': 'Who is the owner in the document?'})], 'tool_use'))
        if any('You are Aegis Dashboard Chat. Decide whether' in part['text'] for part in payload['system']):
            return httpx.Response(200, json=response([{'type': 'text', 'text': '{"route":"knowledge","answer":""}'}]))
        assert ranked, 'Generation must follow actual reranking.'
        current = next(part['text'] for m in payload['messages'] for part in m['content'] if part.get('type') == 'text' and 'Published vector evidence:\n' in part.get('text', ''))
        evidence = json.loads(current.split('Published vector evidence:\n', 1)[1])
        assert 'Alice' in json.dumps(evidence['records'])
        assert other_doc['id'] not in json.dumps(evidence)
        return httpx.Response(200, json=response([{'type': 'text', 'text': 'Alice is the owner. [1]'}]))
    cloud_transport(monkeypatch, handle)
    if surface == 'agent':
        result = plan(s, d, text='Who is the owner in the document?', document_ids=[doc['id']], planner_model_id=model['id'], allow_external=True)
        assert result['agent'] == 'chat', result
        record = main.get_record(result['conversation_id'], s.owner, 'conversation')
        answer = core.store.json(record.ref)['messages'][-1]
    else:
        result = s.api.post('/api/dataset-chat/messages', json={'text': 'Who is the owner in the document?', 'dataset_ids': [d['id']], 'document_ids': [doc['id']], 'model_id': model['id']})
        assert result.status_code == 200, result.text
        answer = result.json()['message']
    assert answer['answer_workflow']['status'] == 'completed', answer
    assert answer['citations'] and {c['document_id'] for c in answer['citations']} == {doc['id']}
    retrieval = answer['tool_trace'][0]['result']['retrieval']
    assert retrieval['mode'] == 'hybrid' and retrieval['reranker_enabled']
    assert requests and all(p['model'] == 'deployed-model' for p in requests)
