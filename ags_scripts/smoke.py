"""Run against an isolated Compose test deployment. Never uses a live model key."""
import http.cookiejar
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = os.getenv('AEGIS_SMOKE_URL', 'http://127.0.0.1:3000')
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
csrf = ''


def request(path, data=None, method=None, expected=200, raw=False, headers=None):
    hdr = {'X-CSRF-Token': csrf, **(headers or {})}
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        hdr['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + '/api' + path, data=data, method=method, headers=hdr)
    try:
        response = client.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        response = e
    body = response.read()
    assert response.status == expected, (path, response.status, body.decode(errors='replace')[:500])
    return body if raw else json.loads(body)


def upload(dataset_id, name, text, expected=200):
    boundary = 'aegis-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="dataset_id"\r\n\r\n{dataset_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f'Content-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--\r\n').encode()
    return request('/documents/upload', body, expected=expected, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})


def map_models(dataset, models, embedding):
    return request('/datasets/' + dataset['id'] + '/models', {
        'mappings': [{'model_id': model['id'], 'enabled': True} for model in [*models, embedding]],
        'default_chat_model_id': models[0]['id'] if models else None,
        'default_extraction_model_id': models[0]['id'] if models else None,
        'embedding_model_id': embedding['id'],
    }, method='PUT')


def await_job(job_id):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = next(j for j in request('/jobs') if j['id'] == job_id)
        if job['status'] in ('failed', 'cancelled'):
            raise AssertionError(job)
        if job['status'] == 'completed':
            return job
        time.sleep(1)
    raise AssertionError('Job did not reach completion before the integration timeout: ' + job_id)


# Container 'running' is not HTTP readiness; wait for the published web proxy.
deadline = time.monotonic() + 60
while True:
    try:
        status = request('/auth/status')
        break
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
assert status['setup_required']
request('/documents', expected=401)
values = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
password = os.getenv('AEGIS_SMOKE_PASSWORD') or 'Smoke-test-only-' + uuid.uuid4().hex
request('/auth/setup', {'username': 'smoke', 'password': password, 'bootstrap_token': 'wrong'}, expected=403)
request('/auth/setup', {'username': 'smoke', 'password': password, 'bootstrap_token': values['AEGIS_BOOTSTRAP_TOKEN']})
csrf = request('/auth/login', {'username': 'smoke', 'password': password})['csrf_token']
cfg = request('/settings')
assert cfg['model_provider'] == cfg['embedding_provider'] == 'mock'
request('/datasets', {'name': 'Invalid CSRF'}, expected=403, headers={'X-CSRF-Token': ''})
kb = request('/datasets', {'name': 'Integration dataset', 'description': 'Isolated synthetic CI fixture'})
other = request('/datasets', {'name': 'Separate scope'})
unconfigured = request('/datasets', {'name': 'Not configured yet'})
assert request('/datasets/' + unconfigured['id'] + '/models')['mappings'] == []
upload(unconfigured['id'], 'not-uploaded.txt', 'Synthetic missing-model test.', expected=409)

# Catalog entries explicitly reference a mock-only saved connection profile. Nothing
# silently falls back to global generation settings for a newly onboarded dataset.
profile = request('/settings/profiles', {'name': 'Integration mock connection'})
models = []
for name, provider_model, capabilities in [
    ('Integration fast', 'mock-fast', ['chat', 'extraction']),
    ('Integration careful', 'mock-careful', ['chat', 'extraction']),
    ('Integration separate', 'mock-separate', ['chat', 'extraction']),
    ('Integration embedding', 'mock-embedding', ['embedding']),
]:
    models.append(request('/models', {'name': name, 'connection_profile_id': profile['id'],
                                    'provider_model': provider_model, 'capabilities': capabilities, 'enabled': True}))
fast, careful, separate, embedding = models
mapped = map_models(kb, [fast, careful], embedding)
map_models(other, [separate], embedding)
assert mapped['default_chat_model_id'] == fast['id']
assert {m['model_id'] for m in mapped['mappings']} == {fast['id'], careful['id'], embedding['id']}

# The queued job must survive a stopped worker, proving it is not an in-process background task.
use_docker = os.getenv('AEGIS_SMOKE_NO_DOCKER') != 'true'
if use_docker:
    subprocess.run(['docker', 'compose', 'stop', 'worker'], check=True)
first = upload(kb['id'], 'evidence.txt', 'Aegis launch code is COBALT. The invoice total is 420 USD. This document is public test data.')
second = upload(other['id'], 'other.txt', 'A separate project secret phrase is MAGENTA. It must not leak into a scoped answer.')
if use_docker:
    subprocess.run(['docker', 'compose', 'start', 'worker'], check=True)
