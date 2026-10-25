"""Administrator-published cloud copies use the existing dataset upload/index path.

No delegated-user ACL mirror, background sync or writes to the remote provider.
Credentials and continuation/selection capabilities never enter public metadata.
"""
import hashlib
import io
import json
import os
import re
import time
from typing import Literal

import anyio
from cryptography.fernet import InvalidToken
from fastapi import Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from . import core, dataset_access as access, dataset_models as routing, cloud_sources

ROOT = 'configuration/source-connections/'
KEYS = {'s3': {'access_key_id', 'secret_access_key', 'session_token'}, 'sharepoint': {'client_secret'}, 'google_drive': {'service_account'}}


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    provider: Literal['s3', 'sharepoint', 'google_drive']
    dataset_id: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    auth_mode: Literal['access_key', 'server_identity'] = 'access_key'
    bucket: str = Field(default='', max_length=63)
    region: str = Field(default='', max_length=64)
    prefix: str = Field(default='', max_length=1024)
    expected_owner: str = Field(default='', max_length=12)
    tenant_id: str = Field(default='', max_length=36)
    client_id: str = Field(default='', max_length=36)
    site_id: str = Field(default='', max_length=300)
    drive_id: str = Field(default='', max_length=200)
    folder_id: str = Field(default='', max_length=200)
    credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=3)

    @model_validator(mode='after')
    def location(self):
        if not self.name.strip():
            raise ValueError('Enter a connection name.')
        if any(k not in KEYS[self.provider] or len(v.get_secret_value()) > 32768 for k, v in self.credentials.items()):
            raise ValueError('Invalid credential fields.')
        if self.provider == 's3':
            if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket) or '..' in self.bucket or re.fullmatch(r'\d+\.\d+\.\d+\.\d+', self.bucket):
                raise ValueError('Enter a valid S3 general-purpose bucket name.')
            if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d+', self.region):
                raise ValueError('Enter an AWS region, for example ap-south-1.')
            if self.prefix and not self.prefix.endswith('/'):
                raise ValueError('Use a folder prefix ending in /, or leave it empty for the bucket root.')
            if self.expected_owner and not re.fullmatch(r'\d{12}', self.expected_owner):
                raise ValueError('Expected bucket owner must be a 12-digit AWS account ID.')
        elif self.provider == 'sharepoint':
            for value in (self.tenant_id, self.client_id):
                if not re.fullmatch(r'[a-fA-F0-9-]{36}', value):
                    raise ValueError('Enter the Entra tenant and application client UUIDs.')
            if not re.fullmatch(r'[A-Za-z0-9.,_-]+', self.site_id) or not re.fullmatch(r'[A-Za-z0-9!_-]+', self.drive_id):
                raise ValueError('Enter the SharePoint site ID and document-library drive ID, not URLs.')
            if self.folder_id and not re.fullmatch(r'[A-Za-z0-9!_-]+', self.folder_id):
                raise ValueError('Enter a valid SharePoint folder item ID, or leave it empty for the library root.')
        elif not re.fullmatch(r'[A-Za-z0-9_-]+', self.folder_id):
            raise ValueError('Enter a Google Drive folder ID shared with the service account.')
        return self


class ImportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[str] = Field(min_length=1, max_length=20)
    allow_external: bool = False
    publish_to_dataset: bool = False


def ref(identifier):
    if not re.fullmatch(r'[a-f0-9-]{16,64}', identifier):
        raise HTTPException(404, 'Source connection not found.')
    return ROOT + identifier + '.json'


def authorize(actor, dataset_id):
    access.require_admin(actor)
    dataset = access.get_record(dataset_id, actor, 'knowledge_base')
    if routing.dataset_config(dataset).get('active') is False:
        raise HTTPException(409, 'Activate the dataset before using its source connections.')
    return dataset


def load(identifier, actor):
    access.require_admin(actor)
    try:
        cfg = core.local_store.json(ref(identifier))
    except FileNotFoundError:
        raise HTTPException(404, 'Source connection not found.') from None
    authorize(actor, cfg['dataset_id'])
    return cfg


def public(cfg):
    return {key: value for key, value in cfg.items() if key != 'secret_ref'} | {'credentials_configured': bool(cfg.get('secret_ref'))}


def credentials(cfg):
    try:
        return json.loads(core.secret_cipher().decrypt(core.local_store.get(cfg['secret_ref']))) if cfg.get('secret_ref') else {}
    except (InvalidToken, ValueError, FileNotFoundError):
        raise HTTPException(409, 'Saved source credentials cannot be decrypted. Enter them again.') from None


