"""Dataset-owned model routing; SQL contains references, never configuration or secrets."""
import copy
import time
from fastapi import HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import core, providers

CAPABILITIES={'chat','extraction','embedding'}
ROUTING_DEFAULTS={'mappings':[], 'default_chat_model_id':None, 'default_extraction_model_id':None, 'embedding_model_id':None, 'index_generation':0}
MODEL_KEYS=('model_provider','model','model_connection','timeout','context_limit','max_output_tokens','extra_parameters','oci_region','oci_project_id','oci_auth_mode','oci_profile','oci_model')
EMBED_KEYS=('embedding_provider','embedding_model','embedding_connection','embedding_context_limit','embedding_extra_parameters','search_provider','oci_region','oci_project_id','oci_auth_mode','oci_profile','oci_vector_store_id','timeout','chunk_size','chunk_overlap','top_k')

def owned(id,owner,kind):
    with core.Session() as s:r=s.get(core.Record,id)
    if not r or r.owner!=owner or r.kind!=kind:raise HTTPException(404,'Not found')
    return r

def rows(owner,kind):
    with core.Session() as s:return list(s.scalars(select(core.Record).where(core.Record.owner==owner,core.Record.kind==kind).order_by(core.Record.created_at.desc())))

def write_version(record,data):
    version=record.version+1;ref=f'{record.kind}/{record.id}/v{version}.json'
    core.store.put_json(ref,data)
    with core.Session.begin() as s:
        r=s.get(core.Record,record.id);r.ref=ref;r.version=version;r.updated_at=time.time()
    return r

def create(kind,owner,name,data,parent=''):
    id=core.uid();ref=f'{kind}/{id}/v1.json';core.store.put_json(ref,data)
    r=core.Record(id=id,kind=kind,owner=owner,name=name,parent_id=parent,ref=ref,created_at=time.time(),updated_at=time.time())
    with core.Session.begin() as s:s.add(r)
    return r

def profile_snapshot(profile,version=None):
    version=version or profile.version
    ref=f'configuration/profiles/{profile.id}/v{version}.json' if version!=profile.version else profile.ref
    data=core.local_store.json(ref);cfg=data['settings']
    refs={}
    for provider,key,filename in [('openai','api_key_configured','openai.enc'),('oci','oci_api_key_configured','oci.enc'),('connection','connection_credentials_configured','connection.enc')]:
        refs[provider]=f'secrets/profiles/{profile.id}/v{version}/{filename}' if data.get(key) else None
    return {'settings':copy.deepcopy(cfg),'secret_refs':refs,'connection_profile_id':profile.id,'connection_profile_version':version}

def model_data(r):return core.store.json(r.ref)
def model_public(r):
    data=model_data(r);profile=owned(data['connection_profile_id'],r.owner,'config_profile');snap=profile_snapshot(profile,data.get('connection_profile_version'))
    p=snap['settings']['embedding_provider'] if data['capabilities']==['embedding'] else snap['settings']['model_provider']
    if data['capabilities']==['embedding'] and snap['settings']['search_provider']=='oci':p='oci'
    connection=snap['settings'].get('embedding_connection' if data['capabilities']==['embedding'] else 'model_connection')
    configured=(bool(snap['secret_refs'].get('connection')) or connection.get('auth_mode') in ('none','server_identity','config_profile')) if connection else p not in ('openai','oci') or bool(snap['secret_refs'].get(p)) or (p=='oci' and snap['settings'].get('oci_auth_mode')!='api_key')
    embedding=data['capabilities']==['embedding'];cfg=snap['settings']
    return core.representation(r)|data|{'provider':connection['protocol'] if connection else p,'connection_profile_version':snap['connection_profile_version'],'credential_configured':configured,'connection':copy.deepcopy(connection),'timeout':cfg.get('timeout',60),'context_limit':cfg.get('embedding_context_limit' if embedding else 'context_limit') or (8192 if embedding else 32768),'max_output_tokens':None if embedding else cfg.get('max_output_tokens') or 4096,'extra_parameters':copy.deepcopy(cfg.get('embedding_extra_parameters' if embedding else 'extra_parameters',{}))}

