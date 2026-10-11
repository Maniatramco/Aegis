"""Operator smoke test: actual local generation/embedding, no application writes."""
import json
import os
import time
import urllib.request


def call(base, path, payload=None, timeout=1200):
    raw = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=raw, headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def run():
    base = os.environ.get('AEGIS_OLLAMA_URL', 'http://ollama:11434').rstrip('/')
    model = os.environ.get('AEGIS_MODEL', 'qwen3:4b')
    embedding = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    tags = call(base, '/api/tags', timeout=10).get('models', [])
    installed = {item['name'] for item in tags}
    for name in (model, embedding):
        if name not in installed and name + ':latest' not in installed:
            raise RuntimeError('Required local model is not installed: ' + name)
    started = time.monotonic()
    messages = [{'role': 'user', 'content': 'Return JSON with ok equal to true.'}]
    if model == 'qwen3' or model.startswith('qwen3:'):
        messages.append({'role': 'assistant', 'content': '<think>\n</think>\n\n'})
    response = call(base, '/api/chat', {
        'model': model, 'messages': messages,
        'stream': False, 'think': False,
        'format': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False},
        'options': {'num_ctx': 2048, 'num_predict': 64, 'temperature': 0}, 'keep_alive': '5m',
    }, timeout=180)
    if not response.get('done') or response.get('done_reason') == 'length' or json.loads(response['message']['content']) != {'ok': True}:
        raise RuntimeError('Local generation smoke test did not finish with valid JSON.')
    loaded = call(base, '/api/ps', timeout=10).get('models', [])
    # This is observed offload, not a claim inferred from the host GPU or device probe.
    vram = sum(int(item.get('size_vram', 0)) for item in loaded)
    generate_seconds = round(time.monotonic() - started, 3)
    vectors = call(base, '/api/embed', {'model': embedding, 'input': ['Aegis fictional resume smoke test.'], 'truncate': False}, timeout=180)
    if len(vectors.get('embeddings', [])) != 1 or not vectors['embeddings'][0]:
        raise RuntimeError('Local embedding smoke test failed.')
    ready = call(os.environ.get('API_INTERNAL_URL', 'http://api:8000').rstrip('/'), '/ready', timeout=10)
    if ready.get('status') != 'ready':
        raise RuntimeError('Application dependencies are not ready.')
    from .ocr_smoke import run as vision_smoke
    ocr_result=vision_smoke()
    result = {'passed': True, 'model': model, 'embedding': embedding,'ocr':ocr_result,
              'inference_hardware': 'GPU offload' if vram else 'CPU', 'size_vram_bytes': vram,
              'generation_seconds': generate_seconds, 'total_seconds': round(time.monotonic() - started, 3)}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    run()
