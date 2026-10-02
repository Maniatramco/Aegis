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


def upload(kb_id, name, text):
    boundary = 'aegis-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="kb_id"\r\n\r\n{kb_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f'Content-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--\r\n').encode()
    return request('/documents/upload', body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})


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


assert request('/auth/status')['setup_required']
request('/documents', expected=401)
values = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
password = os.getenv('AEGIS_SMOKE_PASSWORD') or 'Smoke-test-only-' + uuid.uuid4().hex
request('/auth/setup', {'username': 'smoke', 'password': password, 'bootstrap_token': 'wrong'}, expected=403)
request('/auth/setup', {'username': 'smoke', 'password': password, 'bootstrap_token': values['AEGIS_BOOTSTRAP_TOKEN']})
csrf = request('/auth/login', {'username': 'smoke', 'password': password})['csrf_token']
assert request('/settings')['model_provider'] == 'mock'
request('/knowledge-bases', {'name': 'Invalid CSRF'}, expected=403, headers={'X-CSRF-Token': ''})
kb = request('/knowledge-bases', {'name': 'Integration knowledge', 'description': 'Isolated CI fixture'})
other = request('/knowledge-bases', {'name': 'Separate scope'})

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
conversation = request('/conversations', {'title': 'Scoped smoke', 'kb_id': kb['id'], 'document_ids': [doc['id']]})
answer = request('/conversations/' + conversation['id'] + '/messages', {'text': 'What is the launch code?', 'allow_external': False})
assert 'COBALT' in answer['message']['text']
assert 'MAGENTA' not in answer['message']['text']
assert answer['message']['mock']
assert all(c['document_id'] == doc['id'] for c in answer['message']['citations'])
assert len(request('/conversations/' + conversation['id'])['messages']) == 2

schema = {'type': 'object', 'properties': {'reference': {'type': ['string', 'null']}}, 'required': ['reference'], 'additionalProperties': False}
template = request('/templates', {'name': 'Smoke extraction', 'schema': schema})
request('/templates/' + template['id'], {'name': 'Smoke extraction v2', 'schema': schema}, method='PUT')
assert len(request('/templates/' + template['id'] + '/versions')) == 2
extraction = request('/extractions', {'document_ids': [doc['id']], 'template_id': template['id'], 'allow_external': False})
await_job(extraction['job']['id'])
result = request('/extractions/' + extraction['id'])
assert result['status'] == 'ready' and 'reference' in result['result']
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
print('PASS: setup/login/CSRF, upload/index, scope/citations, storage download, template versions, extraction/export, reindex/delete, logout; durable queued worker restart: ' + ('verified' if use_docker else 'not run without Docker'))
