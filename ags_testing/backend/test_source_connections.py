"""Cloud contracts without network accounts; imports use real upload, worker and scoped knowledge."""
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from ags_app import core, main, worker, cloud_sources as cloud, source_connections as sources, dataset_access as access, knowledge
from test_dataset_models import system, dataset, post


def body(d, provider='s3'):
    return {'name': 'Team files', 'provider': provider, 'dataset_id': d['id'], 'bucket': 'team-documents', 'region': 'ap-south-1', 'prefix': 'approved/', 'credentials': {'access_key_id': 'TEST_ACCESS_KEY', 'secret_access_key': 'DO_NOT_EXPOSE'}}


@pytest.fixture
def remote(monkeypatch):
    state = SimpleNamespace(raw=b'Aegis connector project codename Cedar. Invoice total is 42.', fetches=0, builds=0)
    class Adapter:
        def browse(self, folder='', cursor=''):
            if folder == 'outside':
                raise cloud.SourceError('Outside source scope.')
            return [{'id': 'approved/invoice.txt', 'name': 'invoice.txt', 'folder': False, 'supported': True, 'size': len(state.raw), 'revision': 'r1'}, {'id': 'image.png', 'name': 'image.png', 'folder': False, 'supported': False}], 'next-page' if not cursor else ''
        def fetch(self, item, limit):
            state.fetches += 1
            if getattr(state, 'failure', False):
                raise RuntimeError('SECRET signed_url=DO_NOT_EXPOSE')
            if getattr(state, 'after_read', None):
                state.after_read()
            return item['name'], state.raw, {'remote_id': item['id'], 'revision': 'r1', 'original_url': 's3://team-documents/' + item['id']}
    def adapter(cfg, secret):
        state.builds += 1
        return Adapter()
    monkeypatch.setattr(cloud, 'adapter', adapter)
    return state


def connection(s, d, **values):
    return post(s, '/api/source-connections', body(d) | values)


def selections(s, c):
    response = s.api.get('/api/source-connections/' + c['id'] + '/files')
    assert response.status_code == 200, response.text
    return response.json()


def submit(s, c, tokens=None, **values):
    tokens = tokens or [selections(s, c)['items'][0]['selection']]
    return s.api.post('/api/source-connections/' + c['id'] + '/import', json={'selections': tokens, 'publish_to_dataset': True, 'allow_external': True} | values)


def test_credentials_encrypted_and_never_listed(system, remote):
    s = system; d = dataset(s); c = connection(s, d)
    assert c['credentials_configured']
    assert 'secret_ref' not in c and 'DO_NOT_EXPOSE' not in json.dumps(c)
    saved = core.local_store.json(sources.ref(c['id']))
    assert b'DO_NOT_EXPOSE' not in core.local_store.get(saved['secret_ref'])
    assert sources.credentials(saved)['secret_access_key'] == 'DO_NOT_EXPOSE'
    assert 'DO_NOT_EXPOSE' not in s.api.get('/api/source-connections').text
    assert remote.builds == 0  # Saving does not contact cloud or claim a connection test.


def test_test_is_read_only_and_browse_is_paginated(system, remote):
    s = system; d = dataset(s)
    assert post(s, '/api/source-connections/test', body(d))['ok']
    assert s.api.get('/api/source-connections').json() == []
    c = connection(s, d); page = selections(s, c)
    assert page['items'][0]['selection'] and not page['items'][1]['selection']
    assert page['next_cursor'] != 'next-page'
    assert s.api.get('/api/source-connections/' + c['id'] + '/files', params={'cursor': page['next_cursor']}).json()['next_cursor'] == ''
    assert s.api.get('/api/source-connections/' + c['id'] + '/files', params={'cursor': page['next_cursor'], 'folder': 'other'}).status_code == 409
    assert s.api.get('/api/documents').json() == []


