"""Gemini page transcription using a dataset's pinned extraction registration."""
import hashlib
import json
from urllib.parse import urlsplit
from .... import core
from ...connection import ModelConnection
from ...parameters import validate_parameters


def dataset_snapshot(dataset):
    from .... import dataset_models as routing
    from fastapi import HTTPException
    try: snapshot = routing.resolve_model(dataset, 'extraction')
    except HTTPException: return None  # Inspecting an embedding index requires no extraction default.
    cfg = snapshot['settings']
    connection = cfg.get('model_connection') or {}
    if (cfg.get('model_provider') == 'registered'
            and connection.get('protocol') == 'openai-compatible'
            and urlsplit(connection.get('endpoint', '')).hostname == 'generativelanguage.googleapis.com'
            and snapshot['provider_model'].startswith('gemini-')):
        return snapshot
    return None


def configure(snapshot, limits):
    cfg = snapshot['settings']
    connection = cfg.get('model_connection') or {}
    if (connection.get('protocol') != 'openai-compatible'
            or urlsplit(connection.get('endpoint', '')).hostname != 'generativelanguage.googleapis.com'
            or not snapshot['provider_model'].startswith('gemini-')):
        raise ValueError('OCR requires a Gemini Developer API extraction registration.')
    identity = {key: snapshot.get(key) for key in ('model_id', 'model_version', 'connection_profile_id', 'connection_profile_version', 'provider_model')}
    identity['connection'] = connection
    identity['parameters'] = cfg.get('extra_parameters', {})
    return limits | {'provider': 'gemini', 'model': snapshot['provider_model'],
        'endpoint': connection['endpoint'], 'protocol': 4, 'execution': snapshot,
        'context': min(limits['context'], cfg.get('context_limit') or 32768),
        'output': min(limits['output'], cfg.get('max_output_tokens') or 4096),
        # Cloud APIs do not expose installed weight digests. This pins configuration.
        'digest': hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
        'digest_type': 'configuration'}


def available(cfg):
    with core.execution_context(cfg['execution']):
        ModelConnection(core.settings())  # Validate saved credentials and endpoint; no inference.
    return cfg


def transcribe(image, cfg, instruction, schema):
    import base64
    with core.execution_context(cfg['execution']):
        settings = core.settings()
        adapter = ModelConnection(settings)
        extra = validate_parameters(settings.get('extra_parameters', {}), adapter.c['protocol'], 'extraction', adapter.c)
        payload = {'model': adapter.model, 'max_completion_tokens': cfg['output'], 'temperature': 0.1, **extra,
            'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Transcribe every visible line. Return only text and unreadable in the requested JSON.'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')}}]}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'page_transcription', 'strict': True, 'schema': schema}}}
        data = adapter.post('/chat/completions', payload)
    choice = data['choices'][0]
    message = choice.get('message') or {}
    return {'done': choice.get('finish_reason') == 'stop' and not message.get('refusal'),
        'message': {'content': message.get('content')}, 'done_reason': choice.get('finish_reason')}
