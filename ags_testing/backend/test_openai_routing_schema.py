"""Exercise actual Agent routing with the object-only OpenAI function contract."""
import copy
import json
import httpx
import pytest
from ags_app import core, agent_model, providers
from ags_app.ags_models.providers.ags_openai import adapter
from ags_app.ags_models.validation import temporary_credentials, ConnectionError
from ags_app.ags_models.connection import ModelConnection
from test_ocr_cloud import snapshot
from test_dataset_models import system, dataset, upload
from test_model_registration import body, register, select, cloud_transport


@pytest.mark.parametrize('protocol,endpoint', [
    ('openai-compatible', 'https://api.openai.com/v1'),
    ('azure-openai', 'https://example.openai.azure.com/openai/v1'),
])
def test_actual_agent_router_uses_object_parameters_and_restores_route(monkeypatch, protocol, endpoint):
    pinned = snapshot()
    pinned['settings'].update(model='gpt-4o-mini', extra_parameters={})
    pinned['settings']['model_connection'].update(protocol=protocol, endpoint=endpoint)
    request = 'What total is written in invoice.txt?'
    seen = []
    def post(self, path, payload, headers=None):
        seen.append(copy.deepcopy(payload))
        assert core._execution.get()['secret_refs'] == pinned['secret_refs']
        assert payload['tool_choice'] == 'required' and len(payload['tools']) == 5
        assert all(t['function']['parameters']['type'] == 'object' and
                   'oneOf' not in t['function']['parameters'] for t in payload['tools'])
        tool = next(t['function'] for t in payload['tools'] if
                    'original' in t['function']['parameters']['properties'].get('query', {}).get('enum', []))
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': 'route-1', 'type': 'function', 'function': {'name': tool['name'],
            'arguments': json.dumps({'agent': 'chat', 'query': 'original',
                                    'document_names': ['invoice.txt'], 'request_evidence': request})}}]}}]}
    monkeypatch.setattr(ModelConnection, 'post', post)
    with core.execution_context(pinned), temporary_credentials({'api_key': 'synthetic'}):
        frame = agent_model.classify_vector([{'role': 'user', 'content': request}])
    assert frame['source'] == 'documents' and frame['document_names'] == ['invoice.txt']
    assert seen[0]['tools'][4]['function']['parameters']['required'] == ['agent', 'query', 'request_evidence']


def routes():
    return [{'type': 'function', 'function': {'name': 'route', 'parameters': {'type': 'object', 'oneOf': [
        {'type': 'object', 'additionalProperties': False, 'properties': {'agent': {'const': 'chat'}}, 'required': ['agent']},
        {'type': 'object', 'additionalProperties': False, 'properties': {'agent': {'const': 'action'}, 'operation': {'const': 'extract'}}, 'required': ['agent', 'operation']}
    ]}}}]


def test_provider_wire_does_not_widen_or_mutate_canonical_routes():
    tools = routes(); original = copy.deepcopy(tools)
    wire = adapter.agent_tools(tools)
    assert tools == original and len(wire) == 2
    assert wire[0]['function']['parameters']['properties']['agent'] == {'enum': ['chat']}
    assert wire[0]['function']['parameters']['additionalProperties'] is False
    with pytest.raises(ConnectionError, match='invalid function arguments'):
        adapter.agent_calls([{'name': 'route__branch_0', 'arguments': {'agent': 'chat', 'operation': 'extract'}}], tools)
    with pytest.raises(ConnectionError, match='undeclared function'):
        adapter.agent_calls([{'name': 'route', 'arguments': {'agent': 'chat'}}], tools)
    with pytest.raises(ConnectionError, match='unique'):
        adapter.agent_tools(tools + [wire[0]])


