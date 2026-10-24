"""Select OCR from the dataset's extraction registration, never its embeddings."""
from urllib.parse import urlsplit

PROVIDERS = ('gemini', 'openai')


def provider(snapshot):
    cfg = snapshot['settings']
    connection = cfg.get('model_connection') or {}
    if cfg.get('model_provider') != 'registered' or connection.get('protocol') != 'openai-compatible':
        return None
    host = urlsplit(connection.get('endpoint', '')).hostname
    if host == 'generativelanguage.googleapis.com' and snapshot['provider_model'].startswith('gemini-'):
        return 'gemini'
    if host == 'api.openai.com':
        return 'openai'
    return None


def dataset_snapshot(dataset):
    from fastapi import HTTPException
    from .. import dataset_models as routing
    try:
        snapshot = routing.resolve_model(dataset, 'extraction')
    except HTTPException:
        # A missing default is allowed for inspecting an embedding index; an
        # invalid saved extraction mapping must never select another OCR service.
        if routing.dataset_config(dataset).get('default_extraction_model_id'):
            raise
        return None
    return snapshot if provider(snapshot) else None


def adapter(name):
    if name == 'gemini':
        from .providers.ags_gcp import ocr
    elif name == 'openai':
        from .providers.ags_openai import ocr
    else:
        raise ValueError('Unsupported cloud OCR provider.')
    return ocr