def dataset_config(r):return core.store.json(r.ref)
def routing_public(r):
    data=dataset_config(r);out=copy.deepcopy(ROUTING_DEFAULTS)|{k:data[k] for k in ROUTING_DEFAULTS if k in data};models=[]
    for mapping in out['mappings']:
        try:models.append(model_public(owned(mapping['model_id'],r.owner,'model'))|{'mapping_enabled':mapping['enabled']})
        except HTTPException:continue
    selection=public_selection(data['embedding_snapshot']|{'dataset_id':r.id,'index_generation':out['index_generation']}) if data.get('embedding_snapshot') else None
    complete=all(out.get(key) and any(m['id']==out[key] and m.get('enabled',True) and m.get('mapping_enabled',True) and cap in m['capabilities'] for m in models) for cap,key in [('embedding','embedding_model_id'),('chat','default_chat_model_id'),('extraction','default_extraction_model_id')])
    return out|{'dataset_id':r.id,'version':r.version,'models':models,'embedding_selection':selection,'models_complete':complete,'migration_required':'mappings' not in data}

def dataset_public(r):
    data=dataset_config(r)
    return core.representation(r)|{'name':r.name,'description':data.get('description',''),'active':data.get('active',True)}|routing_public(r)

def require_active(r):
    if not dataset_config(r).get('active',True):raise HTTPException(409,'Dataset is inactive. Activate it before starting new uploads, indexing, chat, or extraction.')

def resolve_model(r,capability,model_id=None):
    cfg=dataset_config(r);mappings=cfg.get('mappings',[])
    selected=model_id or cfg.get('default_'+capability+'_model_id')
    eligible=[]
    for mapping in mappings:
        if not mapping.get('enabled',True):continue
        try:model=owned(mapping['model_id'],r.owner,'model')
        except HTTPException:continue
        data=model_data(model)
        if data.get('enabled',True) and capability in data['capabilities']:eligible.append(model)
    if not selected:
        if len(eligible)!=1:raise HTTPException(409,'Map an enabled '+capability+' model and choose a default, or select one of the mapped models.')
        selected=eligible[0].id
    model=next((m for m in eligible if m.id==selected),None)
    if not model:raise HTTPException(409,'Selected model is not an enabled, capable mapping for this dataset.')
    data=model_data(model);profile=owned(data['connection_profile_id'],r.owner,'config_profile');snap=profile_snapshot(profile,data.get('connection_profile_version'))
    snap.update(model_id=model.id,model_name=model.name,model_version=model.version,provider_model=data['provider_model'],capability=capability)
    if capability=='embedding':
        snap['settings']['embedding_model']=data['provider_model']
    else:
        snap['settings']['model']=data['provider_model'];snap['settings']['oci_model']=data['provider_model']
        snap['settings'].setdefault('context_limit',32768)
        snap['settings'].setdefault('max_output_tokens',4096)
        snap['settings'].setdefault('extra_parameters',{})
    return snap

def embedding_snapshot(r):
    data=dataset_config(r);selected=data.get('embedding_model_id')
    if not selected or not data.get('embedding_snapshot'):raise HTTPException(409,'Map an embedding model for this dataset before indexing or asking questions.')
    # Enforce current ownership, enabled state and capability without changing the pinned space.
    current=resolve_model(r,'embedding',selected);snap=copy.deepcopy(data['embedding_snapshot'])
    if current['model_version']!=snap['model_version'] or current['connection_profile_version']!=snap['connection_profile_version']:raise HTTPException(409,'Embedding model configuration changed. Save the dataset model mapping and reindex documents.')
    cfg=core.settings().copy();cfg.update({k:snap['settings'][k] for k in EMBED_KEYS if k in snap['settings']})
    snap['settings']=cfg
    if cfg['embedding_provider']=='ollama':
        from .ollama_provider import model_digest,OllamaError
        try:
            with core.execution_context(snap):cfg['_embedding_digest']=model_digest(cfg['embedding_model'])
        except OllamaError as error:raise HTTPException(409,str(error))
    snap['settings']['_index_namespace']=r.id+':'+str(data['index_generation'])
    snap.update(dataset_id=r.id,index_generation=data['index_generation'])
    return snap