def test_branch_tool_roundtrip_preserves_provider_name_and_call_id(monkeypatch):
    pinned = snapshot()
    pinned['settings'].update(model='gpt-4o-mini', extra_parameters={})
    pinned['settings']['model_connection']['endpoint'] = 'https://api.openai.com/v1'
    seen = []
    def post(self, path, payload, headers=None):
        seen.append(copy.deepcopy(payload))
        if len(seen) == 1:
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None, 'tool_calls': [{
                'id': 'call-route', 'type': 'function', 'function': {'name': 'route__branch_0', 'arguments': '{"agent":"chat"}'}}]}}]}
        replay = payload['messages'][-2]['tool_calls'][0]
        assert replay['id'] == payload['messages'][-1]['tool_call_id'] == 'call-route'
        assert replay['function']['name'] == 'route__branch_0'
        assert 'tool_name' not in payload['messages'][-1]
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Ready.'}}]}
    monkeypatch.setattr(ModelConnection, 'post', post)
    messages = [{'role': 'user', 'content': 'Read the synthetic status.'}]
    with core.execution_context(pinned), temporary_credentials({'api_key': 'synthetic'}):
        result = agent_model.complete(messages, routes())
        assert result['calls'][0]['name'] == 'route'
        follow = messages + [{'role': 'assistant', 'content': '', 'tool_calls': [{
            'id': 'call-route', 'type': 'function', 'function': {'name': 'route', 'arguments': {'agent': 'chat'}}}],
            '_provider_state': result['_provider_state']},
            {'role': 'tool', 'tool_call_id': 'call-route', 'tool_name': 'route', 'content': '{"ready":true}'}]
        assert agent_model.complete(follow, routes())['text'] == 'Ready.'


def test_agent_openai_answer_follows_scoped_hybrid_retrieval_and_rerank(system, monkeypatch):
    from ags_app import knowledge, reranker, main
    from test_agent_workspace import plan
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    other = dataset(s, 'Other private dataset'); foreign = upload(s, other)['documents'][0]
    value = body(protocol='openai-compatible', context_limit=65536, provider_model='gpt-4o-mini')
    value['connection']['endpoint'] = 'https://api.openai.com/v1'
    model = register(s, value); select(s, d, model, 'chat'); knowledge.sync(s.owner, d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE', 'langgraph')
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY', 'true')
    monkeypatch.setenv('AEGIS_RERANKER', 'local')
    ranked = []
    monkeypatch.setattr(reranker, 'rank', lambda query, items, limit: (ranked.append(items) or items[:limit]))
    def handle(req):
        payload = json.loads(req.content)
        assert req.headers['authorization'] == 'Bearer synthetic-secret'
        assert payload['model'] == 'gpt-4o-mini'
        if payload.get('tools'):
            tool = next(t['function'] for t in payload['tools'] if 'original' in t['function']['parameters']['properties'].get('query', {}).get('enum', []))
            message = {'tool_calls': [{'id': 'route-1', 'type': 'function', 'function': {
                'name': tool['name'], 'arguments': json.dumps({'agent': 'chat', 'query': 'original', 'request_evidence': 'Who is the owner in the document?'})}}]}
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': message}]})
        assert ranked
        evidence = next(m['content'] for m in payload['messages'] if 'Published vector evidence:\n' in (m.get('content') or ''))
        assert 'Alice' in evidence and foreign['id'] not in evidence
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'Alice is the owner. [1]'}}]})
    cloud_transport(monkeypatch, handle)
    result = plan(s, d, text='Who is the owner in the document?', document_ids=[doc['id']], planner_model_id=model['id'], allow_external=True)
    assert result['agent'] == 'chat', result
    record = main.get_record(result['conversation_id'], s.owner, 'conversation')
    answer = core.store.json(record.ref)['messages'][-1]
    assert answer['answer_workflow']['status'] == 'completed'
    assert {c['document_id'] for c in answer['citations']} == {doc['id']}
    retrieval = answer['tool_trace'][0]['result']['retrieval']
    assert retrieval['mode'] == 'hybrid' and retrieval['reranker_enabled']
