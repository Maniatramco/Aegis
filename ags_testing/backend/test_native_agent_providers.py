"""Real provider wire contracts and SDK objects, with no cloud traffic or secrets."""
import json
from types import SimpleNamespace
import httpx
import pytest
from ags_app import core, agent_model, token_usage, model_connections, providers
from ags_app.ags_models import provider_registry
from ags_app.ags_models.validation import temporary_credentials, credentials
from test_dataset_models import system
from test_model_registration import body, register, routing, cloud_transport

TOOL = {'type': 'function', 'function': {'name': 'connection_status', 'description': 'Read the synthetic status.', 'parameters': {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['ready']}}, 'required': ['status'], 'additionalProperties': False}}}
MESSAGES = [{'role': 'system', 'content': 'Use the tool.'}, {'role': 'user', 'content': 'Status?'}]


@pytest.mark.parametrize('protocol,format', [('bedrock','generic'), ('vertex','generic'), ('oci','generic'), ('oci','cohere')])
def test_native_agent_tool_roundtrip_usage_and_registered_credentials(system, monkeypatch, protocol, format):
    value = body('chat', protocol, max_output_tokens=256, context_limit=32768)
    value['connection']['chat_format'] = format
    model = register(system, value)
    snapshot = routing.profile_snapshot(routing.owned(model['connection_profile_id'], system.owner, 'config_profile'))
    snapshot['settings']['_agent_require_tool'] = True
    requests = []
    turns = [0]
    def is_first():
        first = turns[0] == 0
        turns[0] += 1
        return first
    class Bedrock:
        def converse(self, **payload):
            requests.append(payload)
            first = is_first()
            content = [{'toolUse': {'toolUseId': 'native_call', 'name': 'connection_status', 'input': {'status': 'ready'}}}] if first else [{'text': 'Ready.'}]
            return {'stopReason': 'tool_use' if first else 'end_turn', 'output': {'message': {'content': content}}, 'usage': {'inputTokens': 10, 'outputTokens': 3}}
    monkeypatch.setattr(model_connections.ModelConnection, 'bedrock', lambda _: Bedrock())
    def vertex(req):
        requests.append(json.loads(req.content)); assert req.headers['authorization'] == 'Bearer synthetic-secret'
        first = is_first()
        parts = [{'functionCall': {'name': 'connection_status', 'args': {'status': 'ready'}}, 'thoughtSignature': 'opaque-signature'}] if first else [{'text': 'Ready.'}]
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': parts}}], 'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 2, 'thoughtsTokenCount': 1}})
    cloud_transport(monkeypatch, vertex)
    class OCI:
        def chat(self, payload):
            import oci
            from oci.generative_ai_inference import models
            requests.append(oci.util.to_dict(payload))
            first = is_first()
            usage = models.Usage(prompt_tokens=10, completion_tokens=3, total_tokens=13)
            if format == 'cohere':
                response = models.CohereChatResponse(text='' if first else 'Ready.', finish_reason='COMPLETE', usage=usage,
                    tool_calls=[models.CohereToolCall(name='connection_status', parameters={'status':'ready'})] if first else [])
            else:
                response = models.GenericChatResponse(usage=usage, choices=[models.ChatChoice(finish_reason='tool_calls' if first else 'stop', message=models.AssistantMessage(
                    content=[] if first else [models.TextContent(text='Ready.')], tool_calls=[models.FunctionCall(id='native_call', name='connection_status', arguments='{"status":"ready"}')] if first else []))])
            return SimpleNamespace(data=SimpleNamespace(chat_response=response))
    monkeypatch.setattr(model_connections.ModelConnection, 'oci_client', lambda _: OCI())
    with core.execution_context(snapshot), token_usage.collect() as usage:
        first = agent_model.complete(MESSAGES, [TOOL])
        assert first['calls'][0]['name'] == 'connection_status' and first['calls'][0]['arguments'] == {'status':'ready'}
        c = first['calls'][0]
        assistant = {'role':'assistant','content':'','tool_calls':[{'id':c['id'],'function':{'name':c['name'],'arguments':c['arguments']}}]}
        if first.get('_provider_state'): assistant['_provider_state'] = first['_provider_state']
        follow = MESSAGES + [assistant, {'role':'tool','tool_call_id':c['id'],'tool_name':c['name'],'content':'{"status":"ready"}'}]
        snapshot['settings']['_agent_require_tool'] = False
        pieces = []
        answer = agent_model.complete(follow, [TOOL], on_token=pieces.append)
        assert answer['text'] == 'Ready.' and not answer['calls'] and pieces == ['Ready.']
        totals = token_usage.summary(usage)
        assert totals['input_tokens'] == 20 and totals['output_tokens'] == 6 and totals['complete']
    assert len(requests) == 2
    if protocol == 'bedrock':
        assert requests[0]['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'] == TOOL['function']['parameters']
        assert requests[1]['messages'][-1]['content'][0]['toolResult']['toolUseId'] == c['id']
    elif protocol == 'vertex':
        assert requests[0]['tools'][0]['functionDeclarations'][0]['parametersJsonSchema'] == TOOL['function']['parameters']
        assert requests[1]['contents'][-2]['parts'][0]['thoughtSignature'] == 'opaque-signature'
        assert requests[1]['contents'][-1]['parts'][0]['functionResponse']['name'] == c['name']
    else:
        assert requests[0]['chat_request']['max_tokens'] == 256
        assert requests[0]['chat_request']['tools'][0]['name'] == c['name']
        if format == 'cohere':
            assert requests[0]['chat_request']['preamble_override'] == 'Use the tool.'
            assert requests[1]['chat_request']['tool_results'][0]['call']['parameters'] == {'status':'ready'}
            assert requests[1]['chat_request']['message'] == ''
            assert requests[1]['chat_request']['chat_history'][-2]['message'] == 'Status?'
            assert requests[1]['chat_request']['chat_history'][-1]['role'] == 'CHATBOT'
        else:
            assert requests[1]['chat_request']['messages'][-1]['tool_call_id'] == c['id']
            assert not requests[1]['chat_request']['messages'][-2]['content']


