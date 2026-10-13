"""One-screen database setup. Tests never mutate schemas or active routing."""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from contextlib import contextmanager
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,SecretStr
from sqlalchemy import create_engine,select,inspect
from sqlalchemy.engine import URL
from typing import Literal

REF='configuration/database.json'
DEFAULT={'provider':'oci','name':'agsora','region':'ap-mumbai-1','username':'',
    'dsn':'agsora_low','auth_mode':'mtls','wallet_directory':'/run/aegis-db/wallet'}
_engines={};_lock=threading.RLock()

class Connection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:Literal['local','oci']='oci'
    name:str='agsora'
    region:str='ap-mumbai-1'
    username:str=''
    dsn:str='agsora_low'
    auth_mode:Literal['tls','mtls']='mtls'
    wallet_directory:str='/run/aegis-db/wallet'
    password:SecretStr=SecretStr('')
    wallet_password:SecretStr=SecretStr('')

def state():
    from . import core
    try:return core.local_store.json(REF)
    except FileNotFoundError:return {'active_provider':'local','draft':DEFAULT.copy()}

def secrets_for(cfg):
    from . import core
    if not cfg.get('secret_ref'):return {}
    encoded=core.local_store.json(cfg['secret_ref'])['encrypted']
    return json.loads(core.secret_cipher().decrypt(encoded.encode()))

def resolved(body):
    cfg=body.model_dump(exclude={'password','wallet_password'})
    existing=state().get('oci_connection',state().get('draft',{}))
    # A changed destination must never implicitly send the old password to it.
    identity=('username','dsn','auth_mode','wallet_directory')
    saved=secrets_for(existing) if all(existing.get(k)==cfg.get(k) for k in identity) else {}
    cfg['_password']=body.password.get_secret_value() or saved.get('password','')
    cfg['_wallet_password']=body.wallet_password.get_secret_value() or saved.get('wallet_password','')
    return cfg

def parameters(cfg):
    from . import core
    if os.getenv('AEGIS_LOCAL_ONLY')=='true':raise ValueError('This deployment is local-only. OCI database connections are disabled.')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_$#]{0,127}',cfg['username']):raise ValueError('Enter an existing database username.')
    if not cfg.get('_password'):raise ValueError('Enter the database user password. This is separate from the wallet password.')
    if not cfg.get('dsn'):raise ValueError('Enter a connection alias or TCPS connection string.')
    result={'user':cfg['username'],'password':cfg['_password'],'dsn':cfg['dsn'],
        'tcp_connect_timeout':10,'retry_count':0,'ssl_server_dn_match':True}
    if cfg['auth_mode']=='mtls':
        root=Path(cfg['wallet_directory']).resolve()
        allowed=(Path('/run/aegis-db').resolve(),(core.DATA/'oci/database').resolve())
        if not any(p in root.parents for p in allowed):raise ValueError('Use a mounted wallet directory under /run/aegis-db or /data/oci/database.')
        if not all((root/name).is_file() for name in ('tnsnames.ora','ewallet.pem')):raise ValueError('Wallet mount must contain tnsnames.ora and ewallet.pem.')
        if not cfg.get('_wallet_password'):raise ValueError('Enter the password chosen when downloading this wallet.')
        # Reject alias/descriptor mismatches instead of connecting elsewhere.
        if not re.fullmatch(r'[A-Za-z0-9_]+',cfg['dsn']):raise ValueError('For mTLS, use a TNS alias from the wallet, such as agsora_low.')
        tns=(root/'tnsnames.ora').read_text(encoding='utf-8')
        if not re.search(r'^\s*'+re.escape(cfg['dsn'])+r'\s*=',tns,re.M|re.I):raise ValueError('Connection alias was not found in this wallet.')
        result.update(config_dir=str(root),wallet_location=str(root),wallet_password=cfg['_wallet_password'])
    elif not (cfg['dsn'].lower().startswith('tcps://') or re.search(r'protocol\s*=\s*tcps',cfg['dsn'],re.I)):
        raise ValueError('OCI database connections require a TCPS connection string.')
    return result

def candidate(cfg):
    args=parameters(cfg)
    return create_engine(URL.create('oracle+oracledb'),connect_args=args,
        hide_parameters=True,pool_pre_ping=True,pool_size=2,max_overflow=2)

def active_engine():
    from . import core
    cfg=state()
    if cfg.get('active_provider')!='oci':return core.engine
    connection=cfg['active_connection'];key=json.dumps(connection,sort_keys=True)
    with _lock:
        if key not in _engines:
            secret=secrets_for(connection)
            _engines[key]=candidate(connection|{'_password':secret.get('password',''),
                '_wallet_password':secret.get('wallet_password','')})
        return _engines[key]

def vector_backend():
    cfg=state()
    return 'oracle' if cfg.get('active_provider')=='oci' else 'qdrant' if cfg.get('activated_at') else None

