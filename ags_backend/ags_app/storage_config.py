"""Admin storage destinations. New objects are pinned; switching never migrates files."""
import hashlib
import os
from pathlib import Path
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from . import core, dataset_access as access

CONTROL = ('configuration/', 'secrets/', 'diagnostics/', 'model/', 'models/', 'locks/', 'workspace-archives/', 'storage-routes/', 'object-cache/')
FIELDS = ('storage_provider','local_storage_path','oci_storage_namespace','oci_storage_bucket','oci_storage_prefix',
          'oci_storage_region','oci_storage_auth_mode','oci_storage_profile','oci_storage_config_file','oci_storage_key_file')
ENTITIES={'documents','extraction','knowledge_base','template','conversation','agent_plan','agent_onboarding','agent-state','jobs','temporary_session','temporary_document'}

def active():
    try: cfg=core.DEFAULTS|core.local_store.json('configuration/settings.json')
    except FileNotFoundError: cfg=core.DEFAULTS.copy()
    result={k:cfg.get(k,'') for k in FIELDS}
    for key in ('oci_storage_namespace','oci_storage_bucket','oci_storage_region'):
        if not result[key]:result[key]=core.DEFAULTS.get(key,'')
    return result

def connection_summary():
    """Display active destinations only; never return drafts or credentials."""
    from .database_control import state
    files=active();database=state();cfg=core.settings()
    remote=database.get('active_provider')=='oci'
    connection=database.get('active_connection',{}) if remote else {}
    search=cfg.get('search_provider','local')
    return {
        'files':{'provider':files['storage_provider'],
            'name':files.get('oci_storage_bucket','') if files['storage_provider']=='oci' else 'Laptop',
            'region':files.get('oci_storage_region','') if files['storage_provider']=='oci' else ''},
        'database':{'provider':'oci' if remote else 'local',
            'name':connection.get('name','Oracle') if remote else 'Laptop',
            'region':connection.get('region','')},
        'knowledge':{'provider':'oci' if search in ('oracle','oci') else 'local',
            'name':{'oracle':'Oracle vectors','oci':'OCI Search','qdrant':'Qdrant','local':'Local index'}.get(search,search)},
    }

def route_ref(key):return 'storage-routes/'+hashlib.sha256(key.encode()).hexdigest()+'.json'

def route(key, create=False):
    if key.startswith(CONTROL):return {'storage_provider':'local','local_storage_path':str(core.DATA)}
    try:return core.local_store.json(route_ref(key))['destination']
    except FileNotFoundError:pass
    parts=key.split('/')
    entity='/'.join(parts[:2]) if len(parts)>2 and parts[0] in ENTITIES else None
    destination=None
    if entity:
        try:destination=core.local_store.json(route_ref(entity))['destination']
        except FileNotFoundError:pass
        # Objects written before entity markers were introduced still anchor
        # later derived files and revisions to their original destination.
        if destination is None:
            for suffix in ('original', 'v1.json', 'workflow.json'):
                try:destination=core.local_store.json(route_ref(entity+'/'+suffix))['destination'];break
                except FileNotFoundError:pass
    # Legacy local objects keep their original location after a provider switch.
    if destination is None and (core.local_store.path(key).is_file() or entity and core.local_store.path(entity).is_dir()):
        destination={'storage_provider':'local','local_storage_path':str(core.DATA)}
    if destination is None:destination=active()
    if create:
        core.local_store.put_json(route_ref(key),{'key':key,'destination':destination})
        if entity:core.local_store.put_json(route_ref(entity),{'key':entity,'destination':destination})
    return destination

class DirectoryStorage(core.FileStorage):
    def __init__(self,root):self.root=Path(root or core.DATA).resolve()
    def path(self,key):
        target=(self.root/key).resolve()
        if self.root not in target.parents:raise ValueError('Invalid storage key')
        return target

def backend(key,create=False):
    destination=route(key,create)
    if destination['storage_provider']!='oci':return DirectoryStorage(destination.get('local_storage_path'))
    from .object_cache import CachedObjects,eligible
    return CachedObjects(lambda:core.oci_storage(destination),destination) if eligible(key) else core.oci_storage(destination)