def prepare(body, actor, previous=None):
    authorize(actor, body.dataset_id)
    cfg = body.model_dump(exclude={'credentials'})
    cfg['name'] = cfg['name'].strip()
    secret = {k: v.get_secret_value() for k, v in body.credentials.items() if v.get_secret_value()}
    same = previous and all(previous.get(k) == cfg.get(k) for k in ('provider', 'auth_mode', 'bucket', 'region', 'tenant_id', 'client_id', 'site_id', 'drive_id', 'folder_id', 'prefix', 'expected_owner', 'dataset_id'))
    if not secret and same:
        secret = credentials(previous)
    required = {'s3': ('access_key_id', 'secret_access_key') if body.auth_mode == 'access_key' else (), 'sharepoint': ('client_secret',), 'google_drive': ('service_account',)}[body.provider]
    if any(not secret.get(key) for key in required):
        raise HTTPException(422, 'Enter the required source credentials. Changed locations require credentials again.')
    if body.provider == 's3' and body.auth_mode == 'server_identity':
        secret = {}
    if body.provider == 'google_drive':
        try:
            info = json.loads(secret['service_account'])
            if info.get('type') != 'service_account' or not all(info.get(k) for k in ('client_email', 'private_key', 'token_uri')):
                raise ValueError()
            if info['token_uri'] != 'https://oauth2.googleapis.com/token' or info.get('universe_domain', 'googleapis.com') != 'googleapis.com':
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, 'Enter a Google service-account JSON key for googleapis.com. Delegated user credentials are not supported.') from None
    return cfg, secret


def remote(cfg, secret, operation):
    if os.getenv('AEGIS_LOCAL_ONLY') == 'true':
        raise HTTPException(409, 'Cloud connections are unavailable in local-only mode.')
    try:
        return operation(cloud_sources.adapter(cfg, secret))
    except cloud_sources.SourceError as error:
        raise HTTPException(400, str(error)) from None
    except Exception:
        # SDK/HTTP exception strings can contain signed URLs and credentials.
        raise HTTPException(502, 'Could not read the cloud source. Check credentials, location, read permissions and network access, then retry. If a file changed, refresh the list.') from None


def seal(cfg, actor, kind, value):
    data = {'connection': cfg['id'], 'version': cfg['version'], 'actor': actor, 'dataset': cfg['dataset_id'], 'kind': kind, 'value': value, 'expires': time.time() + 1800}
    return core.secret_cipher().encrypt(json.dumps(data).encode()).decode()


def unseal(token, cfg, actor, kind):
    try:
        value = json.loads(core.secret_cipher().decrypt(token.encode(), ttl=1800))
        if any(value.get(k) != expected for k, expected in {'connection': cfg['id'], 'version': cfg['version'], 'actor': actor, 'dataset': cfg['dataset_id'], 'kind': kind}.items()) or value['expires'] < time.time():
            raise ValueError()
        return value['value']
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(409, 'This source selection expired or the connection changed. Refresh the file list.') from None


