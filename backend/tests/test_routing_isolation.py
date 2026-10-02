"""Independent regression checks for per-run model/credential isolation."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from cryptography.fernet import Fernet
from app import core, providers
from app.dataset_models import public_selection


@pytest.fixture
def routed_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA', tmp_path)
    monkeypatch.setenv('AEGIS_MASTER_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('OPENAI_API_KEY', 'global-test-key-must-not-leak')
    snapshots = []
    for name in ('alpha', 'beta'):
        ref = f'secrets/profiles/{name}/v1/openai.enc'
        core.local_store.put(ref, core.secret_cipher().encrypt(f'{name}-test-key'.encode()))
        snapshots.append({
            'settings': core.DEFAULTS | {'model_provider': 'openai', 'model': f'model-{name}', 'timeout': 5},
            'secret_refs': {'openai': ref, 'oci': None},
            'model_id': name, 'model_name': name, 'model_version': 1,
            'provider_model': f'model-{name}', 'connection_profile_id': name,
            'connection_profile_version': 1, 'dataset_id': f'dataset-{name}',
            'index_generation': 1,
        })
    return snapshots


def test_execution_context_is_thread_local_and_restored(routed_profiles):
    baseline = core.settings()
    barrier = Barrier(2)
    def inspect(snapshot):
        with core.execution_context(snapshot):
            barrier.wait(timeout=5)
            result = (core.settings()['model'], core.api_key())
            with core.execution_context({'settings': snapshot['settings'] | {'model': 'nested'}, 'secret_refs': {}}):
                assert core.settings()['model'] == 'nested'
                assert core.api_key() == ''
            assert core.settings()['model'] == snapshot['settings']['model']
            barrier.wait(timeout=5)
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(inspect, routed_profiles))
    assert results == [('model-alpha', 'alpha-test-key'), ('model-beta', 'beta-test-key')]
    assert core.settings() == baseline
    assert core._execution.get() is None


def test_execution_context_restored_after_error(routed_profiles):
    with pytest.raises(RuntimeError):
        with core.execution_context(routed_profiles[0]):
            raise RuntimeError('interrupted')
    assert core._execution.get() is None


def test_interleaved_real_stream_adapter_uses_selected_model_and_key(routed_profiles, monkeypatch):
    requests = []
    real_client = httpx.AsyncClient
    async def respond(request):
        payload = json.loads(request.content)
        requests.append((payload['model'], request.headers['authorization']))
        await asyncio.sleep(0.01)
        text = payload['model'] + ' [1]'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=(
            'data: ' + json.dumps({'type': 'response.output_text.delta', 'delta': text}) + '\n\n' +
            'data: ' + json.dumps({'type': 'response.completed'}) + '\n\n'
        ).encode())
    monkeypatch.setattr(providers.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    async def execute(snapshot):
        with core.execution_context(snapshot):
            assert await asyncio.to_thread(core.api_key) == snapshot['model_id'] + '-test-key'
            output = []
            async for token in providers.answer_stream_async('Question', [{'document_name': 'sample.txt', 'text': 'Evidence'}]):
                output.append(token)
                await asyncio.sleep(0)
            return ''.join(output)
    async def run():
        return await asyncio.gather(*(execute(snapshot) for snapshot in routed_profiles))
    assert asyncio.run(run()) == ['model-alpha [1]', 'model-beta [1]']
    assert sorted(requests) == [('model-alpha', 'Bearer alpha-test-key'), ('model-beta', 'Bearer beta-test-key')]
    assert core._execution.get() is None


def test_public_provenance_omits_configuration_and_credential_references(routed_profiles):
    public = public_selection(routed_profiles[0])
    assert public['provider_model'] == 'model-alpha'
    assert public['dataset_id'] == 'dataset-alpha'
    text = json.dumps(public)
    assert 'secret_refs' not in text and 'secrets/' not in text and 'settings' not in text
    assert 'test-key' not in text


def test_extraction_adapter_sends_selected_model_with_its_profile_key(routed_profiles, monkeypatch):
    requests = []
    real_client = httpx.Client
    def respond(request):
        payload = json.loads(request.content)
        requests.append((payload['model'], request.headers['authorization'], payload['text']['format']['type']))
        result = json.dumps({'value': payload['model']})
        return httpx.Response(200, json={'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': result}]}]})
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    schema = {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value'], 'additionalProperties': False}
    for snapshot in routed_profiles:
        with core.execution_context(snapshot):
            assert providers.extract('Synthetic evidence', schema) == {'value': snapshot['provider_model']}
    assert requests == [('model-alpha', 'Bearer alpha-test-key', 'json_schema'), ('model-beta', 'Bearer beta-test-key', 'json_schema')]