@pytest.mark.parametrize('provider', ['s3', 'sharepoint', 'google_drive'])
def test_import_indexes_and_publishes_authorized_knowledge(system, remote, provider):
    s = system; d = dataset(s)
    values = {}
    if provider == 'sharepoint':
        values = {'tenant_id': '11111111-1111-1111-1111-111111111111', 'client_id': '22222222-2222-2222-2222-222222222222', 'site_id': 'tenant.sharepoint.com,site,web', 'drive_id': 'drive', 'credentials': {'client_secret': 'DO_NOT_EXPOSE'}}
    elif provider == 'google_drive':
        values = {'folder_id': 'folder', 'credentials': {'service_account': json.dumps({'type': 'service_account', 'client_email': 'test@example.iam.gserviceaccount.com', 'private_key': 'testkey', 'token_uri': 'https://oauth2.googleapis.com/token'})}}
    c = connection(s, d, provider=provider, **values)
    result = submit(s, c); assert result.status_code == 200, result.text
    item = result.json()['results'][0]; assert item['status'] == 'imported', item
    assert core.store.get('documents/' + item['document_id'] + '/original') == remote.raw
    assert worker.run_once()
    doc = s.api.get('/api/documents/' + item['document_id']).json()
    assert doc['status'] == 'ready' and not doc['requires_reindex']
    assert doc['cloud_source']['provider'] == provider
    assert doc['cloud_source']['connection_id'] == c['id']
    assert 'DO_NOT_EXPOSE' not in json.dumps(doc)
    knowledge.sync(s.owner, d['id'])
    hits = knowledge.search('Cedar invoice total', s.owner, dataset_id=d['id'], source_types=['document_chunk'], limit=20)['matches']
    assert any('Cedar' in h.get('text', '') for h in hits), hits
    other = dataset(s, 'Other')
    assert not any('Cedar' in h.get('text', '') for h in knowledge.search('Cedar invoice total', s.owner, dataset_id=other['id'], source_types=['document_chunk'], limit=20)['matches'])


def test_duplicate_import_reuses_document_and_job_new_content_retained(system, remote):
    s = system; d = dataset(s); c = connection(s, d); tokens = [selections(s, c)['items'][0]['selection']]
    first = submit(s, c, tokens).json()['results'][0]
    second = submit(s, c, tokens).json()['results'][0]
    assert second['status'] == 'already_imported'
    assert first['document_id'] == second['document_id'] and first['jobs'] == second['jobs']
    remote.raw = b'Updated Cedar total is 73.'
    third = submit(s, c, tokens).json()['results'][0]
    assert third['document_id'] != first['document_id']
    assert len(s.api.get('/api/documents').json()) == 2


@pytest.mark.parametrize('surface', ['agent', 'dashboard'])
def test_imported_document_chat_uses_hybrid_rerank_generate_and_validate(system, remote, monkeypatch, surface):
    from ags_app import agent_model, reranker, dataset_models as routing
    from test_agent_workspace import plan
    from test_chat_hybrid_required import install_models
    s = system; d = dataset(s); c = connection(s, d)
    document = submit(s, c).json()['results'][0]['document_id']
    assert worker.run_once()
    knowledge.sync(s.owner, d['id'])
    events = install_models(monkeypatch)
    monkeypatch.setattr(agent_model, 'classify', lambda _: {'intent': 'answer', 'operation': 'none', 'source': 'documents'})
    def answer(messages, tools, **kwargs):
        assert tools == []
        events.append(('answer', None))
        request = next(m['content'] for m in messages if m['role'] == 'user' and 'Published vector evidence:' in m['content'])
        evidence = json.loads(request.split('Published vector evidence:\n', 1)[1])
        record = next(r for r in evidence['records'] if 'Cedar' in json.dumps(r))
        return {'text': 'The Cedar invoice total is 42 [' + str(record['citation_index']) + '].', 'calls': []}
    monkeypatch.setattr(agent_model, 'complete', answer)
    if surface == 'agent':
        result = plan(s, d, text='What is the Cedar invoice total?', document_ids=[document])
        reply = core.store.json(routing.owned(result['conversation_id'], s.owner, 'conversation').ref)['messages'][-1]
        text = result['explanation']
    else:
        from ags_app.ags_agent import dataset_chat_general
        monkeypatch.setattr(dataset_chat_general, 'requires_knowledge', lambda *args, **kwargs: True)
        model = next(m for m in d['models'] if 'chat' in m['capabilities'])
        result = post(s, '/api/dataset-chat/messages', {'text': 'What is the Cedar invoice total?', 'dataset_ids': [d['id']], 'document_ids': [document], 'model_id': model['id']})
        reply = result['message']; text = reply['text']
    assert len(events) >= 2 and events[-1][0] == 'answer'
    assert all(e[0] == 'rerank' for e in events[:-1])
    trace = reply['tool_trace'][0]['result']
    assert trace['retrieval']['mode'] == 'hybrid' and trace['retrieval']['reranker_enabled']
    assert reply['citations'] and reply['answer_workflow']['status'] == 'completed'
    if surface == 'agent': assert trace['answer_check'] == 'passed'
    assert d['id'] in json.dumps(trace['scope']) and '42' in text


