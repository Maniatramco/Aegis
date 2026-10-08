"""Generic model registration; immutable connection versions, encrypted secrets."""
import copy
import json
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, SecretStr
from . import core, dataset_models as routing, providers
from .model_connections import ConnectionError, ModelConnection, validate_connection, validate_credentials
from .model_parameters import validate_parameters


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    protocol: Literal['ollama', 'openai-compatible', 'azure-openai', 'bedrock', 'vertex', 'oci']
    endpoint: str = Field(min_length=1, max_length=500)
    auth_mode: str = Field(max_length=40)
    region: str = Field(default='', max_length=64)
    project_id: str = Field(default='', max_length=128)
    compartment_id: str = Field(default='', max_length=200)
    profile: str = Field(default='DEFAULT', max_length=80)
    embedding_format: str = Field(default='titan', max_length=30)
    chat_format: str = Field(default='generic', max_length=30)
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    structured_output: bool = True


class RegistrationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    category: Literal['embedding', 'chat', 'extraction']
    provider_model: str = Field(min_length=1, max_length=200)
    connection: ConnectionInput
    timeout: int = Field(default=60, ge=5, le=600)
    context_limit: int | None = Field(default=None, ge=1, le=2097152, strict=True)
    max_output_tokens: int | None = Field(default=None, ge=1, le=131072, strict=True)
    extra_parameters: dict | None = None
    enabled: bool = True
    credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=12)
    clear_credentials: bool = False
    existing_model_id: str | None = None
    allow_external: bool = False


def previous(r):
    md = routing.model_data(r)
    profile = routing.owned(md['connection_profile_id'], r.owner, 'config_profile')
    snapshot = routing.profile_snapshot(profile, md.get('connection_profile_version'))
    cfg = snapshot['settings']
    return md, profile, snapshot, cfg.get('embedding_connection' if md['capabilities'] == ['embedding'] else 'model_connection')


def prepare(body, owner, existing=None):
    if not body.name.strip():
        raise HTTPException(400, 'Enter a model name.')
    try:
        c = validate_connection(body.connection.model_dump(), body.category, body.provider_model.strip())
        secret = {key: value.get_secret_value() for key, value in body.credentials.items()}
        if any(len(value) > 32768 for value in secret.values()):
            raise ConnectionError('Credential values are too large.')
        md = None
        if existing:
            md, profile, snapshot, old = previous(existing)
            if body.category not in md['capabilities']:
                raise ConnectionError('A registered model category cannot change. Register another model for the new category.')
            unchanged_destination = old and all(old.get(k) == c.get(k) for k in ('protocol', 'auth_mode', 'endpoint'))
            # Never reuse a saved key for a different endpoint or protocol implicitly.
            if not secret and not body.clear_credentials and unchanged_destination:
                ref = snapshot['secret_refs'].get('connection')
                if ref:
                    secret = json.loads(core.secret_cipher().decrypt(core.local_store.get(ref)).decode())
        if body.clear_credentials:
            secret = {}
        if body.enabled or secret:validate_credentials(c, secret)
        cfg = copy.deepcopy(core.settings())
        role = 'embedding' if body.category == 'embedding' else 'model'
        cfg[role + '_provider'] = 'ollama' if c['protocol'] == 'ollama' else 'registered'
        cfg['embedding_model' if role == 'embedding' else 'model'] = body.provider_model.strip()
        cfg[role + '_connection'] = c
        cfg['timeout'] = body.timeout
        old_cfg = snapshot['settings'] if existing else {}
        context_key = 'embedding_context_limit' if role == 'embedding' else 'context_limit'
        extra_key = 'embedding_extra_parameters' if role == 'embedding' else 'extra_parameters'
        cfg[context_key] = body.context_limit if body.context_limit is not None else old_cfg.get(context_key) or (8192 if role == 'embedding' else 32768)
        params = body.extra_parameters if body.extra_parameters is not None else old_cfg.get(extra_key, {})
        try:
            cfg[extra_key] = validate_parameters(params, c['protocol'], body.category, c)
        except ValueError as exc:
            raise ConnectionError(str(exc)) from exc
        if role == 'embedding':
            if body.max_output_tokens is not None:
                raise ConnectionError('Embedding models return vectors; output tokens apply only to Chat and Extraction.')
        else:
            cfg['max_output_tokens'] = body.max_output_tokens if body.max_output_tokens is not None else old_cfg.get('max_output_tokens') or 4096
            if cfg['max_output_tokens'] + 512 >= cfg['context_limit']:
                raise ConnectionError('Context tokens must exceed maximum output tokens plus 512 tokens of headroom.')
        return cfg, secret, (md['capabilities'] if md else [body.category])
    except ConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, 'Saved credentials cannot be decrypted. Enter the credentials again.')