def execution_snapshot(r,capability,model_id=None):
    # Activity gates new work only; inspecting existing indexes must remain possible.
    require_active(r)
    if not routing_public(r)['models_complete']:raise HTTPException(409,'Model Mapping requires an enabled Embedding, Chat, and Extraction selection for this dataset before starting new work.')
    embedding=embedding_snapshot(r)
    if capability=='embedding':return embedding
    model=resolve_model(r,capability,model_id)
    # Runtime infrastructure is global, but routing/model/index settings and secrets are pinned.
    cfg=core.settings().copy()
    cfg.update({k:embedding['settings'][k] for k in EMBED_KEYS if k in embedding['settings']})
    cfg['_index_namespace']=embedding['settings']['_index_namespace']
    cfg.update({k:model['settings'][k] for k in MODEL_KEYS if k in model['settings']})
    # OCI model and OCI index may use independent projects/profiles. Preserve both contexts.
    model['settings']=cfg;model['embedding_execution']=embedding
    model.update(dataset_id=r.id,index_generation=embedding['index_generation'])
    return model

def public_selection(snapshot):
    selected={k:snapshot.get(k) for k in ('model_id','model_name','model_version','provider_model','connection_profile_id','connection_profile_version','dataset_id','index_generation')}
    cfg=snapshot.get('settings',{})
    return selected|{k:cfg.get(k) for k in ('model_provider','embedding_provider','search_provider','context_limit','max_output_tokens','extra_parameters','embedding_context_limit','embedding_extra_parameters')}

def documents_scope(owner,dataset_id,ids=None):
    docs=[owned(id,owner,'document') for id in ids] if ids else []
    if not dataset_id:
        parents={d.parent_id for d in docs}
        if len(parents)==1 and '' not in parents:dataset_id=next(iter(parents))
        else:raise HTTPException(400,'Choose one dataset. Existing unassigned documents must be assigned to a dataset first.')
    r=owned(dataset_id,owner,'knowledge_base')
    if any(d.parent_id!=r.id for d in docs):raise HTTPException(400,'All selected documents must belong to the selected dataset.')
    if not ids:docs=[d for d in rows(owner,'document') if d.parent_id==r.id]
    return r,docs

def index_matches(d,snapshot):
    try:index=core.store.json('documents/'+d.id+'/index.json')
    except FileNotFoundError:return False
    return index.get('dataset_id')==snapshot['dataset_id'] and index.get('index_generation')==snapshot['index_generation'] and index.get('fingerprint')==providers.fingerprint(snapshot.get('embedding_execution',snapshot)['settings'])

def require_indexes(docs,snapshot):
    if any(d.status=='ready' and not index_matches(d,snapshot) for d in docs):raise HTTPException(409,'Dataset index configuration changed. Reindex the selected documents before retrieval or extraction.')

def document_public(d,snapshots=None):
    result=core.representation(d)|{'dataset_id':d.parent_id or None,'requires_reindex':True}
    from .temporary_files import marker
    result.update(marker(d.id))
    if not d.parent_id:return result
    try:
        # Share snapshots only within this listing request. Recheck the live
        # model digest on every new request and before executing any work.
        key=(d.owner,d.parent_id)
        if snapshots is None:snapshot=embedding_snapshot(owned(d.parent_id,d.owner,'knowledge_base'))
        else:
            if key not in snapshots:
                try:snapshots[key]=embedding_snapshot(owned(d.parent_id,d.owner,'knowledge_base'))
                except HTTPException as error:snapshots[key]=error
            snapshot=snapshots[key]
            if isinstance(snapshot,HTTPException):raise snapshot
        result['requires_reindex']=not index_matches(d,snapshot)
    except HTTPException:pass
    if result['requires_reindex'] and d.status=='ready':result['index_notice']='Reindex required: embedding configuration or installed model digest differs, or this older index has no verified model digest. Original retained.'
    return result