def test_removed_copy_can_be_explicitly_reimported(system, remote):
    s = system; d = dataset(s); c = connection(s, d)
    first = submit(s, c).json()['results'][0]
    assert s.api.delete('/api/documents/' + first['document_id']).status_code == 200
    second = submit(s, c).json()['results'][0]
    assert second['status'] == 'imported' and second['document_id'] != first['document_id']


def test_scope_tokens_are_actor_dataset_connection_and_version_bound(system, remote):
    s = system; d = dataset(s); c = connection(s, d)
    token = selections(s, c)['items'][0]['selection']
    other = connection(s, d, name='Another')
    assert submit(s, other, [token]).status_code == 409
    assert submit(s, c, [token[:-4] + 'AAAA']).status_code == 409
    assert submit(s, c, [token, token]).status_code == 422
    assert s.api.put('/api/source-connections/' + c['id'], json=body(d) | {'name': 'Renamed', 'credentials': {}}).status_code == 200
    assert submit(s, c, [token]).status_code == 409
    assert remote.fetches == 0


def test_import_requires_publication_consent_models_and_no_fetch_on_rejection(system, remote):
    s = system; d = dataset(s, mapped=False); c = connection(s, d)
    assert submit(s, c, publish_to_dataset=False).status_code == 409
    assert submit(s, c).status_code == 409
    assert remote.fetches == 0


def test_disabled_and_local_only_connections_do_not_read_cloud(system, remote, monkeypatch):
    s = system; d = dataset(s); c = connection(s, d, enabled=False)
    assert s.api.get('/api/source-connections/' + c['id'] + '/files').status_code == 409
    assert remote.builds == 0
    monkeypatch.setenv('AEGIS_LOCAL_ONLY', 'true')
    assert s.api.post('/api/source-connections/test', json=body(d)).status_code == 409
    assert remote.builds == 0


def test_provider_errors_are_sanitized_and_partial_results_truthful(system, remote):
    s = system; d = dataset(s); c = connection(s, d); remote.failure = True
    response = submit(s, c)
    assert response.status_code == 200 and response.json()['results'][0]['status'] == 'failed'
    assert 'DO_NOT_EXPOSE' not in response.text and not s.api.get('/api/documents').json()


def test_real_nonadmin_cannot_list_test_browse_or_import(system, remote):
    s = system; d = dataset(s); c = connection(s, d); token = selections(s, c)['items'][0]['selection']
    with core.Session.begin() as session:
        session.add(core.User(id='bob', username='bob', password_hash='unused', role='user'))
    async def auth():
        access.request_actor.set('bob'); return 'bob'
    main.app.dependency_overrides[main.auth] = auth
    assert s.api.get('/api/source-connections').status_code == 403
    assert s.api.post('/api/source-connections/test', json=body(d)).status_code == 403
    assert s.api.get('/api/source-connections/' + c['id'] + '/files').status_code == 403
    assert submit(s, c, [token]).status_code == 403


def test_admin_revocation_during_download_blocks_publication(system, remote):
    s = system
    with core.Session.begin() as session:
        session.add(core.User(id='alice', username='Alice', password_hash='unused', role='administrator'))
    async def authenticated():
        access.request_actor.set('alice'); return 'alice'
    main.app.dependency_overrides[main.auth] = authenticated
    d = dataset(s); c = connection(s, d); token = selections(s, c)['items'][0]['selection']
    def revoke():
        with core.Session.begin() as session:
            session.get(core.User, 'alice').role = 'user'
    remote.after_read = revoke
    response = submit(s, c, [token])
    assert response.status_code == 200 and response.json()['results'][0]['status'] == 'failed'
    assert remote.fetches == 1
    with core.Session() as session:
        assert not list(session.scalars(select(core.Record).where(core.Record.kind == 'document')))


