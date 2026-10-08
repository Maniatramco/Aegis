"""Generic registrations drive real routing; cloud traffic is mocked, never billed."""
import copy
import io
import json
from types import SimpleNamespace
import httpx
import pytest
from app import core, providers, worker, dataset_models as routing, model_connections as connections
from test_dataset_models import system, dataset, mapping, upload, conversation, message, template, post


def body(category='chat', protocol='azure-openai', **values):
    endpoint = {
        'ollama': 'http://127.0.0.1:11435', 'azure-openai': 'https://example.openai.azure.com/openai/v1',
        'openai-compatible': 'https://api.openai.com/v1', 'bedrock': 'https://bedrock-runtime.us-east-1.amazonaws.com',
        'vertex': 'https://us-central1-aiplatform.googleapis.com', 'oci': 'https://inference.generativeai.us-chicago-1.oci.oraclecloud.com',
    }[protocol]
    auth = {'ollama': 'none', 'azure-openai': 'api_key', 'openai-compatible': 'api_key', 'bedrock': 'aws_keys', 'vertex': 'bearer_token', 'oci': 'config_profile'}[protocol]
    secrets = {'api_key': {'api_key': 'synthetic-secret'}, 'aws_keys': {'access_key_id': 'synthetic-id', 'secret_access_key': 'synthetic-secret'}, 'bearer_token': {'token': 'synthetic-secret'}}.get(auth, {})
    return {'name': category+' registered', 'category': category, 'provider_model': 'deployed-model', 'timeout': 45, 'enabled': True,
        'connection': {'protocol': protocol, 'endpoint': endpoint, 'auth_mode': auth, 'region': 'us-chicago-1' if protocol == 'oci' else 'us-central1' if protocol == 'vertex' else 'us-east-1', 'project_id': 'test-project', 'compartment_id': 'ocid1.compartment.oc1..synthetic', 'embedding_format': 'titan', 'chat_format': 'generic'},
        'credentials': secrets, **values}


def register(s, value):return post(s, '/api/model-registrations', value)


def cloud_transport(monkeypatch, handler):
    original = httpx.Client
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(connections.httpx, 'Client', client)


def select(s, d, m, capability):
    current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    key = {'chat': 'default_chat_model_id', 'extraction': 'default_extraction_model_id', 'embedding': 'embedding_model_id'}[capability]
    return mapping(s, d, mappings=current['mappings']+[{'model_id': m['id'], 'enabled': True}], **{key: m['id']})


def test_registration_keeps_secrets_encrypted_and_global_settings_unchanged(system):
    s = system; before = core.settings(); model = register(s, body())
    assert model['capabilities'] == ['chat'] and model['credential_configured']
    assert model['connection']['endpoint'].endswith('/openai/v1')
    assert core.settings() == before
    record = routing.owned(model['id'], s.owner, 'model')
    profile = routing.owned(model['connection_profile_id'], s.owner, 'config_profile')
    assert 'synthetic-secret' not in core.store.get(record.ref).decode()
    assert 'synthetic-secret' not in core.local_store.get(profile.ref).decode()
    encrypted = core.local_store.get(f'secrets/profiles/{profile.id}/v1/connection.enc')
    assert b'synthetic-secret' not in encrypted
    assert json.loads(core.secret_cipher().decrypt(encrypted)) == {'api_key': 'synthetic-secret'}
    for path in ('/api/models', '/api/settings/profiles', '/api/settings/profiles/'+profile.id+'/export'):
        assert 'synthetic-secret' not in s.api.get(path).text
    assert s.api.post('/api/settings/profiles/'+profile.id+'/activate').status_code == 400
    assert s.api.put('/api/settings/profiles/'+profile.id, json={'name': 'overwrite'}).status_code == 400


def test_three_mapping_categories_required_and_optimistic_save(system):
    s = system; d = dataset(s); current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    assert current['models_complete']
    payload = {k: current[k] for k in ('mappings', 'embedding_model_id', 'default_chat_model_id', 'default_extraction_model_id')}
    for key in ('embedding_model_id', 'default_chat_model_id', 'default_extraction_model_id'):
        assert s.api.put('/api/datasets/'+d['id']+'/models', json=payload|{key: None}).status_code == 400
    saved = s.api.put('/api/datasets/'+d['id']+'/models', json=payload|{'expected_version': current['version']})
    assert saved.status_code == 200
    assert s.api.put('/api/datasets/'+d['id']+'/models', json=payload|{'expected_version': current['version']}).status_code == 409
    assert s.api.get('/api/datasets/'+d['id']).json()['models_complete']