def validate(cfg):
    core.enforce_local_only(core.settings()|cfg)
    if cfg['storage_provider']=='local':
        target=Path(cfg.get('local_storage_path') or core.DATA).resolve()
        if target!=core.DATA and core.DATA not in target.parents:raise ValueError('Local directory must be inside the mounted storage root '+str(core.DATA))
        return
    if not cfg['oci_storage_namespace'] or not cfg['oci_storage_bucket'] or not cfg['oci_storage_region']:
        raise ValueError('Enter namespace, bucket and region.')
    from .oci_adapters import _key
    if cfg['oci_storage_prefix']:_key(cfg['oci_storage_prefix'])
    if cfg['oci_storage_auth_mode']=='config_file':
        for field in ('oci_storage_config_file','oci_storage_key_file'):
            value=cfg.get(field)
            if field=='oci_storage_config_file' and not value:raise ValueError('Enter the mounted OCI config path.')
            if value:
                target=Path(value).resolve()
                approved=[Path('/run/oci').resolve(),(core.DATA/'oci').resolve()]
                if not any(root in target.parents for root in approved):raise ValueError('Credential paths must be under /run/oci or the mounted storage root/oci directory.')
                if not target.is_file():raise ValueError('Mounted credential file is unavailable: '+field)

def test(cfg):
    try:
        validate(cfg)
        if cfg['storage_provider']=='oci':
            value=core.oci_storage(cfg).test_connection()
            return dict(value,provider='oci',message='Bucket read access verified. Write access is checked when a new file is saved.')
        root=Path(cfg.get('local_storage_path') or core.DATA).resolve()
        root.mkdir(parents=True,exist_ok=True)
        if not os.access(root,os.R_OK|os.W_OK):raise ValueError('Local directory is not readable and writable.')
        return {'ok':True,'provider':'local','message':'Local directory is readable and writable.'}
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else 'OCI connection failed. Check mounted configuration, region and bucket permissions.'
        raise HTTPException(400,message) from None

class Destination(BaseModel):
    model_config=ConfigDict(extra='forbid')
    storage_provider:Literal['local','oci']='local'
    local_storage_path:str=''
    oci_storage_namespace:str=''
    oci_storage_bucket:str=''
    oci_storage_prefix:str='aegis'
    oci_storage_region:str=''
    oci_storage_auth_mode:Literal['config_file','instance_principal','resource_principal']='config_file'
    oci_storage_profile:str='DEFAULT'
    oci_storage_config_file:str='/run/oci/config'
    oci_storage_key_file:str='/run/oci/aegis_api_key.pem'

def install(app,auth):
    @app.get('/api/storage/status')
    def status(actor=Depends(auth)):
        return connection_summary()
    @app.get('/api/storage')
    def current(actor=Depends(auth)):
        access.require_admin(actor)
        return dict(destination=active(),local_root=str(core.DATA),
            credential_mount='/run/oci',credentials_mounted=Path('/run/oci/config').is_file(),
            note='Applies to new objects. Existing files keep their saved destination; no automatic migration.')
    @app.post('/api/storage/test')
    def probe(body:Destination,actor=Depends(auth)):
        access.require_admin(actor);return test(body.model_dump())
    @app.put('/api/storage')
    def save(body:Destination,actor=Depends(auth)):
        access.require_admin(actor)
        with core.document_lock('settings-config'):
            from sqlalchemy import select
            with core.Session() as session:
                if session.scalar(select(core.Job.id).where(core.Job.status.in_(['queued','running'])).limit(1)):
                    raise HTTPException(409,'Wait for processing jobs to finish before changing storage.')
            cfg=body.model_dump();receipt=test(cfg)
            try:existing=core.local_store.json('configuration/settings.json')
            except FileNotFoundError:existing={}
            core.local_store.put_json('configuration/settings.json',existing|cfg)
        return dict(destination=active(),test=receipt)