class ModelInput(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    connection_profile_id:str
    provider_model:str=Field(min_length=1,max_length=200)
    capabilities:list[str]=Field(min_length=1,max_length=3)
    enabled:bool=True
class Mapping(BaseModel):model_id:str;enabled:bool=True
class MappingInput(BaseModel):
    mappings:list[Mapping]=Field(default_factory=list,max_length=100)
    default_chat_model_id:str|None=None
    default_extraction_model_id:str|None=None
    embedding_model_id:str|None=None
    expected_version:int|None=None
    acknowledge_reindex:bool=False
class DatasetInput(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    description:str=Field(default='',max_length=10000)
    active:bool=Field(default=True,strict=True)
class DatasetStatusInput(BaseModel):active:bool=Field(strict=True)
class AssignInput(BaseModel):document_ids:list[str]=Field(min_length=1,max_length=100)

def validate_model(body,owner):
    data=body.model_dump();data['capabilities']=sorted(set(data['capabilities']))
    if set(data['capabilities'])-CAPABILITIES or ('embedding' in data['capabilities'] and len(data['capabilities'])>1):raise HTTPException(400,'Use chat/extraction capabilities together, or a separate embedding model.')
    profile=owned(body.connection_profile_id,owner,'config_profile');cfg=profile_snapshot(profile)['settings']
    if core.local_store.json(profile.ref).get('registration_model_id'):raise HTTPException(400,'Edit or register this model through Model Registration.')
    p=cfg['embedding_provider'] if data['capabilities']==['embedding'] else cfg['model_provider']
    if p=='mock' and __import__('os').getenv('AEGIS_ALLOW_MOCK')!='true':raise HTTPException(400,'Mock providers require AEGIS_ALLOW_MOCK=true')
    if p=='sentence_transformers' and body.provider_model!='sentence-transformers/all-MiniLM-L6-v2':raise HTTPException(400,'Local embeddings currently support sentence-transformers/all-MiniLM-L6-v2 only.')
    if p=='ollama':
        from .ollama_provider import local_model_name,OllamaError
        try:local_model_name(body.provider_model)
        except OllamaError as exc:raise HTTPException(400,str(exc))
    return data

def save_mappings(r,body):
    if body.expected_version is not None and body.expected_version!=r.version:raise HTTPException(409,'Dataset mappings changed. Refresh and review the saved mappings before applying your draft.')
    values=body.model_dump(exclude={'expected_version','acknowledge_reindex'});ids=[m['model_id'] for m in values['mappings']]
    if len(ids)!=len(set(ids)):raise HTTPException(400,'Each model can be mapped only once.')
    for id in ids:owned(id,r.owner,'model')
    data=dataset_config(r)|values
    # Validate against the proposed mapping without publishing it first.
    eligible={}
    for m in values['mappings']:
        model=owned(m['model_id'],r.owner,'model');md=model_data(model)
        if m['enabled'] and md['enabled']:eligible[model.id]=md
    for capability,key in [('chat','default_chat_model_id'),('extraction','default_extraction_model_id'),('embedding','embedding_model_id')]:
        id=values[key]
        if not id:raise HTTPException(400,'Embedding, Chat, and Extraction model selections are all required.')
        if id and (id not in eligible or capability not in eligible[id]['capabilities']):raise HTTPException(400,'The '+capability+' default must be an enabled mapped model with that capability.')
        selected=owned(id,r.owner,'model');md=model_data(selected);cfg=profile_snapshot(owned(md['connection_profile_id'],r.owner,'config_profile'),md.get('connection_profile_version'))['settings']
        if capability=='embedding' and cfg.get('embedding_connection') and cfg['search_provider']=='oci':raise HTTPException(400,'Registered embedding connections require Local or Qdrant vector storage. OCI managed retrieval owns its embedding configuration.')
        try:core.enforce_local_only(cfg)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    old=dataset_config(r);embedding=None
    if values['embedding_model_id']:
        model=owned(values['embedding_model_id'],r.owner,'model');md=model_data(model);embedding=profile_snapshot(owned(md['connection_profile_id'],r.owner,'config_profile'),md.get('connection_profile_version'))
        embedding.update(model_id=model.id,model_name=model.name,model_version=model.version,provider_model=md['provider_model'],capability='embedding')
        embedding['settings']['embedding_model']=md['provider_model']
    data['embedding_snapshot']=embedding
    # A different pinned profile version is a deliberate new generation, even if only credentials changed.
    changed=old.get('embedding_snapshot')!=embedding
    if changed and old.get('embedding_snapshot') and not body.acknowledge_reindex and any(d.parent_id==r.id for d in rows(r.owner,'document')):raise HTTPException(400,'Acknowledge reindexing existing documents before applying an embedding change.')
    data['index_generation']=old.get('index_generation',0)+(1 if changed else 0)
    if not data['index_generation'] and embedding:data['index_generation']=1
    data['routing_version']=1
    return write_version(r,data)

def install_routes(app,auth,write_profile):
    @app.get('/api/models')
    def models(owner=Depends(auth)):return [model_public(r) for r in rows(owner,'model')]
    @app.post('/api/models')
    def add_model(body:ModelInput,owner=Depends(auth)):
        data=validate_model(body,owner);return model_public(create('model',owner,body.name,data))
    @app.put('/api/models/{id}')
    def update_model(id:str,body:ModelInput,owner=Depends(auth)):
        data=validate_model(body,owner)
        with core.document_lock('model-'+id):
            r=owned(id,owner,'model');r=write_version(r,data)
            with core.Session.begin() as s:s.get(core.Record,id).name=body.name
            r.name=body.name;return model_public(r)
    @app.get('/api/datasets')
    def datasets(owner=Depends(auth)):return [dataset_public(r) for r in rows(owner,'knowledge_base')]
    @app.post('/api/datasets')
    def add_dataset(body:DatasetInput,owner=Depends(auth)):
        return dataset_public(create('knowledge_base',owner,body.name,body.model_dump()|copy.deepcopy(ROUTING_DEFAULTS)|{'routing_version':1}))
    @app.get('/api/datasets/{id}')
    def dataset(id:str,owner=Depends(auth)):return dataset_public(owned(id,owner,'knowledge_base'))
    @app.patch('/api/datasets/{id}/status')
    def dataset_status(id:str,body:DatasetStatusInput,owner=Depends(auth)):
        with core.document_lock('dataset-'+id):
            r=owned(id,owner,'knowledge_base')
            return dataset_public(write_version(r,dataset_config(r)|{'active':body.active}))
    @app.get('/api/datasets/{id}/models')
    def mappings(id:str,owner=Depends(auth)):return routing_public(owned(id,owner,'knowledge_base'))
    @app.put('/api/datasets/{id}/models')
    def put_mappings(id:str,body:MappingInput,owner=Depends(auth)):
        with core.document_lock('dataset-'+id):return routing_public(save_mappings(owned(id,owner,'knowledge_base'),body))
    @app.post('/api/datasets/{id}/migrate-settings')
    def migrate(id:str,owner=Depends(auth)):
        with core.document_lock('dataset-'+id):
            r=owned(id,owner,'knowledge_base')
            if dataset_config(r).get('mappings'):raise HTTPException(409,'Dataset already has model mappings; update them explicitly.')
            profile=write_profile(owner,r.name+' imported connection');cfg=core.settings()
            generation=cfg.get('oci_model') if cfg['model_provider']=='oci' else cfg['model']
            generation=generation or 'mock-generation'
            embedding='sentence-transformers/all-MiniLM-L6-v2' if cfg['embedding_provider']=='sentence_transformers' else cfg['embedding_model']
            shared={'connection_profile_id':profile['id'],'enabled':True}
            gen=create('model',owner,r.name+' model',shared|{'name':r.name+' model','provider_model':generation,'capabilities':['chat','extraction']})
            emb=create('model',owner,r.name+' embeddings',shared|{'name':r.name+' embeddings','provider_model':embedding,'capabilities':['embedding']})
            r=save_mappings(r,MappingInput(mappings=[Mapping(model_id=gen.id),Mapping(model_id=emb.id)],default_chat_model_id=gen.id,default_extraction_model_id=gen.id,embedding_model_id=emb.id))
            return dataset_public(r)
    @app.post('/api/datasets/{id}/assign-documents')
    def assign(id:str,body:AssignInput,owner=Depends(auth)):
        owned(id,owner,'knowledge_base');docs=[owned(did,owner,'document') for did in body.document_ids]
        if any(d.parent_id and d.parent_id!=id for d in docs):raise HTTPException(400,'Only unassigned legacy documents can be assigned; moving existing datasets is unsupported.')
        with core.Session.begin() as s:
            if s.scalar(select(core.Job).where(core.Job.target_id.in_(body.document_ids),core.Job.status.in_(['queued','running']))):raise HTTPException(409,'Wait for or cancel active jobs before assigning documents.')
            for d in docs:s.get(core.Record,d.id).parent_id=id
        return {'assigned':len(docs),'requires_reindex':True,'dataset_id':id}