def test_next_chat_uses_updated_connection_without_global_activation(system, monkeypatch):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]; c = conversation(s, d, [doc['id']])
    m = register(s, body(provider_model='deployment-one')); select(s, d, m, 'chat')
    sent = []
    def handle(req):
        payload = json.loads(req.content); sent.append((str(req.url), payload['model'], req.headers['authorization']))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'Alice [1].'}}]})
    cloud_transport(monkeypatch, handle)
    assert message(s, c, allow_external=False).status_code == 409
    assert message(s, c).status_code == 200
    updated = s.api.put('/api/model-registrations/'+m['id'], json=body(provider_model='deployment-two', credentials={'api_key': 'replacement-secret'}))
    assert updated.status_code == 200, updated.text
    answer = message(s, c); assert answer.status_code == 200, answer.text
    assert answer.json()['message']['model_selection']['connection_profile_version'] == 2
    assert [x[1:] for x in sent] == [('deployment-one', 'Bearer synthetic-secret'), ('deployment-two', 'Bearer replacement-secret')]
    assert all(x[0] == 'https://example.openai.azure.com/openai/v1/chat/completions' for x in sent)
    assert core.settings()['model_provider'] == 'mock'


def test_queued_extraction_keeps_model_and_secret_version(system, monkeypatch):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    m = register(s, body('extraction', provider_model='first-deployment')); select(s, d, m, 'extraction')
    t = template(s)
    first = post(s, '/api/extractions', {'dataset_id': d['id'], 'document_ids': [doc['id']], 'template_id': t['id'], 'allow_external': True})
    revised = s.api.put('/api/model-registrations/'+m['id'], json=body('extraction', provider_model='second-deployment', credentials={'api_key': 'second-secret'}))
    assert revised.status_code == 200
    sent = []
    def handle(req):
        payload = json.loads(req.content); sent.append((payload['model'], req.headers['authorization']))
        assert payload['response_format']['json_schema']['schema']['properties']['data']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'data': {'owner': 'Alice'}, 'evidence': []})}}]})
    cloud_transport(monkeypatch, handle)
    assert worker.run_once()
    assert s.api.get('/api/extractions/'+first['id']).json()['status'] == 'ready'
    second = post(s, '/api/extractions', {'dataset_id': d['id'], 'document_ids': [doc['id']], 'template_id': t['id'], 'allow_external': True})
    assert worker.run_once()
    assert s.api.get('/api/extractions/'+second['id']).json()['status'] == 'ready'
    assert sent == [('first-deployment', 'Bearer synthetic-secret'), ('second-deployment', 'Bearer second-secret')]


def test_model_read_overlapping_edit_keeps_matching_connection_version(system, monkeypatch):
    s = system; d = dataset(s)
    m = register(s, body(provider_model='deployment-one')); select(s, d, m, 'chat')
    before = routing.owned(m['id'], s.owner, 'model')
    assert s.api.put('/api/model-registrations/'+m['id'], json=body(provider_model='deployment-two', credentials={'api_key': 'second-secret'})).status_code == 200
    owned = routing.owned
    # Simulate a request that read the model row immediately before the edit,
    # then reads the connection row immediately after its transaction commits.
    monkeypatch.setattr(routing, 'owned', lambda id, owner, kind: before if kind=='model' and id==m['id'] else owned(id, owner, kind))
    snapshot = routing.resolve_model(owned(d['id'], s.owner, 'knowledge_base'), 'chat')
    assert snapshot['model_version']==1 and snapshot['connection_profile_version']==1
    assert snapshot['settings']['model']=='deployment-one'
    with core.execution_context(snapshot):
        assert connections.credentials()['api_key']=='synthetic-secret'
    monkeypatch.setattr(routing, 'owned', owned)
    current = routing.resolve_model(owned(d['id'], s.owner, 'knowledge_base'), 'chat')
    assert current['model_version']==2 and current['connection_profile_version']==2
    assert current['settings']['model']=='deployment-two'
    with core.execution_context(current):
        assert connections.credentials()['api_key']=='second-secret'