def probe(engine):
    from . import core
    with engine.connect() as connection:
        connection.exec_driver_sql('SELECT 1 FROM dual')
        distance=connection.exec_driver_sql("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) FROM dual").scalar()
        assert distance==0
    tables=set(inspect(engine).get_table_names())
    expected=set(core.Base.metadata.tables)|{'aegis_knowledge_vectors'}
    return {'ok':True,'vector_supported':True,'tables_present':len(expected&tables),
        'tables_required':13,'schema_ready':expected<=tables,
        'message':'Database connection and native vector search verified.'}

def prepare(engine):
    from . import core,oracle_vectors
    if not core.ORACLE_NAMES:raise ValueError('OCI activation requires the Oracle-compatible Aegis deployment.')
    with core.document_lock('database-schema'):
        core.Base.metadata.create_all(engine)
        oracle_vectors.prepare(engine)
    return probe(engine)

def no_jobs():
    from . import core
    with core.Session() as session:
        if session.scalar(select(core.Job.id).where(core.Job.status.in_(['queued','running'])).limit(1)):
            raise HTTPException(409,'Wait for processing jobs to finish before changing the database.')
        for record in session.scalars(select(core.Record).where(core.Record.kind=='agent_plan')):
            data=core.store.json(record.ref)
            if any(c.get('status')=='running' for c in data.get('calls',[])):
                raise HTTPException(409,'Wait for the active Agent request to finish before changing the database.')

def save_draft(cfg):
    from . import core
    public={k:v for k,v in cfg.items() if not k.startswith('_')}
    if cfg['provider']=='oci':
        secret_ref='secrets/database/'+str(uuid.uuid4())+'.json'
        secret={'password':cfg['_password'],'wallet_password':cfg['_wallet_password']}
        encrypted=core.secret_cipher().encrypt(json.dumps(secret).encode()).decode()
        core.local_store.put_json(secret_ref,{'encrypted':encrypted})
        public['secret_ref']=secret_ref
    previous=state();previous['draft']=public
    if cfg['provider']=='oci':previous['oci_connection']=public
    core.local_store.put_json(REF,previous)
    return public

def migrate_metadata(source,target):
    """Transactional copy only into an empty or matching Aegis catalog."""
    from . import core
    tables=list(core.Base.metadata.sorted_tables)
    with source.connect() as connection:
        rows={t.name:[dict(r._mapping) for r in connection.execute(select(t))] for t in tables}
    with target.begin() as connection:
        for table in tables:
            keys=[k.name for k in table.primary_key]
            source_keys={tuple(r[k] for k in keys) for r in rows[table.name]}
            target_keys={tuple(r._mapping[k] for k in keys) for r in connection.execute(select(table))}
            if not target_keys<=source_keys:raise ValueError('Destination contains a different Aegis workspace. Use an empty application schema.')
        backup={t.name:[dict(r._mapping) for r in connection.execute(select(t))] for t in tables}
        archive='configuration/database-migrations/'+str(uuid.uuid4())+'.json'
        core.local_store.put_json(archive,{'created_at':time.time(),'destination_before':backup})
        for table in reversed(tables):connection.execute(table.delete())
        for table in tables:
            values=rows[table.name]
            # User audit references can form cycles; populate those nullable
            # references only after every user exists (Oracle checks each row).
            if table is core.User.__table__:values=[r|{'created_by':None,'updated_by':None} for r in values]
            if values:connection.execute(table.insert(),values)
        for row in rows[core.User.__tablename__]:
            connection.execute(core.User.__table__.update().where(core.User.__table__.c.id==row['id']).values(created_by=row['created_by'],updated_by=row['updated_by']))
        for table in tables:
            actual=[dict(r._mapping) for r in connection.execute(select(table))]
            expected=rows[table.name]
            if sorted(actual,key=lambda r:tuple(str(r[k.name]) for k in table.primary_key))!=sorted(expected,key=lambda r:tuple(str(r[k.name]) for k in table.primary_key)):
                raise ValueError('Database copy verification failed; active database was preserved.')
    return {name:len(values) for name,values in rows.items()}

