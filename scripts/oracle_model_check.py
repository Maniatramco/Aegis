"""Synthetic workflow check with real Oracle, Qdrant and local Ollama models.

Run through the oracle-test Compose service. Only this run's records are removed.
"""
import os
import secrets
import tempfile
import uuid
from pathlib import Path


def run():
    from cryptography.fernet import Fernet
    from app.database import database_url
    url = database_url(Path('/tmp/aegis-oracle-test'))
    if url.get_backend_name() != 'oracle' or url.username != 'AEGIS_TEST':
        raise RuntimeError('Use the dedicated AEGIS_TEST schema.')
    with tempfile.TemporaryDirectory(prefix='aegis-model-check-') as directory:
        os.environ.update(AEGIS_STORAGE_ROOT=directory, MODEL_PROVIDER='ollama',
            EMBEDDING_PROVIDER='ollama', SEARCH_PROVIDER='qdrant',
            AEGIS_MODEL=os.getenv('AEGIS_MODEL', 'qwen3:4b'),
            EMBEDDING_MODEL=os.getenv('EMBEDDING_MODEL', 'nomic-embed-text'),
            AEGIS_OLLAMA_URL='http://ollama:11434', AEGIS_OLLAMA_ENDPOINT_HOSTS='ollama',
            QDRANT_URL='http://qdrant:6333', AEGIS_TIMEOUT='300', AEGIS_ALLOW_MOCK='false',
            AEGIS_MASTER_KEY=Fernet.generate_key().decode())
        from sqlalchemy import select, delete
        from fastapi.testclient import TestClient
        from app import core, main, worker, providers
        from app.provision_account import create_account
        owner = None
        documents = []
        core.init()
        with core.Session() as db:
            if db.scalar(select(core.Record).limit(1)) or db.scalar(select(core.Job).limit(1)):
                raise RuntimeError('The dedicated test schema must have no records or jobs.')
        username = 'model-check-' + uuid.uuid4().hex
        password = secrets.token_urlsafe(32)
        try:
            create_account(username, password)
            with core.Session() as db:
                owner = db.scalar(select(core.User).where(core.User.username == username)).id
            with TestClient(main.app) as client:
                def request(method, path, **kwargs):
                    response = client.request(method, path, **kwargs)
                    if response.status_code != 200:
                        raise RuntimeError(f'{method} {path}: HTTP {response.status_code}')
                    return response.json()

                login = request('POST', '/api/auth/login', json={'username': username, 'password': password})
                client.headers['X-CSRF-Token'] = login['csrf_token']
                print('PASS: Oracle account and authenticated login', flush=True)
                dataset = request('POST', '/api/datasets', json={'name': 'Isolated real-model check'})
                dataset = request('POST', f'/api/datasets/{dataset["id"]}/migrate-settings')
                assert dataset['models_complete'], 'Local model mappings are incomplete.'
                generation = next(m for m in dataset['models'] if 'chat' in m['capabilities'])
                uploaded = request('POST', '/api/documents/upload',
                    files={'files': ('invoice.txt', b'Invoice INV-QA-1\nOwner: Alice\nTotal including tax: 42.00 INR\n', 'text/plain')},
                    data={'dataset_id': dataset['id'], 'allow_external': 'false'})
                documents.extend(d['id'] for d in uploaded['documents'])
                assert worker.run_once(), 'Index job was not claimed.'
                document = request('GET', '/api/documents/' + documents[0])
                assert document['status'] == 'ready', 'Real embedding/indexing failed.'
                print('PASS: document upload, Nomic embeddings and Qdrant indexing', flush=True)
                body = {'name': 'Ignored internal name', 'source_filename': 'mani.json', 'dataset_id': dataset['id'],
                    'schema': {'type': 'object', 'properties': {'total': {'type': 'number', 'description': 'Invoice total including tax'}},
                               'required': ['total'], 'additionalProperties': False}}
                assert client.post('/api/templates', content='{"broken":', headers={'Content-Type': 'application/json'}).status_code == 422
                invalid = body | {'schema': {'type': 'array'}}
                assert client.post('/api/templates/validate', json=invalid).status_code == 400
                template = request('POST', '/api/templates', json=body)
                replacement = request('POST', '/api/templates', json=body)
                assert replacement['id'] == template['id'] and replacement['version'] == 2
                assert any(t['name'] == 'mani.json' for t in request('GET', '/api/templates'))
                print('PASS: JSON/schema validation and filename-based prompt versions', flush=True)
                plan = request('POST', '/api/agent-v2/plans', json={
                    'text': 'Extract the invoice total from the selected document using the selected prompt template.',
                    'planner_model_id': generation['id'], 'dataset_id': dataset['id'],
                    'document_ids': documents, 'template_id': template['id']})
                index = next((i for i, call in enumerate(plan['calls']) if call['tool'] == 'extract'), None)
                assert index is not None, 'The real agent did not propose extraction.'
                call_path = f'/api/agent-v2/plans/{plan["id"]}/calls/{index}'
                before = len(request('GET', '/api/jobs'))
                assert client.post(call_path, json={'confirmed': False}).status_code == 409
                assert len(request('GET', '/api/jobs')) == before, 'Unconfirmed action queued work.'
                accepted = request('POST', call_path, json={'confirmed': True})
                extraction_id = accepted['calls'][index]['result']['extraction_id']
                assert worker.run_once(), 'Extraction job was not claimed.'
                extraction_path = '/api/extractions/' + extraction_id
                result = request('GET', extraction_path)
                assert result['status'] == 'ready' and result['result']['total'] == 42, 'Real invoice extraction was incorrect.'
                completed = request('GET', '/api/agent-v2/plans/' + plan['id'])
                assert completed['calls'][index]['status'] == 'completed', 'Agent progress did not complete.'
                print('PASS: real Qwen3 planning, confirmation, extraction and progress', flush=True)
                reviewed = request('PATCH', extraction_path, json={'version': result['version'], 'result': {'total': 43}})
                assert reviewed['review_status'] == 'reviewed'
                export = request('GET', extraction_path + '/export?format=json')
                assert export['result']['total'] == 43
                assert client.post(extraction_path + '/reextract', json={'version': reviewed['version']}).status_code == 409
                request('POST', extraction_path + '/reextract', json={'version': reviewed['version'], 'confirm_reviewed': True})
                assert worker.run_once(), 'Re-extraction job was not claimed.'
                assert request('GET', extraction_path)['result']['total'] == 42
                previous = next(item for item in request('GET', extraction_path + '/versions')
                                if item['version'] == reviewed['version'])
                assert previous['result']['total'] == 43, 'Reviewed version was not retained.'
                print('PASS: extraction review, export and preservation during re-extraction', flush=True)
                conversation = request('POST', '/api/conversations', json={'dataset_id': dataset['id'], 'document_ids': documents})
                answer = request('POST', f'/api/conversations/{conversation["id"]}/messages', json={'text': 'Who is the invoice owner?'})
                assert 'Alice' in str(answer['message']), 'Document chat missed the known owner.'
                assert answer['message'].get('citations'), 'Document chat returned no citations.'
                request('POST', '/api/auth/logout')
                assert client.get('/api/datasets').status_code == 401
                request('POST', '/api/auth/login', json={'username': username, 'password': password})
                assert request('GET', '/api/datasets')[0]['id'] == dataset['id']
                print('PASS: real document chat with citations, logout and durable sign-in', flush=True)
        finally:
            for document_id in documents:
                providers.delete_vectors(document_id)
            if owner:
                with core.Session.begin() as db:
                    for table in (core.Job, core.Record, core.Login):
                        db.execute(delete(table).where(table.owner == owner))
                    db.execute(delete(core.User).where(core.User.id == owner))
            core.engine.dispose()


if __name__ == '__main__':
    run()