def test_embedding_edit_requires_mapping_acknowledgement_and_reindex(system, monkeypatch):
    s = system; d = dataset(s); m = register(s, body('embedding')); selected = select(s, d, m, 'embedding')
    dimensions = [3]
    def handle(req):
        payload = json.loads(req.content)
        return httpx.Response(200, json={'data': [{'index': i, 'embedding': [1.0]*dimensions[0]} for i, _ in enumerate(payload['input'])]})
    cloud_transport(monkeypatch, handle)
    doc = upload(s, d)['documents'][0]; c = conversation(s, d, [doc['id']])
    old = core.store.get('documents/'+doc['id']+'/index.json')
    assert s.api.put('/api/model-registrations/'+m['id'], json=body('embedding', provider_model='new-embedding')).status_code == 200
    assert message(s, c).status_code == 409
    current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    payload = {k: current[k] for k in ('mappings', 'embedding_model_id', 'default_chat_model_id', 'default_extraction_model_id')}
    assert s.api.put('/api/datasets/'+d['id']+'/models', json=payload).status_code == 400
    applied = s.api.put('/api/datasets/'+d['id']+'/models', json=payload|{'acknowledge_reindex': True})
    assert applied.status_code == 200 and applied.json()['index_generation'] == selected['index_generation']+1
    assert core.store.get('documents/'+doc['id']+'/index.json') == old
    assert s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    dimensions[0] = 4
    post(s, '/api/documents/'+doc['id']+'/reindex', {'allow_external': True}); assert worker.run_once()
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    assert core.store.json('documents/'+doc['id']+'/index.json')['dimensions'] == 4
    assert core.store.get('documents/'+doc['id']+'/original') == b'Invoice total 42. Alice is the owner.'


def test_credentials_retain_clear_and_never_follow_an_endpoint_change(system):
    s = system; m = register(s, body())
    changed = body(provider_model='another-model', credentials={})
    result = s.api.put('/api/model-registrations/'+m['id'], json=changed)
    assert result.status_code == 200 and result.json()['credential_configured']
    destination = copy.deepcopy(changed); destination['connection']['endpoint'] = 'https://different.openai.azure.com/openai/v1'
    assert s.api.put('/api/model-registrations/'+m['id'], json=destination).status_code == 400
    result = s.api.put('/api/model-registrations/'+m['id'], json=changed|{'enabled': False, 'clear_credentials': True})
    assert result.status_code == 200 and not result.json()['credential_configured']
    assert s.api.put('/api/model-registrations/'+m['id'], json=changed).status_code == 400


def test_registration_ownership_and_local_only_enforcement(system, monkeypatch):
    s = system; d = dataset(s); m = register(s, body()); s.owner = 'bob'
    assert s.api.get('/api/models').json() == []
    assert s.api.put('/api/model-registrations/'+m['id'], json=body()).status_code == 404
    assert s.api.post('/api/model-registrations/test', json=body(existing_model_id=m['id'], allow_external=True)).status_code == 404
    s.owner = 'alice'; monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'true')
    m2 = register(s, body())  # Registration is allowed, transmitting data is not.
    assert s.api.post('/api/model-registrations/test', json=body(allow_external=True)).status_code == 409
    current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    payload = {k: current[k] for k in ('mappings', 'embedding_model_id', 'default_chat_model_id', 'default_extraction_model_id')}
    payload['mappings'].append({'model_id': m2['id'], 'enabled': True}); payload['default_chat_model_id'] = m2['id']
    assert s.api.put('/api/datasets/'+d['id']+'/models', json=payload).status_code == 409


def test_probe_is_real_adapter_request_and_does_not_persist_credentials(system, monkeypatch):
    s = system; calls = []
    def handle(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [1, 2, 3]}]})
    cloud_transport(monkeypatch, handle)
    assert s.api.post('/api/model-registrations/test', json=body('embedding')).status_code == 400
    assert calls == []
    result = s.api.post('/api/model-registrations/test', json=body('embedding', allow_external=True))
    assert result.status_code == 200, result.text
    assert result.json()['ok'] and result.json()['dimensions'] == 3
    assert len(calls) == 1 and calls[0].endswith('/embeddings')
    assert s.api.get('/api/models').json() == [] and s.api.get('/api/settings/profiles').json() == []
    assert not list(core.DATA.glob('secrets/profiles/**/*'))


@pytest.mark.parametrize('endpoint', ['http://example.com/v1', 'https://169.254.169.254', 'https://127.0.0.1/v1', 'https://example.openai.azure.com@evil.example/v1', 'https://example.openai.azure.com/openai/v1?key=secret', 'https://example.openai.azure.com.evil.example/openai/v1'])
def test_unsafe_endpoints_rejected_before_any_request(system, endpoint):
    value = body(); value['connection']['endpoint'] = endpoint
    assert system.api.post('/api/model-registrations', json=value).status_code == 400