def migrate_vectors(old,new):
    from . import core
    from qdrant_client.models import PointStruct,PointIdsList
    copied=0
    for collection in old.get_collections().collections:
        name=collection.name
        if not name.startswith('aegis_'):continue
        info=old.get_collection(name)
        previous=[];offset=None
        if new.collection_exists(name):
            while True:
                batch,offset=new.scroll(name,limit=100,offset=offset,with_vectors=True,with_payload=True)
                previous.extend({'id':str(p.id),'vector':p.vector,'payload':p.payload} for p in batch)
                if offset is None:break
            core.local_store.put_json('configuration/database-migrations/vectors-'+uuid.uuid4().hex+'.json',{'collection':name,'points':previous})
        else:new.create_collection(name,vectors_config=info.config.params.vectors)
        source_ids=set();offset=None
        while True:
            points,offset=old.scroll(name,limit=100,offset=offset,with_vectors=True,with_payload=True)
            if points:
                new.upsert(name,[PointStruct(id=p.id,vector=p.vector,payload=p.payload) for p in points],wait=True)
                source_ids.update(str(p.id) for p in points);copied+=len(points)
            if offset is None:break
        stale=[p['id'] for p in previous if p['id'] not in source_ids]
        if stale:new.delete(name,PointIdsList(points=stale),wait=True)
        if new.get_collection(name).points_count!=info.points_count:raise ValueError('Vector copy verification failed; active database was preserved.')
    return copied

def activate(cfg):
    from . import core,providers,oracle_vectors
    no_jobs()
    if cfg['provider']=='oci':target=candidate(cfg)
    else:target=core.engine
    try:
        receipt=probe(target)
        if not receipt['schema_ready'] and cfg['provider']=='oci':raise ValueError('Create the Aegis tables before activating this connection.')
        source=active_engine()
        if cfg['provider']=='local' and state().get('active_provider')!='oci':return dict(receipt,active_provider='local',message='Local database is already active.')
        if cfg['provider']=='oci' and state().get('active_provider')=='oci':
            active=state()['active_connection']
            if any(active.get(k)!=cfg.get(k) for k in ('username','dsn','auth_mode','wallet_directory')):
                raise ValueError('Return to Local before selecting a different OCI database.')
            saved=save_draft(cfg);value=state();value['active_connection']=saved
            core.local_store.put_json(REF,value)
            return dict(receipt,active_provider='oci',message='OCI database is already active. Connection configuration verified and saved.')
        with core.document_lock('workspace-reset'):
            no_jobs()
            from .workspace_reset import FLAG
            core.local_store.put_json(FLAG,{'active':True})
            try:
                counts=migrate_metadata(source,target)
                # Copy compatible embeddings, never regenerate or upload originals.
                old=providers.client()
                new=oracle_vectors.OracleVectors(target) if cfg['provider']=='oci' else providers.qdrant_client()
                copied=migrate_vectors(old,new)
                saved=save_draft(cfg);value=state()
                value.update(active_provider=cfg['provider'],active_connection=saved,activated_at=time.time())
                core.local_store.put_json(REF,value)
                return dict(receipt,active_provider=cfg['provider'],copied_rows=counts,copied_vectors=copied,
                    message='Database and knowledge search activated. Original files kept their saved destinations.')
            finally:core.local_store.put_json(FLAG,{'active':False})
    finally:
        if target is not core.engine:target.dispose()

def public():
    from . import core
    cfg=state();draft=cfg.get('draft',DEFAULT.copy());secret=secrets_for(cfg.get('oci_connection',draft))
    wallet=Path(draft.get('wallet_directory','/run/aegis-db/wallet'))
    return {'active_provider':cfg.get('active_provider','local'),
        'local_database':core.engine.url.get_backend_name(),
        'form':{k:v for k,v in draft.items() if k!='secret_ref'},
        'password_saved':bool(secret.get('password')),'wallet_password_saved':bool(secret.get('wallet_password')),
        'wallet_ready':all((wallet/name).is_file() for name in ('tnsnames.ora','ewallet.pem')),
        'vector_provider':vector_backend() or core.settings()['search_provider'],
        'tables_required':13}

def install(app,auth):
    from . import core,dataset_access as access
    @app.get('/api/storage/database')
    def current(actor=Depends(auth)):
        access.require_admin(actor);return public()
    def run(body,operation):
        engine=None
        try:
            cfg=resolved(body)
            if operation=='activate':return activate(cfg)
            engine=core.engine if cfg['provider']=='local' else candidate(cfg)
            result=probe(engine)
            if operation=='prepare':result=prepare(engine)
            if operation=='save':save_draft(cfg)
            return result
        except HTTPException:raise
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else 'Database connection failed. Check username, database password, wallet password and network connectivity.'
            raise HTTPException(400,message) from None
        finally:
            if engine is not None and engine is not core.engine:engine.dispose()
    @app.post('/api/storage/database/test')
    def test(body:Connection,actor=Depends(auth)):
        access.require_admin(actor);return run(body,'test')
    @app.put('/api/storage/database')
    def save(body:Connection,actor=Depends(auth)):
        access.require_admin(actor);no_jobs();return run(body,'save')
    @app.post('/api/storage/database/prepare')
    def schema(body:Connection,actor=Depends(auth)):
        access.require_admin(actor);no_jobs();return run(body,'prepare')
    @app.post('/api/storage/database/activate')
    def choose(body:Connection,actor=Depends(auth)):
        access.require_admin(actor);return run(body,'activate')
