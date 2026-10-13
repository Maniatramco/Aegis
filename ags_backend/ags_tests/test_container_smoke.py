import pytest
from ags_app import container_smoke


@pytest.mark.parametrize('vram,hardware', [(0, 'CPU'), (123456, 'GPU offload')])
def test_smoke_reports_observed_offload_and_real_calls(monkeypatch, vram, hardware):
    sent = []
    def call(base, path, payload=None, timeout=1200):
        sent.append((path, payload))
        return {'/api/tags': {'models': [{'name': 'qwen3:4b'}, {'name': 'nomic-embed-text:latest'}]},
                '/api/chat': {'done': True, 'message': {'content': '{"ok":true}'}},
                '/api/ps': {'models': [{'size_vram': vram}]},
                '/api/embed': {'embeddings': [[0.1, 0.2]]}, '/ready': {'status': 'ready'}}[path]
    monkeypatch.setattr(container_smoke, 'call', call)
    from ags_app import ocr_smoke
    monkeypatch.setattr(ocr_smoke,'run',lambda:{'passed':True,'inference_hardware':hardware})
    monkeypatch.setenv('AEGIS_MODEL', 'qwen3:4b')
    monkeypatch.setenv('EMBEDDING_MODEL', 'nomic-embed-text')
    result = container_smoke.run()
    assert result['inference_hardware'] == hardware
    assert [path for path, _ in sent] == ['/api/tags', '/api/chat', '/api/ps', '/api/embed', '/ready']
    assert sent[1][1]['think'] is False


def test_missing_model_fails_before_generation(monkeypatch):
    monkeypatch.setattr(container_smoke, 'call', lambda *args, **kwargs: {'models': []})
    with pytest.raises(RuntimeError, match='not installed'):
        container_smoke.run()