def test_selection_expiry_and_scope_rejection_precede_download(system, remote, monkeypatch):
    s = system; d = dataset(s); c = connection(s, d); token = selections(s, c)['items'][0]['selection']
    original = sources.time.time
    monkeypatch.setattr(sources.time, 'time', lambda: original() + 1900)
    assert submit(s, c, [token]).status_code == 409 and remote.fetches == 0
    monkeypatch.setattr(sources.time, 'time', original)
    assert s.api.get('/api/source-connections/' + c['id'] + '/files?folder=outside').status_code == 400
    assert remote.fetches == 0


def test_external_processing_consent_rejected_before_cloud_download(system, remote, monkeypatch):
    s = system; d = dataset(s); c = connection(s, d); tokens = [selections(s, c)['items'][0]['selection']]
    original = main.external_check
    def requires_consent(consent, *args, **kwargs):
        if not consent: raise HTTPException(409, 'External consent required.')
        return original(consent, *args, **kwargs)
    monkeypatch.setattr(main, 'external_check', requires_consent)
    assert submit(s, c, tokens, allow_external=False).status_code == 409
    assert remote.fetches == 0


@pytest.mark.parametrize('changes', [{'prefix': 'sibling'}, {'bucket': 'https://evil.example'}, {'region': '../../x'}, {'expected_owner': 'wrong'}, {'credentials': {'endpoint': 'https://evil.example'}}, {'extra': 'anything'}])
def test_invalid_s3_configuration_rejected(system, changes):
    s = system; d = dataset(s)
    assert s.api.post('/api/source-connections', json=body(d) | changes).status_code == 422


def test_credentials_required_again_for_changed_scope(system):
    s = system; d = dataset(s); c = connection(s, d)
    assert s.api.put('/api/source-connections/' + c['id'], json=body(d) | {'prefix': 'other/', 'credentials': {}}).status_code == 422


def test_google_external_token_host_rejected(system):
    s = system; d = dataset(s)
    value = {'type': 'service_account', 'client_email': 'test@example.com', 'private_key': 'secret', 'token_uri': 'https://evil.example/token'}
    response = s.api.post('/api/source-connections', json=body(d) | {'provider': 'google_drive', 'folder_id': 'folder', 'credentials': {'service_account': json.dumps(value)}})
    assert response.status_code == 422 and 'secret' not in response.text


def test_s3_real_sdk_contract_scope_pagination_conditional_read(monkeypatch):
    import boto3
    from botocore.stub import Stubber
    client = boto3.client('s3', region_name='ap-south-1', aws_access_key_id='test', aws_secret_access_key='test')
    monkeypatch.setattr(boto3, 'client', lambda *args, **kwargs: client)
    adapter = cloud.S3({'auth_mode': 'server_identity', 'region': 'ap-south-1', 'bucket': 'bucket', 'prefix': 'approved/', 'expected_owner': '123456789012'}, {})
    with Stubber(client) as stub:
        stub.add_response('list_objects_v2', {'Contents': [{'Key': 'approved/a.txt', 'Size': 4, 'ETag': 'tag'}], 'CommonPrefixes': [{'Prefix': 'approved/sub/'}], 'NextContinuationToken': 'next'}, {'Bucket': 'bucket', 'ExpectedBucketOwner': '123456789012', 'Prefix': 'approved/', 'Delimiter': '/', 'MaxKeys': 100})
        items, cursor = adapter.browse(); assert cursor == 'next' and items[1]['supported']
        stub.add_response('get_object', {'Body': io.BytesIO(b'data'), 'ContentLength': 4, 'ETag': 'tag'}, {'Bucket': 'bucket', 'ExpectedBucketOwner': '123456789012', 'Key': 'approved/a.txt', 'IfMatch': 'tag'})
        assert adapter.fetch(items[1], 10)[1] == b'data'
        stub.assert_no_pending_responses()
    with pytest.raises(cloud.SourceError): adapter.browse('approved-sibling/')
    with pytest.raises(cloud.SourceError): adapter.fetch({'id': 'other/a.txt'}, 10)