def test_provider_catalog_and_gemini_need_no_custom_hostname_allowlist(system, monkeypatch):
    monkeypatch.delenv('AEGIS_MODEL_ENDPOINT_HOSTS', raising=False)
    choices = system.api.get('/api/model-providers').json()
    assert {p['id'] for p in choices} == {'anthropic','ollama','openai','gemini','azure-openai','bedrock','vertex','oci','openai-compatible'}
    assert all(p['protocol'] in provider_registry.REGISTRY for p in choices)
    gemini = next(p for p in choices if p['id'] == 'gemini')
    assert model_connections.validate_endpoint(gemini['endpoint'], gemini['protocol']) == gemini['endpoint']


@pytest.mark.parametrize('bad', [False, True])
def test_chat_probe_checks_function_calling_and_never_saves_credentials(system, monkeypatch, bad):
    def handle(req):
        payload = json.loads(req.content)
        assert payload['tool_choice'] == 'required' and payload['tools'][0]['function']['name'] == 'connection_status'
        assert req.headers['authorization'] == 'Bearer synthetic-secret'
        message = {'content':'Ready'} if bad else {'content':None, 'tool_calls':[{'id':'call_test','function':{'name':'connection_status','arguments':'{"status":"ready"}'}}]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop' if bad else 'tool_calls','message':message}]})
    cloud_transport(monkeypatch,handle)
    result = system.api.post('/api/model-registrations/test',json=body(allow_external=True))
    assert result.status_code == (400 if bad else 200)
    if not bad: assert result.json()['agent_tool_call_validated']
    assert system.api.get('/api/models').json() == []
    assert system.api.get('/api/settings/profiles').json() == []
    assert credentials() == {}


def test_temporary_probe_credentials_are_reset_even_after_failure():
    with pytest.raises(RuntimeError):
        with temporary_credentials({'api_key':'synthetic'}):
            assert credentials() == {'api_key':'synthetic'}
            raise RuntimeError('synthetic')
    assert credentials() == {}


@pytest.mark.parametrize('protocol', ['bedrock','vertex','oci','anthropic'])
@pytest.mark.parametrize('failure', ['refused','malformed','not_tool_capable','budget','timeout'])
def test_native_agent_failures_are_bounded_and_never_expose_provider_secrets(system, monkeypatch, protocol, failure):
    value = body('chat',protocol,context_limit=32768,max_output_tokens=256)
    m = register(system,value)
    snap = routing.profile_snapshot(routing.owned(m['connection_profile_id'],system.owner,'config_profile'))
    cfg = snap['settings']
    cfg['_agent_require_tool'] = True
    selected = provider_registry.provider(cfg['model_connection'])
    invoked = []
    def fail(connection,payload):
        invoked.append(payload)
        if failure == 'timeout':
            raise RuntimeError('synthetic-secret private provider response')
        if failure == 'refused':
            from ags_app.ags_models.validation import ConnectionError
            raise ConnectionError('The Agent model returned an incomplete or refused response.')
        call = {'id':'call_test','name':'connection_status','arguments':'invalid'}
        return {'text':'','calls':[] if failure == 'not_tool_capable' else [call]}, {}
    monkeypatch.setattr(selected,'agent_complete',fail)
    if failure == 'budget': cfg['context_limit'] = 256
    with core.execution_context(snap), token_usage.collect() as usage:
        with pytest.raises(providers.ProviderError) as error:
            agent_model.complete(MESSAGES,[TOOL])
        assert 'synthetic-secret' not in str(error.value) and 'private provider response' not in str(error.value)
        assert len(invoked) == (0 if failure == 'budget' else 1)
        if failure != 'budget': assert token_usage.summary(usage)['model_calls'] == 1