def save(body, owner, existing=None):
    cfg, secret, capabilities = prepare(body, owner, existing)
    model_id = existing.id if existing else core.uid()
    profile = previous(existing)[1] if existing and previous(existing)[3] else None
    profile_id = profile.id if profile else core.uid()
    version = profile.version + 1 if profile else 1
    ref = f'configuration/profiles/{profile_id}/v{version}.json'
    data = {'settings': cfg, 'api_key_configured': False, 'oci_api_key_configured': False,
        'connection_credentials_configured': bool(secret), 'saved_at': time.time(), 'registration_model_id': model_id}
    if secret:
        try:
            encrypted = core.secret_cipher().encrypt(json.dumps(secret).encode())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        core.local_store.put(f'secrets/profiles/{profile_id}/v{version}/connection.enc', encrypted)
    core.local_store.put_json(ref, data)
    model_version = existing.version + 1 if existing else 1
    model_ref = f'model/{model_id}/v{model_version}.json'
    core.store.put_json(model_ref, {'name': body.name.strip(), 'provider_model': body.provider_model.strip(),
        'connection_profile_id': profile_id, 'connection_profile_version': version, 'capabilities': capabilities, 'enabled': body.enabled})
    now = time.time()
    with core.Session.begin() as session:
        if profile:
            p = session.get(core.Record, profile.id)
            p.version = version; p.ref = ref; p.updated_at = now
        else:
            session.add(core.Record(id=profile_id, kind='config_profile', owner=owner, name=body.name.strip()+' connection', ref=ref, created_at=now, updated_at=now))
        if existing:
            r = session.get(core.Record, model_id)
            r.name = body.name.strip(); r.ref = model_ref; r.version = model_version; r.updated_at = now
        else:
            r = core.Record(id=model_id, kind='model', owner=owner, name=body.name.strip(), ref=model_ref, created_at=now, updated_at=now)
            session.add(r)
    return routing.model_public(r)


def install_routes(app, auth):
    @app.post('/api/model-registrations')
    def register(body: RegistrationInput, owner=Depends(auth)):
        with core.document_lock('model-registration-'+owner):
            return save(body, owner)

    @app.put('/api/model-registrations/{id}')
    def revise(id: str, body: RegistrationInput, owner=Depends(auth)):
        with core.document_lock('model-registration-'+owner):
            with core.document_lock('model-'+id):
                return save(body, owner, routing.owned(id, owner, 'model'))

    @app.post('/api/model-registrations/test')
    def test(body: RegistrationInput, owner=Depends(auth)):
        existing = routing.owned(body.existing_model_id, owner, 'model') if body.existing_model_id else None
        cfg, secret, capabilities = prepare(body, owner, existing)
        if body.connection.protocol != 'ollama' and not body.allow_external:
            raise HTTPException(400, 'Allow the synthetic test request to be sent to this external model first.')
        try:
            core.enforce_local_only(cfg)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        # The probe uses the same adapter and validation as execution. No document data
        # or test credentials are persisted, and the configured timeout remains bounded.
        started = time.monotonic()
        snapshot = {'settings': cfg, 'secret_refs': {}, 'capability': body.category}
        with core.execution_context(snapshot):
            try:
                if body.connection.protocol == 'ollama':
                    from .ollama_provider import embed, chat, extract
                    if body.category == 'embedding':
                        vectors = embed(body.provider_model, ['Aegis connection test.'], body.timeout)
                        result = {'dimensions': len(vectors[0])}
                    elif body.category == 'extraction':
                        extract(body.provider_model, 'Return the word ready.', {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status'], 'additionalProperties': False}, body.timeout)
                        result = {'schema_validated': True}
                    else:
                        chat(body.provider_model, 'What is the status?', [{'document_name': 'Connection test', 'text': 'The status is ready.'}], [], body.timeout)
                        result = {'response_received': True}
                else:
                    adapter = ModelConnection(cfg, embedding=body.category=='embedding', credentials_override=secret)
                    if body.category == 'embedding':
                        vectors = adapter.embed(['Aegis connection test.'])
                        result = {'dimensions': len(vectors[0])}
                    elif body.category == 'extraction':
                        adapter.generate('Return JSON.', 'The status is ready.', {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status'], 'additionalProperties': False})
                        result = {'schema_validated': True}
                    else:
                        adapter.generate('Give a brief answer.', 'Say ready.')
                        result = {'response_received': True}
                return {'ok': True, 'category': body.category, 'elapsed_ms': round((time.monotonic()-started)*1000), **result}
            except (ConnectionError, providers.ProviderError) as exc:
                raise HTTPException(400, str(exc)) from exc
            except Exception:
                raise HTTPException(400, 'Connection test failed. Check the endpoint, model, credentials, and service availability.')
