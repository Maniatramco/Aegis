"""OpenAI page transcription using the dataset's pinned extraction connection."""
import base64
import hashlib
import json
import re
from .... import core, runtime_config
from ...cloud_ocr import provider
from ...connection import ModelConnection
from ...parameters import validate_parameters


def configure(snapshot, limits):
    cfg = snapshot['settings']
    connection = cfg.get('model_connection') or {}
    if provider(snapshot) != 'openai' or not re.fullmatch(r'gpt-4o(?:-mini)?(?:-\d{4}-\d{2}-\d{2})?', snapshot['provider_model']):
        raise ValueError('OpenAI OCR requires a mapped GPT-4o or GPT-4o Mini extraction model; embedding models cannot read images.')
    identity = {key: snapshot.get(key) for key in ('model_id', 'model_version', 'connection_profile_id', 'connection_profile_version', 'provider_model')}
    identity.update(connection=connection, parameters=cfg.get('extra_parameters', {}))
    return limits | {'provider': 'openai', 'model': snapshot['provider_model'],
        'endpoint': connection['endpoint'], 'protocol': 5, 'execution': snapshot,
        'timeout': min(limits['timeout'], cfg['timeout']),
        'context': min(limits['context'], cfg.get('context_limit') or runtime_config.get('AEGIS_DEFAULT_MODEL_CONTEXT_TOKENS')),
        'output': min(limits['output'], cfg.get('max_output_tokens') or runtime_config.get('AEGIS_DEFAULT_MODEL_OUTPUT_TOKENS')),
        'digest': hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
        'digest_type': 'configuration'}


def available(cfg):
    with core.execution_context(cfg['execution']):
        ModelConnection(core.settings())  # Validate pinned credentials; no inference.
    return cfg


def transcribe(image, cfg, instruction, schema):
    with core.execution_context(cfg['execution']):
        settings = core.settings()
        adapter = ModelConnection(settings)
        extra = validate_parameters(settings.get('extra_parameters', {}), adapter.c['protocol'], 'extraction', adapter.c)
        payload = {'model': adapter.model, 'max_completion_tokens': cfg['output'], 'temperature': 0.1, **extra,
            'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Transcribe every visible line. Return only text and unreadable in the requested JSON.'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(image).decode('ascii'), 'detail': 'high'}}]}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'page_transcription', 'strict': True, 'schema': schema}}}
        data = adapter.post('/chat/completions', payload)
    choice = data['choices'][0]
    message = choice.get('message') or {}
    return {'done': choice.get('finish_reason') == 'stop' and not message.get('refusal'),
        'message': {'content': message.get('content')}, 'done_reason': choice.get('finish_reason')}