def test_sharepoint_native_token_scoped_library_ancestry_and_content(monkeypatch):
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'POST': return {'access_token': 'test-bearer'}
        if url.endswith('/sites/site/drives'): return {'value': [{'id': 'drive'}]}
        if url.endswith('/children'): return {'value': [{'id': 'file', 'name': 'a.txt', 'file': {}, 'eTag': 'v1'}]}
        if url.endswith('/items/file'): return {'id': 'file', 'name': 'a.txt', 'file': {}, 'eTag': 'v1', 'parentReference': {'driveId': 'drive', 'id': 'folder'}}
        if url.endswith('/items/folder'): return {'id': 'folder', 'folder': {}}
        raise AssertionError(url)
    monkeypatch.setattr(cloud, 'request_json', request)
    monkeypatch.setattr(cloud, 'download', lambda url, headers, limit, microsoft_redirect=False: b'text')
    adapter = cloud.SharePoint({'tenant_id': 'tenant', 'client_id': 'client', 'site_id': 'site', 'drive_id': 'drive', 'folder_id': 'folder'}, {'client_secret': 'secret'})
    items, _ = adapter.browse(); assert items[0]['supported']
    assert adapter.fetch(items[0], 20)[1] == b'text'
    assert calls[0][2]['data']['grant_type'] == 'client_credentials'
    with pytest.raises(cloud.SourceError): adapter.browse(cursor='https://evil.example/next')
    with pytest.raises(cloud.SourceError): adapter.fetch(items[0] | {'revision': 'changed'}, 20)


def test_google_native_exports_shared_drive_flags_and_scope(monkeypatch):
    adapter = object.__new__(cloud.GoogleDrive); adapter.cfg = {'folder_id': 'root-folder'}; adapter.headers = {'Authorization': 'Bearer test'}
    document = {'id': 'doc', 'name': 'Report', 'mimeType': 'application/vnd.google-apps.document', 'parents': ['root-folder'], 'version': '1', 'modifiedTime': 'today'}
    calls = []
    def request(method, url, **kwargs):
        calls.append((url, kwargs))
        if url == adapter.BASE: return {'files': [document], 'nextPageToken': 'page2'}
        if url.endswith('/doc'): return document
        if url.endswith('/root-folder'): return {'id': 'root-folder', 'mimeType': cloud.FOLDER}
        if url.endswith('/outside'): return {'id': 'outside', 'mimeType': cloud.FOLDER}
        raise AssertionError(url)
    monkeypatch.setattr(cloud, 'request_json', request)
    downloads = []
    monkeypatch.setattr(cloud, 'download', lambda url, headers, limit: downloads.append(url) or b'docx')
    items, cursor = adapter.browse(); assert cursor == 'page2' and items[0]['name'] == 'Report.docx'
    assert adapter.fetch(items[0], 20)[1] == b'docx' and '/export?mimeType=' in downloads[0]
    assert any(kwargs.get('params', {}).get('includeItemsFromAllDrives') == 'true' for _, kwargs in calls)
    with pytest.raises(cloud.SourceError): adapter.browse('outside')


def test_graph_redirect_drops_auth_and_rejects_private_host(monkeypatch):
    requests = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or (httpx.Response(302, headers={'location': 'https://tenant.sharepoint.com/download'}) if request.url.host == 'graph.microsoft.com' else httpx.Response(200, content=b'ok')))
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=transport, **kwargs))
    monkeypatch.setattr(cloud.socket, 'getaddrinfo', lambda *args: [(None, None, None, None, ('93.184.216.34', 443))])
    assert cloud.download('https://graph.microsoft.com/file/content', {'Authorization': 'Bearer secret'}, 10, True) == b'ok'
    assert requests[0].headers['authorization'] == 'Bearer secret' and 'authorization' not in requests[1].headers
    monkeypatch.setattr(cloud.socket, 'getaddrinfo', lambda *args: [(None, None, None, None, ('127.0.0.1', 443))])
    with pytest.raises(cloud.SourceError): cloud.download('https://graph.microsoft.com/file/content', {}, 10, True)


def test_stream_limits_and_permission_errors(monkeypatch):
    original = httpx.Client
    def use(response):
        monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: response), **kwargs))
    use(httpx.Response(200, content=b'12345'))
    with pytest.raises(cloud.SourceError): cloud.download('https://www.googleapis.com/file', {}, 4)
    use(httpx.Response(403, text='SECRET_ERROR'))
    with pytest.raises(cloud.SourceError, match='permission was denied') as error: cloud.download('https://www.googleapis.com/file', {}, 20)
    assert 'SECRET_ERROR' not in str(error.value)
