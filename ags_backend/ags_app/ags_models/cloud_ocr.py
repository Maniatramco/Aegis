"""Select OCR from the dataset's extraction registration, never its embeddings."""
from urllib.parse import urlsplit
import re

PROVIDERS = ('gemini', 'openai')


def eligible(snapshot):
    kind = provider(snapshot)
    return kind == 'gemini' or kind == 'openai' and bool(re.fullmatch(r'gpt-4o(?:-mini)?(?:-\d{4}-\d{2}-\d{2})?', snapshot['provider_model']))


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
    data = routing.dataset_config(dataset)
    selected = data.get('ocr_model_id')
    if selected == 'local':
        return None
    try:
        snapshot = routing.resolve_model(dataset, 'extraction', selected)
    except HTTPException:
        # A missing default is allowed for inspecting an embedding index; an
        # invalid saved extraction mapping must never select another OCR service.
        if selected or data.get('default_extraction_model_id'):
            raise
        return None
    if selected and not eligible(snapshot):
        raise HTTPException(409, 'Selected OCR model must be an enabled mapped vision-capable extraction registration.')
    return snapshot if provider(snapshot) else None


def adapter(name):
    if name == 'gemini':
        from .providers.ags_gcp import ocr
    elif name == 'openai':
        from .providers.ags_openai import ocr
    else:
        raise ValueError('Unsupported cloud OCR provider.')
    return ocr
