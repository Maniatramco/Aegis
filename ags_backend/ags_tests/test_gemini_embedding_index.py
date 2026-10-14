"""Gemini's omitted zero index must not weaken vector ordering checks."""
import pytest
from ags_app import core
from ags_app.model_connections import ModelConnection, ConnectionError


def adapter(monkeypatch, rows, host='generativelanguage.googleapis.com'):
    monkeypatch.delenv('AEGIS_LOCAL_ONLY', raising=False)
    monkeypatch.setenv('AEGIS_MODEL_ENDPOINT_HOSTS', host)
    cfg = dict(core.settings(), embedding_provider='registered',
               embedding_model='gemini-embedding-2', embedding_context_limit=8192,
               embedding_extra_parameters={}, timeout=30,
               embedding_connection={'protocol': 'openai-compatible',
                   'endpoint': 'https://' + host + '/v1beta/openai',
                   'auth_mode': 'api_key', 'dimensions': 2})
    model = ModelConnection(cfg, embedding=True,
                            credentials_override={'api_key': 'synthetic-key'})
    monkeypatch.setattr(model, 'post', lambda *_: {'data': rows})
    return model


def test_omitted_zero_index_and_reordered_batch(monkeypatch):
    model = adapter(monkeypatch, [
        {'index': 1, 'embedding': [0.0, 2.0]},
        {'embedding': [3.0, 0.0]}])
    assert model.embed(['first text', 'second text']) == [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.parametrize('rows', [
    [{'embedding': [1, 0]}, {'embedding': [0, 1]}],
    [{'embedding': [1, 0]}, {'index': 2, 'embedding': [0, 1]}],
    [{'embedding': [1, 0]}],
    [{'embedding': [1, 0]}, {'index': 1, 'embedding': [float('nan'), 1]}],
])
def test_invalid_batch_still_fails(monkeypatch, rows):
    with pytest.raises(ConnectionError):
        adapter(monkeypatch, rows).embed(['first text', 'second text'])


def test_other_providers_still_require_explicit_index(monkeypatch):
    with pytest.raises(ConnectionError):
        adapter(monkeypatch, [{'embedding': [1, 0]}], host='api.openai.com').embed(['text'])
