"""Storage-first control plane. Only references and operational metadata enter SQL."""
import os, json, uuid, hashlib, secrets, time
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from sqlalchemy import create_engine, String, Integer, Float, Text, select, ForeignKey, inspect, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from cryptography.fernet import Fernet
from .database import database_url, engine_options, StoredString, timestamp_type
from . import runtime_config

DATA = Path(os.getenv('AEGIS_STORAGE_ROOT', os.getenv('DATA_DIR', './data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
URL = database_url(DATA)
engine = create_engine(URL, hide_parameters=True, **engine_options(URL))
def current_engine():
    from .database_control import active_engine
    return active_engine()
class DatabaseSessions(sessionmaker):
    def __call__(self,**kwargs):
        kwargs.setdefault('bind',current_engine())
        return super().__call__(**kwargs)
Session = DatabaseSessions(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
ORACLE_NAMES = URL.get_backend_name() == 'oracle'
USER_TABLE = 'user_tbl' if ORACLE_NAMES else 'users'
class Audit:
    created_by:Mapped[str|None]=mapped_column(String(80),ForeignKey(USER_TABLE+'.id'),nullable=True)
    updated_by:Mapped[str|None]=mapped_column(String(80),ForeignKey(USER_TABLE+'.id'),nullable=True)
    created_via:Mapped[str]=mapped_column(String(24),default='api')
    updated_via:Mapped[str]=mapped_column(String(24),default='api')
class Record(Audit,Base):
    __tablename__='aegis_items' if ORACLE_NAMES else 'records'
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    kind:Mapped[str]=mapped_column(String(32),index=True)
    owner:Mapped[str]=mapped_column(String(80),ForeignKey(USER_TABLE+'.id'),index=True)
    name:Mapped[str]=mapped_column(StoredString(250),default='')
    status:Mapped[str]=mapped_column(String(32),default='ready')
    ref:Mapped[str]=mapped_column(StoredString(500),default='')
    parent_id:Mapped[str]=mapped_column(StoredString(80),default='',index=True)
    created_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
    updated_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
    size:Mapped[int]=mapped_column(Integer,default=0)
    version:Mapped[int]=mapped_column(Integer,default=1)
    error:Mapped[str]=mapped_column(StoredString(500),default='')
class Job(Audit,Base):
    __tablename__='job_tbl' if ORACLE_NAMES else 'jobs'
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    owner:Mapped[str]=mapped_column(String(80),ForeignKey(USER_TABLE+'.id'),index=True)
    kind:Mapped[str]=mapped_column(String(32))
    target_id:Mapped[str]=mapped_column(String(80),index=True)
    document_id:Mapped[str|None]=mapped_column(String(80),ForeignKey('document_tbl.document_id',ondelete='SET NULL'),nullable=True,index=True)
    extract_id:Mapped[str|None]=mapped_column(String(80),ForeignKey('extract_tbl.extract_id',ondelete='SET NULL'),nullable=True,index=True)
    status:Mapped[str]=mapped_column(String(32),default='queued',index=True)
    progress:Mapped[int]=mapped_column(Integer,default=0)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    lease_until:Mapped[float]=mapped_column(timestamp_type(),default=0)
    lease_token:Mapped[str]=mapped_column(StoredString(80),default='')
    error:Mapped[str]=mapped_column(StoredString(500),default='')
    created_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
    updated_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
class User(Audit,Base):
    __tablename__=USER_TABLE
    __table_args__=(CheckConstraint("role IN ('user', 'administrator')",name='ck_user_role'),)
    id:Mapped[str]=mapped_column(String(80),primary_key=True)
    username:Mapped[str]=mapped_column(String(120),unique=True)
    password_hash:Mapped[str]=mapped_column(Text)
    role:Mapped[str]=mapped_column(String(20),default='user',server_default='user')
    created_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
    updated_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
class Login(Audit,Base):
    __tablename__='sessions_tbl' if ORACLE_NAMES else 'sessions'
    id:Mapped[str]=mapped_column(String(100),primary_key=True)
    owner:Mapped[str]=mapped_column(String(80),ForeignKey(USER_TABLE+'.id'))
    expires:Mapped[float]=mapped_column(timestamp_type())
    csrf:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)
    updated_at:Mapped[float]=mapped_column(timestamp_type(),default=time.time)

def is_administrator(user_id, session=None):
    """Read the persisted role; IDs and client-supplied flags grant no access."""
    if session is None:
        with Session() as active:return is_administrator(user_id,active)
    user=session.get(User,user_id)
    return bool(user and user.role=='administrator')

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
    def stat(self,key):
        try:return {'size':self.path(key).stat().st_size}
        except FileNotFoundError:return None
    def list_prefix(self,prefix):
        if not prefix.endswith('/'):raise ValueError('A directory prefix is required')
        root=self.path(prefix)
        return [{'key':prefix+str(p.relative_to(root)).replace('\\','/'),'size':p.stat().st_size} for p in root.rglob('*') if p.is_file()]
local_store=FileStorage()
class RoutingStorage:
    def backend(self,key):
        from .storage_config import backend
        return backend(key)
    def put(self,key,data):
        from .storage_config import backend
        from .workspace_reset import paused
        if paused() and not key.startswith(('configuration/','secrets/','diagnostics/','model/')):
            raise ValueError('Workspace archive operation is running')
        return backend(key,create=True).put(key,data)
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
    engine=current_engine()
    if engine.dialect.name == 'postgresql':
        from sqlalchemy import text
        with engine.begin() as connection:
            connection.execute(text('SELECT pg_advisory_xact_lock(741936)'))
            bootstrap_assignments=not inspect(connection).has_table('user_dataset_tbl')
            Base.metadata.create_all(connection)
            from .relational import upgrade_legacy
            upgrade_legacy(connection,bootstrap_assignments=bootstrap_assignments)
    else:
        # API and worker share this volume. Oracle DDL auto-commits; serialize
        # first-start schema creation rather than relying on transaction locks.
        with document_lock('database-schema'):
            bootstrap_assignments=not inspect(engine).has_table('user_dataset_tbl')
            Base.metadata.create_all(engine)
            from .relational import upgrade_legacy
            with engine.begin() as connection:upgrade_legacy(connection,bootstrap_assignments=bootstrap_assignments)
def secret_cipher():
    key=os.getenv('AEGIS_MASTER_KEY', os.getenv('MASTER_KEY'))
    if not key: raise ValueError('MASTER_KEY is required to save provider credentials (generate a Fernet key)')
    return Fernet(key.encode())
DEFAULTS={'model_provider':os.getenv('MODEL_PROVIDER','openai'),'embedding_provider':os.getenv('EMBEDDING_PROVIDER','sentence_transformers'),'model':os.getenv('AEGIS_MODEL',os.getenv('OPENAI_MODEL','gpt-4.1-mini')),'embedding_model':os.getenv('EMBEDDING_MODEL','text-embedding-3-small'),'chunk_size':runtime_config.get('AEGIS_CHUNK_SIZE'),'chunk_overlap':runtime_config.get('AEGIS_CHUNK_OVERLAP'),'top_k':runtime_config.get('AEGIS_RETRIEVED_CHUNKS'),'timeout':runtime_config.get('AEGIS_TIMEOUT'),'max_upload_mb':runtime_config.get('AEGIS_MAX_UPLOAD_MB'),'search_provider':os.getenv('SEARCH_PROVIDER','qdrant'),'storage_provider':os.getenv('STORAGE_PROVIDER','local'),'oci_region':os.getenv('OCI_REGION',''),'oci_project_id':'','oci_auth_mode':'api_key','oci_profile':'DEFAULT','oci_model':'','oci_vector_store_id':'','oci_storage_namespace':os.getenv('OCI_NAMESPACE',''),'oci_storage_bucket':os.getenv('OCI_BUCKET',''),'oci_storage_prefix':os.getenv('OCI_OBJECT_PREFIX','aegis'),'oci_storage_region':os.getenv('OCI_REGION',''),'oci_storage_auth_mode':os.getenv('OCI_AUTH_MODE','config_file'),'oci_storage_profile':os.getenv('OCI_PROFILE','DEFAULT'),'queue_provider':os.getenv('QUEUE_PROVIDER','database')}
_execution=ContextVar('aegis_execution',default=None)
DEFAULTS.update(local_storage_path='',oci_storage_config_file='/run/oci/config',oci_storage_key_file='/run/oci/aegis_api_key.pem')
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
    if active is not None:cfg=active['settings'].copy()
    else:
        try:cfg=DEFAULTS|store.json('configuration/settings.json')
        except FileNotFoundError:cfg=DEFAULTS.copy()
    from .database_control import vector_backend
    transport=vector_backend()
    if transport:cfg['search_provider']=transport
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
    from .workflow import read
    workflow=read(j.id)
    current=workflow.get('current')
    stage={'upload':'Upload','extract':'Extracting text','index':'Indexing','ready':'Ready'}.get(current,'Ready' if j.status=='completed' else j.status.title())
    return {'id':j.id,'kind':j.kind,'status':j.status,'progress':j.progress,'stage':stage,'workflow':workflow,'attempts':j.attempts,'error':j.error or None,'document_id':j.target_id if j.kind=='index' else None,'target_id':j.target_id,'created_at':j.created_at}

def oci_api_key():
    value=execution_secret('oci')
    return value if value is not None else _provider_secret('secrets/oci-provider.enc','OCI_GENAI_API_KEY')

def oci_storage(cfg=None):
    from .oci_adapters import OCIStorageAdapter
    cfg=cfg or settings()
    return OCIStorageAdapter(namespace=cfg.get('oci_storage_namespace') or None,bucket=cfg.get('oci_storage_bucket') or None,prefix=cfg.get('oci_storage_prefix'),region=cfg.get('oci_storage_region') or None,auth_mode=cfg.get('oci_storage_auth_mode') or None,profile=cfg.get('oci_storage_profile') or None,config_file=cfg.get('oci_storage_config_file') or None,key_file=cfg.get('oci_storage_key_file') or None)

@contextmanager
def document_lock(document_id,*,blocking=True):
    """Filesystem lock fences deletion against in-flight worker writes on shared data volume."""
    if os.name=='nt':
        import portalocker
        lock=lambda handle:portalocker.lock(handle,portalocker.LOCK_EX|(0 if blocking else portalocker.LOCK_NB))
        unlock=portalocker.unlock
    else:
        import fcntl
        lock=lambda handle:fcntl.flock(handle,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
        unlock=lambda handle:fcntl.flock(handle,fcntl.LOCK_UN)
    if not all(c.isalnum() or c in '-_' for c in document_id):raise ValueError('Invalid document identifier')
    path=local_store.path('locks/'+document_id+'.lock');path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a') as handle:
        lock(handle)
        try:yield
        finally:unlock(handle)

# Register the relational tables and transaction hooks after storage exists.
from . import relational