for result in (first, second):
    await_job(result['jobs'][0]['id'])
doc = first['documents'][0]
assert request('/documents/' + doc['id'])['status'] == 'ready'
assert 'COBALT' in request('/documents/' + doc['id'] + '/preview')['text']
assert b'COBALT' in request('/documents/' + doc['id'] + '/download', raw=True)
conversation = request('/conversations', {'title': 'Scoped smoke', 'dataset_id': kb['id'], 'document_ids': [doc['id']]})
message_path = '/conversations/' + conversation['id'] + '/messages'
request(message_path, {'text': 'Reject an unmapped model', 'dataset_id': kb['id'], 'model_id': separate['id']}, expected=409)
request(message_path, {'text': 'Reject a different dataset document', 'dataset_id': kb['id'], 'model_id': fast['id'],
                       'document_ids': [second['documents'][0]['id']]}, expected=400)
answer = request(message_path, {'text': 'What is the launch code?', 'dataset_id': kb['id'],
                                'model_id': careful['id'], 'allow_external': False})
assert 'COBALT' in answer['message']['text']
assert 'MAGENTA' not in answer['message']['text']
assert answer['message']['mock']
assert answer['message']['model_selection']['model_id'] == careful['id']
assert answer['message']['model_selection']['provider_model'] == 'mock-careful'
assert answer['message']['model_selection']['dataset_id'] == kb['id']
assert all(c['document_id'] == doc['id'] for c in answer['message']['citations'])
assert len(request('/conversations/' + conversation['id'])['messages']) == 2
default_answer = request(message_path, {'text': 'Use the dataset default.', 'dataset_id': kb['id'], 'allow_external': False})
assert default_answer['message']['model_selection']['model_id'] == fast['id']
other_conversation = request('/conversations', {'title': 'Other dataset', 'dataset_id': other['id']})
other_answer = request('/conversations/' + other_conversation['id'] + '/messages', {
    'text': 'What is the secret phrase?', 'dataset_id': other['id'], 'model_id': separate['id'], 'allow_external': False,
})
assert 'MAGENTA' in other_answer['message']['text'] and 'COBALT' not in other_answer['message']['text']
assert other_answer['message']['model_selection']['model_id'] == separate['id']

schema = {'type': 'object', 'properties': {'reference': {'type': ['string', 'null']}}, 'required': ['reference'], 'additionalProperties': False}
template = request('/templates', {'name': 'Smoke extraction', 'schema': schema})
request('/templates/' + template['id'], {'name': 'Smoke extraction v2', 'schema': schema}, method='PUT')
assert len(request('/templates/' + template['id'] + '/versions')) == 2
request('/extractions', {'dataset_id': kb['id'], 'model_id': separate['id'], 'document_ids': [doc['id']],
                         'template_id': template['id'], 'allow_external': False}, expected=409)
extraction = request('/extractions', {'dataset_id': kb['id'], 'model_id': careful['id'], 'document_ids': [doc['id']],
                                    'template_id': template['id'], 'allow_external': False})
await_job(extraction['job']['id'])
result = request('/extractions/' + extraction['id'])
assert result['status'] == 'ready' and 'reference' in result['result']
assert result['model_selection']['model_id'] == careful['id']
assert result['model_selection']['provider_model'] == 'mock-careful'
assert result['model_selection']['connection_profile_id'] == profile['id']
assert b'reference' in request('/extractions/' + extraction['id'] + '/export?format=csv', raw=True)
assert {'api_key', 'oci_api_key', 'master_key'}.isdisjoint(request('/settings/export'))

# Reindex and repeated action checks; delete removes retrieval eligibility and original download.
reindex = request('/documents/' + doc['id'] + '/reindex', {'allow_external': False})
await_job(reindex['id'])
request('/documents/' + doc['id'], method='DELETE')
request('/documents/' + doc['id'], expected=404)
request('/documents/' + doc['id'] + '/download', expected=404, raw=True)
request('/auth/logout', {}, method='POST')
request('/documents', expected=401)
print('PASS: setup/login/CSRF, explicit dataset/model onboarding, missing and unmapped model rejection, selected/default generation routing, cross-dataset isolation, upload/index, scope/citations, storage download, template versions, selected-model extraction/export, reindex/delete, logout; durable queued worker restart: ' + ('verified' if use_docker else 'not run without Docker'))
