"""Single-document direct chat: bounded RAM only, no jobs, chunks or vectors."""
import asyncio
import copy
import os
import re
import threading
import time
from typing import Literal

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from . import core, dataset_models as routing, providers

RETENTION_SECONDS = 3600
MAX_TEXT_BYTES = 40000
MAX_CONTEXT_BYTES = 48000
_documents = {}
_lock = threading.Lock()


def purge_expired():
    with _lock:
        for id in [id for id, doc in _documents.items() if doc['expires_at'] <= time.time()]:
            del _documents[id]


async def expiry_loop():
    while True:
        purge_expired()
        await asyncio.sleep(60)


def owned_document(id, owner):
    purge_expired()
    with _lock:
        doc = _documents.get(id)
        if not doc or doc['owner'] != owner:
            raise HTTPException(404, 'Temporary document expired or is no longer available. Upload it again.')
        return copy.deepcopy(doc)


def public_document(doc):
    return {key: doc[key] for key in ('id', 'name', 'size', 'text_bytes', 'expires_at')} | {
        'temporary': True, 'status': 'ready', 'page_count': len(doc['pages']),
        'indexed': False, 'embedded': False,
    }


def chat_snapshot(owner, id):
    model = routing.owned(id, owner, 'model')
    data = routing.model_data(model)
    if not data.get('enabled', True) or 'chat' not in data['capabilities']:
        raise HTTPException(409, 'Choose an enabled registered Chat model.')
    profile = routing.owned(data['connection_profile_id'], owner, 'config_profile')
    snap = routing.profile_snapshot(profile, data.get('connection_profile_version'))
    cfg = core.settings().copy()
    cfg.update({key: snap['settings'][key] for key in routing.MODEL_KEYS if key in snap['settings']})
    cfg['model'] = cfg['oci_model'] = data['provider_model']
    try:
        core.enforce_local_only(cfg)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if cfg['model_provider'] == 'mock' and os.getenv('AEGIS_ALLOW_MOCK') != 'true':
        raise HTTPException(409, 'Mock models are disabled. Choose a registered Chat model.')
    snap.update(settings=cfg, model_id=model.id, model_name=model.name,
                model_version=model.version, provider_model=data['provider_model'], capability='chat')
    return snap


class Turn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    text: str = Field(max_length=12000)


class DirectMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=12000)
    history: list[Turn] = Field(default_factory=list, max_length=8)
    allow_external: bool = False


def install(app, auth):
    @app.post('/api/temporary-chat/documents')
    async def upload_document(files: list[UploadFile] = File(...), session_id: str = Form(..., min_length=16, max_length=100, pattern=r'^[A-Za-z0-9_-]+$'), owner=Depends(auth)):
        if len(files) != 1:
            raise HTTPException(400, 'Temporary chat accepts exactly one document. Choose one PDF, DOCX, or UTF-8 TXT file.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', session_id):
            raise HTTPException(400, 'Invalid temporary session identifier.')
        file = files[0]
        name = (file.filename or 'document').replace('\\', '/').split('/')[-1][:200]
        if name.rsplit('.', 1)[-1].lower() not in {'pdf', 'docx', 'txt'}:
            raise HTTPException(400, 'Choose a PDF, DOCX, or UTF-8 TXT document.')
        limit = min(core.settings()['max_upload_mb'], 25) * 1024 * 1024
        raw = await file.read(limit + 1)
        if not raw or len(raw) > limit:
            raise HTTPException(413 if raw else 400, 'File is empty or exceeds the temporary upload size limit.')
        from .worker import parse_document
        try:
            pages = await asyncio.to_thread(parse_document, name, raw)
        except UnicodeDecodeError:
            raise HTTPException(400, 'TXT files must use UTF-8. Save this file as UTF-8 and try again.')
        except Exception as error:
            detail = str(error) if isinstance(error, ValueError) else 'This document could not be read. Upload an unlocked, valid document with selectable text.'
            raise HTTPException(400, detail) from error
        pages = [page for page in pages if page['text'].strip()]
        text_bytes = sum(len(page['text'].encode('utf-8')) for page in pages)
        if not pages:
            raise HTTPException(400, 'No readable text was found. Scanned documents need OCR before direct chat.')
        if text_bytes > MAX_TEXT_BYTES:
            raise HTTPException(413, 'This document exceeds the 40 KB text limit for direct chat. Use a shorter document or the regular dataset workflow. No text was indexed or embedded.')
        doc = {'id': core.uid(), 'owner': owner, 'session_id': session_id, 'name': name,
               'size': len(raw), 'text_bytes': text_bytes, 'pages': pages,
               'expires_at': time.time() + RETENTION_SECONDS}
        purge_expired()
        with _lock:
            previous = [id for id, item in _documents.items() if item['owner'] == owner and item['session_id'] == session_id]
            if not previous and (sum(item['owner'] == owner for item in _documents.values()) >= 5 or len(_documents) >= 128):
                raise HTTPException(429, 'Too many temporary documents are open. Clear an earlier temporary chat and try again.')
            for id in previous:
                del _documents[id]
            _documents[doc['id']] = doc
        return public_document(doc)

    @app.get('/api/temporary-chat/documents/{id}')
    def preview_document(id: str, owner=Depends(auth)):
        doc = owned_document(id, owner)
        return public_document(doc) | {'pages': doc['pages']}

    @app.delete('/api/temporary-chat/documents/{id}')
    def clear_document(id: str, owner=Depends(auth)):
        owned_document(id, owner)
        with _lock:
            _documents.pop(id, None)
        return {'ok': True}

    @app.post('/api/temporary-chat/messages')
    async def message(body: DirectMessage, owner=Depends(auth)):
        doc = owned_document(body.document_id, owner)
        snap = chat_snapshot(owner, body.model_id)
        if snap['settings']['model_provider'] not in {'ollama', 'mock'} and not body.allow_external:
            raise HTTPException(409, 'Allow this temporary document and question to be sent to the selected external Chat model first.')
        history = [turn.model_dump() for turn in body.history]
        context_bytes = doc['text_bytes'] + len(body.text.encode('utf-8')) + sum(len(turn.text.encode('utf-8')) for turn in body.history)
        if context_bytes > MAX_CONTEXT_BYTES:
            raise HTTPException(400, 'This document, question, and chat history exceed the direct context limit. Start a new chat or ask a shorter question. The document has not been truncated.')
        sources = [{'document_name': doc['name'], 'text': page['text'], 'page': page['page']} for page in doc['pages']]
        def answer():
            with core.execution_context(snap):
                return providers.answer(body.text, sources, history)
        try:
            text = await asyncio.to_thread(answer)
        except providers.ProviderError as error:
            raise HTTPException(502, str(error)) from error
        except Exception as error:
            raise HTTPException(502, 'The selected Chat model could not answer. Check the model connection or use a smaller document.') from error
        used = {int(value) for value in re.findall(r'\[(\d+)\]', text)}
        citations = [{'index': index + 1, 'document_name': doc['name'], 'page': source['page'],
                      'excerpt': source['text'][:1200], 'temporary_document_id': doc['id']}
                     for index, source in enumerate(sources) if index + 1 in used]
        selection = {key: snap[key] for key in ('model_id', 'model_name', 'model_version', 'provider_model', 'connection_profile_id', 'connection_profile_version')}
        return {'temporary': True, 'indexed': False, 'embedded': False,
                'message': {'id': core.uid(), 'role': 'assistant', 'text': text, 'citations': citations,
                            'created_at': time.time(), 'model_selection': selection,
                            'mock': snap['settings']['model_provider'] == 'mock'}}