def test_ollama_registered_endpoint_used_for_probe_and_embedding_digest(system, monkeypatch):
    s = system; urls = []
    def handle(req):
        urls.append(str(req.url))
        if req.method == 'GET':
            return httpx.Response(200, json={'models': [{'name': 'nomic-embed-text:latest', 'digest': 'a'*64}]})
        return httpx.Response(200, json={'embeddings': [[1, 2, 3]]})
    cloud_transport(monkeypatch, handle)
    value = body('embedding', 'ollama', provider_model='nomic-embed-text:latest')
    result = s.api.post('/api/model-registrations/test', json=value)
    assert result.status_code == 200, result.text
    m = register(s, value); d = dataset(s); select(s, d, m, 'embedding')
    snapshot = routing.execution_snapshot(routing.owned(d['id'], s.owner, 'knowledge_base'), 'embedding')
    assert snapshot['settings']['_embedding_digest'] == 'a'*64
    assert urls and all(u.startswith('http://127.0.0.1:11435/') for u in urls)


@pytest.mark.parametrize('category', ['chat', 'extraction', 'embedding'])
@pytest.mark.parametrize('protocol', ['azure-openai', 'openai-compatible', 'bedrock', 'vertex', 'oci'])
def test_native_protocol_contracts(system, monkeypatch, protocol, category):
    s = system; calls = []
    schema = {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status'], 'additionalProperties': False}
    text = json.dumps({'status': 'ready'}) if category == 'extraction' else 'ready'
    def handle(req):
        data = json.loads(req.content); calls.append((str(req.url), data))
        assert req.headers['authorization'] == 'Bearer synthetic-secret'
        if category == 'embedding':
            result = {'predictions': [{'embeddings': {'values': [1, 2, 3]}}]} if protocol == 'vertex' else {'data': [{'index': 0, 'embedding': [1, 2, 3]}]}
        else:
            result = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]} if protocol == 'vertex' else {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}
        return httpx.Response(200, json=result)
    cloud_transport(monkeypatch, handle)
    class Bedrock:
        def converse(self, **payload):
            calls.append(('converse', payload)); return {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': text}]}}}
        def invoke_model(self, **payload):
            calls.append(('invoke_model', json.loads(payload['body']))); return {'body': io.BytesIO(json.dumps({'embedding': [1, 2, 3]}).encode())}
    monkeypatch.setattr(connections.ModelConnection, 'bedrock', lambda self: Bedrock())
    class OCI:
        def chat(self, payload):
            import oci
            calls.append(('chat', oci.util.to_dict(payload)))
            return SimpleNamespace(data=SimpleNamespace(chat_response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=[SimpleNamespace(text=text)]))])))
        def embed_text(self, payload):
            import oci
            calls.append(('embed', oci.util.to_dict(payload))); return SimpleNamespace(data=SimpleNamespace(embeddings=[[1, 2, 3]]))
    monkeypatch.setattr(connections.ModelConnection, 'oci_client', lambda self: OCI())
    m = register(s, body(category, protocol)); profile = routing.owned(m['connection_profile_id'], s.owner, 'config_profile')
    snapshot = routing.profile_snapshot(profile)
    with core.execution_context(snapshot):
        adapter = connections.ModelConnection(core.settings(), embedding=category == 'embedding')
        result = adapter.embed(['test'], query=True) if category == 'embedding' else adapter.generate('instruction', 'test', schema if category == 'extraction' else None)
    assert len(calls) == 1
    if category == 'embedding':
        assert len(result) == 1 and len(result[0]) == 3
    else:
        assert result == ({'status': 'ready'} if category == 'extraction' else 'ready')
    operation, payload = calls[0]
    if protocol == 'bedrock':
        assert operation == ('invoke_model' if category == 'embedding' else 'converse')
        assert payload.get('inputText', 'test') == 'test'
    elif protocol == 'oci':
        assert payload['compartment_id'] == 'ocid1.compartment.oc1..synthetic'
        assert payload['serving_mode']['model_id'] == 'deployed-model'
        if category == 'embedding': assert payload['input_type'] == 'SEARCH_QUERY' and payload['truncate'] == 'NONE'
    elif protocol == 'vertex':
        assert '/v1/projects/test-project/locations/us-central1/publishers/google/models/deployed-model:' in operation
        if category == 'embedding': assert payload['instances'][0]['task_type'] == 'RETRIEVAL_QUERY'
    else:
        assert payload['model'] == 'deployed-model'
        if category == 'extraction': assert payload['response_format']['json_schema']['schema'] == schema


