"""Storage-first control plane. Only references and operational metadata enter SQL."""
import os, json, uuid, hashlib, secrets, time
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from sqlalchemy import create_engine, String, Integer, Float, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from cryptography.fernet import Fernet

DATA = Path(os.getenv('AEGIS_STORAGE_ROOT', os.getenv('DATA_DIR', './data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
URL = os.getenv('DATABASE_URL', 'sqlite:///' + str(DATA / 'control.db'))
engine = create_engine(URL, pool_pre_ping=True, connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Record(Base):
    __tablename__='records'
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    kind:Mapped[str]=mapped_column(String(32),index=True)
    owner:Mapped[str]=mapped_column(String(80),index=True)
    name:Mapped[str]=mapped_column(String(250),default='')
    status:Mapped[str]=mapped_column(String(32),default='ready')
    ref:Mapped[str]=mapped_column(String(500),default='')
    parent_id:Mapped[str]=mapped_column(String(80),default='',index=True)
    created_at:Mapped[float]=mapped_column(Float,default=time.time)
    updated_at:Mapped[float]=mapped_column(Float,default=time.time)
    size:Mapped[int]=mapped_column(Integer,default=0)
    version:Mapped[int]=mapped_column(Integer,default=1)
    error:Mapped[str]=mapped_column(String(500),default='')
class Job(Base):
    __tablename__='jobs'
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    owner:Mapped[str]=mapped_column(String(80),index=True)
    kind:Mapped[str]=mapped_column(String(32))
    target_id:Mapped[str]=mapped_column(String(80),index=True)
    status:Mapped[str]=mapped_column(String(32),default='queued',index=True)
    progress:Mapped[int]=mapped_column(Integer,default=0)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    lease_until:Mapped[float]=mapped_column(Float,default=0)
    lease_token:Mapped[str]=mapped_column(String(80),default='')
    error:Mapped[str]=mapped_column(String(500),default='')
    created_at:Mapped[float]=mapped_column(Float,default=time.time)
    updated_at:Mapped[float]=mapped_column(Float,default=time.time)
class User(Base):
    __tablename__='users'
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    username:Mapped[str]=mapped_column(String(120),unique=True)
    password_hash:Mapped[str]=mapped_column(Text)
class Login(Base):
    __tablename__='sessions'
    id:Mapped[str]=mapped_column(String(100),primary_key=True)
    owner:Mapped[str]=mapped_column(String(80))
    expires:Mapped[float]=mapped_column(Float)
    csrf:Mapped[str]=mapped_column(String(100))

class FileStorage:
    def path(self,key):
        p=(DATA/key).resolve()
        if DATA not in p.parents: raise ValueError('Invalid storage key')
        return p
    def put(self,key,data):
        p=self.path(key);p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_name(p.name+'.'+secrets.token_hex(8)+'.tmp');tmp.write_bytes(data);os.chmod(tmp,0o600);os.replace(tmp,p)
    def get(self,key): return self.path(key).read_bytes()
    def json(self,key): return json.loads(self.get(key))
    def put_json(self,key,data): self.put(key,json.dumps(data,ensure_ascii=False).encode())
    def delete(self,key): self.path(key).unlink(missing_ok=True)
local_store=FileStorage()
class RoutingStorage:
    def backend(self,key):
        if key.startswith(('configuration/','secrets/','diagnostics/')):return local_store
        try:cfg=local_store.json('configuration/settings.json')
        except FileNotFoundError:cfg={}
        provider=cfg.get('storage_provider',os.getenv('STORAGE_PROVIDER','local'))
        if provider=='oci':
            from .oci_adapters import OCIStorageAdapter
            return oci_storage(cfg)
        if provider!='local':raise ValueError('Unsupported storage provider')
        return local_store
    def put(self,key,data):return self.backend(key).put(key,data)
    def get(self,key):return self.backend(key).get(key)
    def json(self,key):return json.loads(self.get(key))
    def put_json(self,key,data):return self.put(key,json.dumps(data,ensure_ascii=False).encode())
    def delete(self,key):return self.backend(key).delete(key)
store=RoutingStorage()
def uid(): return str(uuid.uuid4())
def password_hash(value,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def password_valid(value,hashed): return secrets.compare_digest(password_hash(value,hashed.split(':')[0]),hashed)
def init():
    if URL.startswith('postgresql'):
        from sqlalchemy import text
        with engine.begin() as connection:
            connection.execute(text('SELECT pg_advisory_xact_lock(741936)'))
            Base.metadata.create_all(connection)
    else:Base.metadata.create_all(engine)
def secret_cipher():
    key=os.getenv('AEGIS_MASTER_KEY', os.getenv('MASTER_KEY'))
    if not key: raise ValueError('MASTER_KEY is required to save provider credentials (generate a Fernet key)')
    return Fernet(key.encode())
DEFAULTS={'model_provider':os.getenv('MODEL_PROVIDER','openai'),'embedding_provider':os.getenv('EMBEDDING_PROVIDER','sentence_transformers'),'model':os.getenv('AEGIS_MODEL',os.getenv('OPENAI_MODEL','gpt-4.1-mini')),'embedding_model':os.getenv('EMBEDDING_MODEL','text-embedding-3-small'),'chunk_size':1200,'chunk_overlap':180,'top_k':5,'timeout':int(os.getenv('AEGIS_TIMEOUT','60')),'max_upload_mb':25,'search_provider':os.getenv('SEARCH_PROVIDER','qdrant'),'storage_provider':os.getenv('STORAGE_PROVIDER','local'),'oci_region':os.getenv('OCI_REGION',''),'oci_project_id':'','oci_auth_mode':'api_key','oci_profile':'DEFAULT','oci_model':'','oci_vector_store_id':'','oci_storage_namespace':os.getenv('OCI_NAMESPACE',''),'oci_storage_bucket':os.getenv('OCI_BUCKET',''),'oci_storage_prefix':os.getenv('OCI_OBJECT_PREFIX','aegis'),'oci_storage_region':os.getenv('OCI_REGION',''),'oci_storage_auth_mode':os.getenv('OCI_AUTH_MODE','config_file'),'oci_storage_profile':os.getenv('OCI_PROFILE','DEFAULT'),'queue_provider':os.getenv('QUEUE_PROVIDER','database')}
_execution=ContextVar('aegis_execution',default=None)
@contextmanager
def execution_context(snapshot):
    token=_execution.set(snapshot)
    try:yield
    finally:_execution.reset(token)

def enforce_local_only(cfg):
    if os.getenv('AEGIS_LOCAL_ONLY')=='true':
        allowed={'model_provider':('ollama','mock'),'embedding_provider':('ollama','mock','sentence_transformers'),
                 'search_provider':('local',),'storage_provider':('local',),'queue_provider':('database',)}
        if any(cfg.get(key,DEFAULTS[key]) not in values for key,values in allowed.items()):
            raise ValueError('Local-only mode blocks cloud models, external storage/search, and remote queues.')
    return cfg

def settings():
    active=_execution.get()
    if active is not None:return enforce_local_only(active['settings'].copy())
    try:cfg=DEFAULTS|store.json('configuration/settings.json')
    except FileNotFoundError:cfg=DEFAULTS.copy()
    return enforce_local_only(cfg)
def _provider_secret(key,environment):
    # Explicit clearing overrides bootstrap environment fallback, including profile activation.
    try:store.get(key+'.disabled');return ''
    except FileNotFoundError:pass
    try:encrypted=store.get(key)
    except FileNotFoundError:return os.getenv(environment,'')
    return secret_cipher().decrypt(encrypted).decode()
def execution_secret(provider):
    active=_execution.get()
    if active is None:return None
    ref=active.get('secret_refs',{}).get(provider)
    if not ref:return ''
    return secret_cipher().decrypt(local_store.get(ref)).decode()
def api_key():
    value=execution_secret('openai')
    return value if value is not None else _provider_secret('secrets/provider.enc','OPENAI_API_KEY')
def representation(r):
    return {'id':r.id,'name':r.name,'status':r.status,'kb_id':r.parent_id or None,'size':r.size,'version':r.version,'created_at':r.created_at,'updated_at':r.updated_at,'error':r.error or None}
def job_repr(j):
    return {'id':j.id,'kind':j.kind,'status':j.status,'progress':j.progress,'attempts':j.attempts,'error':j.error or None,'document_id':j.target_id if j.kind=='index' else None,'target_id':j.target_id,'created_at':j.created_at}

def oci_api_key():
    value=execution_secret('oci')
    return value if value is not None else _provider_secret('secrets/oci-provider.enc','OCI_GENAI_API_KEY')

def oci_storage(cfg=None):
    from .oci_adapters import OCIStorageAdapter
    cfg=cfg or settings()
    return OCIStorageAdapter(namespace=cfg.get('oci_storage_namespace') or None,bucket=cfg.get('oci_storage_bucket') or None,prefix=cfg.get('oci_storage_prefix'),region=cfg.get('oci_storage_region') or None,auth_mode=cfg.get('oci_storage_auth_mode') or None,profile=cfg.get('oci_storage_profile') or None)

@contextmanager
def document_lock(document_id):
    """Filesystem lock fences deletion against in-flight worker writes on shared data volume."""
    if os.name=='nt':
        import portalocker
        lock=lambda handle:portalocker.lock(handle,portalocker.LOCK_EX)
        unlock=portalocker.unlock
    else:
        import fcntl
        lock=lambda handle:fcntl.flock(handle,fcntl.LOCK_EX)
        unlock=lambda handle:fcntl.flock(handle,fcntl.LOCK_UN)
    if not all(c.isalnum() or c in '-_' for c in document_id):raise ValueError('Invalid document identifier')
    path=local_store.path('locks/'+document_id+'.lock');path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a') as handle:
        lock(handle)
        try:yield
        finally:unlock(handle)