def install(app, auth, api):
    @app.get('/api/source-connections')
    def listing(actor=Depends(auth)):
        access.require_admin(actor)
        values = []
        for path in core.local_store.path(ROOT + 'index').parent.glob('*.json'):
            cfg = core.local_store.json(ROOT + path.name)
            try:
                authorize(actor, cfg['dataset_id'])
            except HTTPException:
                continue
            values.append(public(cfg))
        return sorted(values, key=lambda c: c['name'].lower())

    @app.post('/api/source-connections/test')
    def test(body: ConnectionInput, connection_id: str = '', actor=Depends(auth)):
        previous = load(connection_id, actor) if connection_id else None
        cfg, secret = prepare(body, actor, previous)
        remote(cfg, secret, lambda adapter: adapter.browse())
        return {'ok': True, 'message': 'Read access verified for the configured location. No files imported or cloud data changed.'}

    def save(body, actor, previous=None):
        cfg, secret = prepare(body, actor, previous)
        identifier = previous['id'] if previous else core.uid()
        version = previous['version'] + 1 if previous else 1
        cfg.update(id=identifier, version=version, updated_at=time.time(), secret_ref='')
        try:
            # A master key is needed even with server identity for scoped selection tokens.
            cipher = core.secret_cipher()
            if secret:
                cfg['secret_ref'] = f'secrets/source-connections/{identifier}/v{version}.enc'
                core.local_store.put(cfg['secret_ref'], cipher.encrypt(json.dumps(secret).encode()))
        except ValueError:
            raise HTTPException(409, 'Configure the server master key before saving source connections.') from None
        core.local_store.put_json(ref(identifier), cfg)
        return public(cfg)

    @app.post('/api/source-connections')
    def create(body: ConnectionInput, actor=Depends(auth)):
        return save(body, actor)

    @app.put('/api/source-connections/{identifier}')
    def update(identifier: str, body: ConnectionInput, actor=Depends(auth)):
        ref(identifier)
        with core.document_lock('source-' + identifier):
            return save(body, actor, load(identifier, actor))

    @app.get('/api/source-connections/{identifier}/files')
    def files(identifier: str, folder: str = '', cursor: str = '', actor=Depends(auth)):
        cfg = load(identifier, actor)
        if not cfg['enabled']:
            raise HTTPException(409, 'Enable this connection before browsing or importing.')
        if len(folder) > 2048 or len(cursor) > 32768:
            raise HTTPException(422, 'Invalid source navigation.')
        continuation = unseal(cursor, cfg, actor, 'cursor') if cursor else None
        if continuation and continuation['folder'] != folder:
            raise HTTPException(409, 'Page cursor belongs to another folder.')
        items, next_page = remote(cfg, credentials(cfg), lambda adapter: adapter.browse(folder, continuation['cursor'] if continuation else ''))
        authorize(actor, cfg['dataset_id'])
        result = []
        for item in items:
            result.append(item | {'selection': seal(cfg, actor, 'file', item) if not item['folder'] and item.get('supported') else ''})
        return {'items': result, 'next_cursor': seal(cfg, actor, 'cursor', {'folder': folder, 'cursor': next_page}) if next_page else '', 'connection_version': cfg['version']}

    @app.post('/api/source-connections/{identifier}/import')
    async def import_files(identifier: str, body: ImportInput, actor=Depends(auth)):
        # The blocking provider reads and filesystem lock run in a worker thread.
        def run():
            ref(identifier)
            with core.document_lock('source-' + identifier):
                cfg = load(identifier, actor)
                if not cfg['enabled']:
                    raise HTTPException(409, 'This connection is disabled.')
                if not body.publish_to_dataset:
                    raise HTTPException(409, 'Confirm that imported copies may be read by authorized users of this dataset.')
                dataset = authorize(actor, cfg['dataset_id'])
                snapshot = routing.execution_snapshot(dataset, 'embedding')
                api.external_check(body.allow_external, True, snapshot['settings'])
                items = [unseal(token, cfg, actor, 'file') for token in body.selections]
                if len({item['id'] for item in items}) != len(items):
                    raise HTTPException(422, 'Select each cloud file once.')
                secret = credentials(cfg)
                results = []
                # A single authenticated adapter is reused for the selected batch.
                def batch(adapter):
                    for item in items:
                        try:
                            authorize(actor, cfg['dataset_id'])
                            name, raw, provenance = adapter.fetch(item, core.settings()['max_upload_mb'] * 1024 * 1024)
                            authorize(actor, cfg['dataset_id'])
                            if not cloud_sources.supported(name):
                                raise cloud_sources.SourceError('Only PDF, DOCX, TXT and JSON files can be imported.')
                            digest = hashlib.sha256(raw).hexdigest()
                            key = hashlib.sha256(json.dumps([cfg['id'], cfg['dataset_id'], item['id'], name, digest]).encode()).hexdigest()
                            generation_ref = ROOT + cfg['id'] + '/' + key + '.json'
                            try:
                                generation = core.local_store.json(generation_ref)['generation']
                            except FileNotFoundError:
                                generation = 0
                            # A user may remove an imported copy and later explicitly
                            # reimport it. Keep the old receipt; advance its generation.
                            receipt_key = 'cloud-' + key + '-' + str(generation)
                            receipt_ref = 'upload-receipts/' + hashlib.sha256(json.dumps([actor, receipt_key]).encode()).hexdigest() + '.json'
                            try:
                                previous = core.store.json(receipt_ref).get('response', {})
                                if previous.get('documents'):
                                    try:
                                        access.get_record(previous['documents'][0]['id'], actor, 'document')
                                    except HTTPException as error:
                                        if error.status_code != 404:
                                            raise
                                        generation += 1
                                        receipt_key = 'cloud-' + key + '-' + str(generation)
                            except FileNotFoundError:
                                pass
                            core.local_store.put_json(generation_ref, {'generation': generation})
                            # Existing upload receipts safely replay completed submissions.
                            response = anyio.from_thread.run(lambda: api.upload(files=[UploadFile(filename=name, file=io.BytesIO(raw))], kb_id='', dataset_id=cfg['dataset_id'], allow_external=body.allow_external, temporary_session_id='', owner=actor, merge_files=False, template_id='', display_name='', idempotency_key=receipt_key, merge_records=False))
                            document = response['documents'][0]
                            # A receipt can reference a copy explicitly removed by the user.
                            try:
                                access.get_record(document['id'], actor, 'document')
                            except HTTPException:
                                raise HTTPException(409, 'This imported copy was removed. Create a new connection to import it again.') from None
                            marker = 'configuration/source-provenance/' + document['id'] + '.json'
                            try:
                                core.local_store.json(marker)
                                status = 'already_imported'
                            except FileNotFoundError:
                                status = 'imported'
                            core.local_store.put_json(marker, provenance | {'provider': cfg['provider'], 'connection_id': cfg['id'], 'connection_name': cfg['name'], 'sha256': digest, 'imported_at': document['created_at']})
                            results.append({'name': name, 'status': status, 'document_id': document['id'], 'jobs': response['jobs']})
                        except HTTPException as error:
                            results.append({'name': item['name'], 'status': 'failed', 'message': error.detail})
                        except cloud_sources.SourceError as error:
                            results.append({'name': item['name'], 'status': 'failed', 'message': str(error)})
                        except Exception:
                            results.append({'name': item['name'], 'status': 'failed', 'message': 'Could not import this file. Refresh the list and check cloud read permissions, size and format before retrying.'})
                    return results
                remote(cfg, secret, batch)
                return {'results': results, 'dataset_id': cfg['dataset_id'], 'notice': 'Imported copies use dataset access. Later remote changes, deletions and source permissions are not automatically synchronized. New content revisions create separate copies; previous imports are retained.'}
        return await anyio.to_thread.run_sync(run)