def test_error_messages_do_not_expose_secrets_or_accept_bad_embeddings(system, monkeypatch):
    s = system; value = body('embedding', allow_external=True)
    invalid = [False]
    def handle(req):
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [0, 0]}]}) if invalid[0] else httpx.Response(401, json={'error': 'synthetic-secret provider details'})
    cloud_transport(monkeypatch, handle)
    response = s.api.post('/api/model-registrations/test', json=value)
    assert response.status_code == 400 and 'HTTP 401' in response.text and 'synthetic-secret' not in response.text
    invalid[0] = True
    result = s.api.post('/api/model-registrations/test', json=value)
    assert result.status_code == 400 and 'zero or unnormalizable embedding' in result.text


def test_registered_embeddings_cannot_be_ignored_by_managed_retrieval(system):
    s = system; d = dataset(s)
    core.store.put_json('configuration/settings.json', core.settings() | {'search_provider': 'oci'})
    model = register(s, body('embedding'))
    current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    payload = {k: current[k] for k in ('mappings', 'embedding_model_id', 'default_chat_model_id', 'default_extraction_model_id')}
    payload['mappings'].append({'model_id': model['id'], 'enabled': True})
    payload['embedding_model_id'] = model['id']
    result = s.api.put('/api/datasets/'+d['id']+'/models', json=payload)
    assert result.status_code == 400 and 'Local or Qdrant' in result.text
    assert s.api.get('/api/datasets/'+d['id']+'/models').json()['embedding_model_id'] == current['embedding_model_id']


def test_local_context_limit_applies_to_next_chat_without_reindex(system, monkeypatch):
    from app import ollama_provider as ollama
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']])
    m=register(s,body(protocol='ollama',provider_model='qwen3:4b',context_limit=32768));select(s,d,m,'chat')
    assert m['context_limit']==32768
    source={'document_id':doc['id'],'document_name':'Synthetic large excerpt','text':'Alice is the owner. '+'x'*70000,'chunk_id':'chunk-1','score':1}
    monkeypatch.setattr(providers,'search',lambda *args,**kwargs:[source])
    sent=[]
    def response(path,payload,timeout):
        sent.append(payload['options']['num_ctx'])
        return {'done':True,'done_reason':'stop','message':{'content':'Alice [1].'}}
    monkeypatch.setattr(ollama,'request',response)
    failed=message(s,c)
    assert failed.status_code==502 and 'context budget' in failed.text and '32,768' in failed.text
    assert sent==[]
    updated=s.api.put('/api/model-registrations/'+m['id'],json=body(protocol='ollama',provider_model='qwen3:4b',context_limit=65536))
    assert updated.status_code==200 and updated.json()['context_limit']==65536
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    result=message(s,c)
    assert result.status_code==200,result.text
    assert result.json()['message']['model_selection']['context_limit']==65536
    assert sent==[65536]
    assert s.api.get('/api/models').json()[0]['context_limit']==65536
    assert core.settings().get('context_limit') is None


def test_local_context_limits_are_per_role_and_queued_extraction_is_pinned(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    chat_model=register(s,body(protocol='ollama',provider_model='qwen3:4b',context_limit=65536));select(s,d,chat_model,'chat')
    extraction_model=register(s,body('extraction','ollama',provider_model='qwen3:4b',context_limit=48000));select(s,d,extraction_model,'extraction')
    t=template(s)
    run=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    queued=core.store.json('jobs/'+run['job']['id']+'.json')['execution']
    assert queued['settings']['context_limit']==48000
    assert s.api.put('/api/model-registrations/'+extraction_model['id'],json=body('extraction','ollama',provider_model='qwen3:4b',context_limit=131072)).status_code==200
    dataset_record=routing.owned(d['id'],s.owner,'knowledge_base')
    assert routing.execution_snapshot(dataset_record,'chat')['settings']['context_limit']==65536
    assert routing.execution_snapshot(dataset_record,'extraction')['settings']['context_limit']==131072
    assert core.store.json('jobs/'+run['job']['id']+'.json')['execution']['settings']['context_limit']==48000


@pytest.mark.parametrize('limit',[8191,262145,0,True,32768.5,'65536'])
def test_invalid_local_context_limits_rejected(system,limit):
    assert system.api.post('/api/model-registrations',json=body(protocol='ollama',context_limit=limit)).status_code==422


def test_local_context_defaults_and_unsupported_categories(system):
    m=register(system,body(protocol='ollama'))
    assert m['context_limit']==32768
    assert system.api.post('/api/model-registrations',json=body('embedding','ollama',context_limit=65536)).status_code==400
    assert system.api.post('/api/model-registrations',json=body(context_limit=65536)).status_code==400
