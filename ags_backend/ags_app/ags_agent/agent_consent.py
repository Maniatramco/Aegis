"""Processing consent preflight; ordinary Aegis chat uses configured providers."""
import hashlib
import json
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import core, database_control, dataset_models as routing
from ..temporary_chat import chat_snapshot


class ConsentScope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = ''
    planner_model_id: str = ''
    roles: list[Literal['chat', 'embedding', 'extraction']] = Field(default_factory=lambda:['chat'], min_length=1, max_length=3)
    model_ids: dict[Literal['embedding', 'extraction'], str] = Field(default_factory=dict)


def notices(snapshot, role, main):
    cfg = snapshot['settings']
    if role == 'chat':
        main.external_check(True, False, cfg)
        return []
    try:
        main.external_check(False, role == 'embedding', cfg)
        return []
    except HTTPException as error:
        if error.status_code != 409 or error.detail != 'This action sends document text or your query to the configured external provider. Confirm external data transmission first.':
            raise
    destinations = []
    def add(kind, provider, text):
        database=database_control.state().get('active_connection',{}) if kind=='search' and cfg.get('search_provider')=='oracle' else {}
        identity = [kind, provider, snapshot.get('connection_profile_id'), snapshot.get('connection_profile_version'),
                    cfg.get(kind+'_connection'), cfg.get('oci_region'), cfg.get('oci_storage_namespace'),
                    cfg.get('oci_storage_bucket'), cfg.get('oci_storage_region'), cfg.get('oci_storage_prefix'),
                    {key:database.get(key) for key in ('name','region','dsn')},cfg.get('oci_vector_store_id')]
        if kind == 'ocr':
            identity += [cfg.get('ocr_model'), cfg.get('ocr_connection_profile_id'), cfg.get('ocr_connection_profile_version')]
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        destinations.append({'key':key, 'title':provider, 'description':text})
    if role == 'embedding' and cfg.get('storage_provider') == 'oci':
        add('storage', 'OCI Object Storage', 'Upload original documents to '+(cfg.get('oci_storage_bucket') or 'your configured OCI bucket')+'.')
    if role == 'embedding' and cfg.get('ocr_provider') in ('gemini','openai'):
        provider = 'OpenAI' if cfg['ocr_provider'] == 'openai' else 'Gemini'
        add('ocr', provider + ' OCR', 'Send scanned page images and embedded document images to the mapped '+provider+' extraction model for transcription.')
    if cfg.get('search_provider') in ('oci', 'oracle'):
        add('search', 'OCI knowledge store', 'Send query text, document content and metadata to the configured OCI search or vector service.')
    if cfg.get('embedding_provider') in ('openai', 'registered'):
        add('embedding', 'OpenAI embeddings' if cfg['embedding_provider']=='openai' else 'Configured embedding provider', 'Send query or document text to generate embeddings.')
    if role != 'embedding' and cfg.get('model_provider') in ('openai', 'oci', 'registered'):
        add('model', {'openai':'OpenAI', 'oci':'OCI model service'}.get(cfg['model_provider'], 'Configured model provider'), 'Send this request and selected document or result context to the configured model.')
    return destinations


def install(app, auth, main):
    @app.post('/api/agent-v2/consent')
    def preflight(body: ConsentScope, owner=Depends(auth)):
        dataset = routing.owned(body.dataset_id, owner, 'knowledge_base') if body.dataset_id else None
        result = {}
        for role in dict.fromkeys(body.roles):
            if dataset:
                snapshot = routing.execution_snapshot(dataset, role, body.planner_model_id if role=='chat' else None)
            elif role == 'chat':
                snapshot = chat_snapshot(owner, body.planner_model_id)
            else:
                model = routing.owned(body.model_ids.get(role, ''), owner, 'model')
                data = routing.model_public(model)
                if not data.get('enabled', True) or role not in data['capabilities']:
                    raise HTTPException(409, 'Choose an enabled model for '+role+'.')
                snapshot = routing.profile_snapshot(routing.owned(data['connection_profile_id'], model.owner, 'config_profile'), data.get('connection_profile_version'))
                # New datasets execute against current global storage/database,
                # while embedding and model choices come from the selected profile.
                cfg=core.settings().copy()
                keys=routing.EMBED_KEYS if role=='embedding' else routing.MODEL_KEYS
                cfg.update({key:snapshot['settings'][key] for key in keys if key in snapshot['settings']})
                transport=database_control.vector_backend()
                if transport:cfg['search_provider']=transport
                snapshot['settings']=cfg
            for notice in notices(snapshot, role, main):
                result[notice['key']] = notice
        return {'dataset_id':body.dataset_id, 'required':bool(result), 'destinations':list(result.values())}
