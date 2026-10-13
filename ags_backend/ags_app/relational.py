"""Relational workflow catalog and transactional audit/projection maintenance.

Stored payloads remain authoritative for content; SQL exposes owned, queryable
workflow relationships. No extracted values or credentials are copied to logs.
"""
import time
from contextvars import ContextVar
from functools import wraps
from sqlalchemy import String, Integer, Boolean, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, event, select, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, Session as ORMSession
from . import core
from .database import timestamp_type, StoredString

source = ContextVar('aegis_audit_source', default='api')
actor_override = ContextVar('aegis_audit_actor', default=None)

def audit_as(value):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            token = source.set(value)
            try:return fn(*args, **kwargs)
            finally:source.reset(token)
        return wrapped
    return decorate

class Times(core.Audit):
    created_at:Mapped[float]=mapped_column(timestamp_type(), default=time.time)
    updated_at:Mapped[float]=mapped_column(timestamp_type(), default=time.time)

item_fk = core.Record.__tablename__ + '.id'
user_fk = core.User.__tablename__ + '.id'

class Dataset(Times, core.Base):
    __tablename__='dataset_tbl'
    dataset_id:Mapped[str]=mapped_column(String(80),ForeignKey(item_fk,ondelete='CASCADE'),primary_key=True)
    owner_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk),index=True)
    dataset_name:Mapped[str]=mapped_column(StoredString(250))
    status:Mapped[str]=mapped_column(String(32))

class UserDataset(Times, core.Base):
    __tablename__='user_dataset_tbl'
    user_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk,ondelete='CASCADE'),primary_key=True)
    dataset_id:Mapped[str]=mapped_column(String(80),ForeignKey('dataset_tbl.dataset_id',ondelete='CASCADE'),primary_key=True)
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)

class Document(Times, core.Base):
    __tablename__='document_tbl'
    document_id:Mapped[str]=mapped_column(String(80),ForeignKey(item_fk,ondelete='CASCADE'),primary_key=True)
    dataset_id:Mapped[str]=mapped_column(String(80),ForeignKey('dataset_tbl.dataset_id'),index=True)
    owner_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk),index=True)
    filename:Mapped[str]=mapped_column(StoredString(250))
    is_merged:Mapped[bool]=mapped_column(Boolean,default=False)
    storage_reference:Mapped[str]=mapped_column(StoredString(500))
    status:Mapped[str]=mapped_column(String(32))
    size_bytes:Mapped[int]=mapped_column(Integer,default=0)

class Prompt(Times, core.Base):
    __tablename__='prompt_tbl'
    prompt_id:Mapped[str]=mapped_column(String(80),ForeignKey(item_fk,ondelete='CASCADE'),primary_key=True)
    dataset_id:Mapped[str|None]=mapped_column(String(80),ForeignKey('dataset_tbl.dataset_id'),nullable=True,index=True)
    owner_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk),index=True)
    filename:Mapped[str]=mapped_column(StoredString(250))
    version:Mapped[int]=mapped_column(Integer)
    schema_reference:Mapped[str]=mapped_column(StoredString(500))

class Extraction(Times, core.Base):
    __tablename__='extract_tbl'
    extract_id:Mapped[str]=mapped_column(String(80),ForeignKey(item_fk,ondelete='CASCADE'),primary_key=True)
    dataset_id:Mapped[str]=mapped_column(String(80),ForeignKey('dataset_tbl.dataset_id'),index=True)
    document_id:Mapped[str|None]=mapped_column(String(80),ForeignKey('document_tbl.document_id',ondelete='SET NULL'),nullable=True,index=True)
    prompt_id:Mapped[str|None]=mapped_column(String(80),ForeignKey('prompt_tbl.prompt_id',ondelete='SET NULL'),nullable=True,index=True)
    owner_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk),index=True)
    prompt_version:Mapped[int]=mapped_column(Integer,default=1)
    version:Mapped[int]=mapped_column(Integer,default=1)
    result_reference:Mapped[str]=mapped_column(StoredString(500))
    status:Mapped[str]=mapped_column(String(32))
    filename:Mapped[str]=mapped_column(StoredString(250))
    error_message:Mapped[str]=mapped_column(StoredString(500))

class Review(Times, core.Base):
    __tablename__='review_tbl'
    review_id:Mapped[str]=mapped_column(String(80),primary_key=True)
    extract_id:Mapped[str]=mapped_column(String(80),ForeignKey('extract_tbl.extract_id',ondelete='CASCADE'),index=True)
    extraction_version:Mapped[int]=mapped_column(Integer)
    review_version:Mapped[int]=mapped_column(Integer)
    reviewed_result_reference:Mapped[str]=mapped_column(StoredString(500))
    status:Mapped[str]=mapped_column(String(32))
    __table_args__=(UniqueConstraint('extract_id','review_version',name='uq_review_extract_version'),)

class ModelConfig(Times, core.Base):
    __tablename__='model_config_tbl'
    model_id:Mapped[str]=mapped_column(String(80),ForeignKey(item_fk,ondelete='CASCADE'),primary_key=True)
    category:Mapped[str]=mapped_column(String(24),primary_key=True)
    owner_id:Mapped[str]=mapped_column(String(80),ForeignKey(user_fk),index=True)
    model_name:Mapped[str]=mapped_column(StoredString(250))
    provider_model:Mapped[str]=mapped_column(StoredString(250))
    config_reference:Mapped[str]=mapped_column(StoredString(500))
    version:Mapped[int]=mapped_column(Integer)
    enabled:Mapped[bool]=mapped_column(Boolean)
    __table_args__=(CheckConstraint("category IN ('chat','extraction','embedding')",name='ck_model_category'),)

class DatasetModel(Times, core.Base):
    __tablename__='dataset_model_tbl'
    dataset_id:Mapped[str]=mapped_column(String(80),ForeignKey('dataset_tbl.dataset_id',ondelete='CASCADE'),primary_key=True)
    model_id:Mapped[str]=mapped_column(String(80),primary_key=True)
    category:Mapped[str]=mapped_column(String(24),primary_key=True)
    enabled:Mapped[bool]=mapped_column(Boolean)
    is_default:Mapped[bool]=mapped_column(Boolean)
    __table_args__=(ForeignKeyConstraint(['model_id','category'],['model_config_tbl.model_id','model_config_tbl.category'],name='fk_dataset_model_category'),)

core.Job.__table__.append_constraint(CheckConstraint(
    'document_id IS NULL OR extract_id IS NULL',name='ck_job_single_target'))

def payload(row):
    if row.kind=='document':return {}
    try:return core.store.json(row.ref)
    except FileNotFoundError:return {}

def sync_item(connection, row, data=None, *, history=True):
    data=payload(row) if data is None else data
    common={k:getattr(row,k) for k in ('created_by','updated_by','created_via','updated_via','created_at','updated_at')}
    values={'owner_id':row.owner,**common}
    if row.kind=='knowledge_base':
        model=Dataset;values.update(dataset_id=row.id,dataset_name=row.name,status=row.status)
    elif row.kind=='document':
        from .merged_documents import manifest
        model=Document;values.update(document_id=row.id,dataset_id=row.parent_id,filename=row.name,
            is_merged=bool(manifest(row.id)),storage_reference=row.ref,status=row.status,size_bytes=row.size)
    elif row.kind=='template':
        model=Prompt;values.update(prompt_id=row.id,dataset_id=row.parent_id or None,filename=data.get('source_filename') or row.name,
            version=row.version,schema_reference=row.ref)
    elif row.kind=='extraction':
        ids=data.get('document_ids',[]); merged=data.get('merge') or {}
        # Older combined selections remain honest: no arbitrary first-document FK.
        did=merged.get('document_id') or (ids[0] if len(ids)==1 else None)
        document_name=connection.scalar(select(Document.filename).where(Document.document_id==did)) if did else None
        if did and document_name is None:did=None
        pid=data.get('template_id')
        if pid and not connection.scalar(select(Prompt.prompt_id).where(Prompt.prompt_id==pid)):pid=None
        model=Extraction;values.update(extract_id=row.id,dataset_id=row.parent_id,document_id=did,prompt_id=pid,
            prompt_version=data.get('template_version',1),version=row.version,result_reference=data.get('output_reference') or row.ref,status=row.status,
            filename=merged.get('filename') or document_name or row.name,error_message=row.error)
    elif row.kind=='model':
        table=ModelConfig.__table__
        connection.execute(table.update().where(table.c.model_id==row.id).values(
            enabled=False,**{k:common[k] for k in ('updated_at','updated_by','updated_via')}))
        for category in data.get('capabilities',[]):
            if category not in ('chat','extraction','embedding'):continue
            model_values={**values,'model_id':row.id,'category':category,'model_name':row.name,
                'provider_model':data.get('provider_model',''),'config_reference':row.ref,'version':row.version,'enabled':data.get('enabled',True)}
            where=(table.c.model_id==row.id)&(table.c.category==category)
            if connection.scalar(select(table.c.model_id).where(where)):connection.execute(table.update().where(where).values(**model_values))
            else:connection.execute(table.insert().values(**model_values))
        return
    else:return
    table=model.__table__;key=list(table.primary_key)[0]
    if connection.scalar(select(key).where(key==row.id)):
        connection.execute(table.update().where(key==row.id).values(**values))
    else:connection.execute(table.insert().values(**values))
    if row.kind=='knowledge_base':
        table=DatasetModel.__table__
        existing={(r.model_id,r.category):dict(r._mapping) for r in connection.execute(select(table).where(table.c.dataset_id==row.id))}
        wanted=set()
        for mapping in data.get('mappings',[]):
            mid=mapping['model_id']
            for cfg in connection.execute(select(ModelConfig.__table__).where(ModelConfig.model_id==mid)):
                if not cfg.enabled:continue
                key=(mid,cfg.category);wanted.add(key)
                default_key={'chat':'default_chat_model_id','extraction':'default_extraction_model_id','embedding':'embedding_model_id'}[cfg.category]
                mv={**common,'dataset_id':row.id,'model_id':mid,'category':cfg.category,'enabled':mapping.get('enabled',True),
                    'is_default':data.get(default_key)==mid}
                if key in existing:
                    mv.update({k:existing[key][k] for k in ('created_at','created_by','created_via')})
                    connection.execute(table.update().where(table.c.dataset_id==row.id,table.c.model_id==mid,table.c.category==cfg.category).values(**mv))
                else:connection.execute(table.insert().values(**mv))
        for mid,category in set(existing)-wanted:
            connection.execute(table.delete().where(table.c.dataset_id==row.id,table.c.model_id==mid,table.c.category==category))
    if row.kind=='extraction' and data.get('review_status')=='reviewed':
        add_review(connection,row,data,row.ref,row.version,common)

def add_review(connection,row,data,ref,version,common):
    table=Review.__table__
    if connection.scalar(select(Review.review_id).where(Review.extract_id==row.id,Review.review_version==version)):return
    stamp=data.get('reviewed_at') or row.updated_at
    actor=data.get('reviewed_by') or row.updated_by
    values={**common,'created_at':stamp,'updated_at':stamp,'created_by':actor,'updated_by':actor,
        'created_via':'migration' if source.get()=='migration' else 'api',
        'updated_via':'migration' if source.get()=='migration' else 'api',
        'review_id':core.uid(),'extract_id':row.id,'extraction_version':data.get('reviewed_extraction_version',max(1,version-1)),
        'review_version':version,'reviewed_result_reference':data.get('output_reference') or ref,'status':'reviewed'}
    connection.execute(table.insert().values(**values))

@event.listens_for(ORMSession,'before_flush')
def audit_and_collect(session,context,instances):
    pending_users={r.id for r in session.new if isinstance(r,core.User)}
    changed=[]
    for row in list(session.new)+list(session.dirty):
        if not isinstance(row,(core.Record,core.Job,core.User,core.Login,UserDataset)):continue
        # Account provisioning has no authenticated actor in the existing CLI.
        # Leave that actor unknown rather than crediting the newly created user.
        actor=getattr(row,'owner',None)
        if actor_override.get():actor=actor_override.get()
        if isinstance(row,core.User) and row not in session.new and source.get()=='recovery':
            actor=row.id
        if actor not in pending_users and actor and not session.get(core.User,actor):actor=None
        now=time.time()
        if row in session.new:
            row.created_at=row.created_at or now;row.created_by=actor;row.created_via=source.get()
        row.updated_at=now;row.updated_by=actor;row.updated_via=source.get()
        if isinstance(row,core.Record):changed.append(row)
        if isinstance(row,core.Job):
            target=session.get(core.Record,row.target_id)
            if target and target.kind=='document':row.document_id=target.id;row.extract_id=None
            elif target and target.kind=='extraction':row.extract_id=target.id;row.document_id=None
    session.info['relational_items']=changed
    session.info['new_datasets']=[row for row in session.new if isinstance(row,core.Record) and row.kind=='knowledge_base']
    session.info['relational_deleted']=[r for r in session.deleted if isinstance(r,core.Record)]
    # Explicit deletion works on SQLite too, where legacy installations may
    # not have foreign-key enforcement enabled.
    for row in session.info['relational_deleted']:
        c=session.connection()
        actor=row.owner if session.get(core.User,row.owner) else None
        audit={'updated_at':time.time(),'updated_by':actor,'updated_via':source.get()}
        if row.kind=='document':
            c.execute(core.Job.__table__.update().where(core.Job.document_id==row.id).values(document_id=None,**audit))
            c.execute(Extraction.__table__.update().where(Extraction.document_id==row.id).values(document_id=None,**audit))
            c.execute(Document.__table__.delete().where(Document.document_id==row.id))
        elif row.kind=='template':
            c.execute(Extraction.__table__.update().where(Extraction.prompt_id==row.id).values(prompt_id=None,**audit))
            c.execute(Prompt.__table__.delete().where(Prompt.prompt_id==row.id))
        elif row.kind=='extraction':
            c.execute(core.Job.__table__.update().where(core.Job.extract_id==row.id).values(extract_id=None,**audit))
            c.execute(Review.__table__.delete().where(Review.extract_id==row.id))
            c.execute(Extraction.__table__.delete().where(Extraction.extract_id==row.id))

@event.listens_for(ORMSession,'after_flush_postexec')
def project(session,context):
    rank={'model':0,'knowledge_base':1,'document':2,'template':3,'extraction':4}
    for row in sorted(session.info.pop('relational_items',[]),key=lambda r:rank.get(r.kind,4)):
        sync_item(session.connection(),row)
    for row in session.info.pop('new_datasets',[]):
        connection=session.connection()
        if connection.scalar(select(core.User.id).where(core.User.id==row.owner,core.User.role!='administrator')):
            if not connection.scalar(select(UserDataset.user_id).where(UserDataset.user_id==row.owner,UserDataset.dataset_id==row.id)):
                connection.execute(UserDataset.__table__.insert().values(user_id=row.owner,dataset_id=row.id,enabled=True,created_at=row.created_at,updated_at=row.updated_at,created_by=row.created_by,updated_by=row.updated_by,created_via=row.created_via,updated_via=row.updated_via))

@event.listens_for(ORMSession,'do_orm_execute')
def audit_bulk(execute_state):
    if not execute_state.is_update:return
    table=getattr(execute_state.statement,'table',None)
    if table is not None and table.name==core.Job.__tablename__:
        execute_state.statement=execute_state.statement.values(updated_at=time.time(),updated_by=core.Job.owner,updated_via=source.get())

def upgrade_legacy(connection, bootstrap_assignments=False):
    """Add audit/link columns to existing native DBs without replacing tables."""
    for model in (core.User,core.Login,core.Record,core.Job,UserDataset):
        table=model.__table__;existing={c['name'] for c in inspect(connection).get_columns(table.name)}
        role_added=False
        for column in table.columns:
            if column.name in existing:continue
            kind=column.type.compile(dialect=connection.dialect)
            if model is core.User and column.name=='role':
                connection.execute(text(f"ALTER TABLE {table.name} ADD role {kind} DEFAULT 'user' NOT NULL CHECK (role IN ('user', 'administrator'))"))
                # Run once for legacy installations; a later deliberate demotion
                # of the bootstrap account must survive API/worker restarts.
                role_added=True
                continue
            connection.execute(text(f'ALTER TABLE {table.name} ADD {column.name} {kind}'))
        if role_added:connection.execute(table.update().where(table.c.id=='administrator').values(role='administrator',updated_at=time.time(),updated_via='migration'))
        # Historical creators/updaters were not recorded. Do not invent them.
        connection.execute(table.update().where(table.c.created_via==None).values(created_via='legacy',updated_via='legacy'))
        if model is UserDataset:connection.execute(table.update().where(table.c.enabled==None).values(enabled=True))
        if model in (core.User,core.Login):
            connection.execute(table.update().where(table.c.created_at==None).values(created_at=time.time(),updated_at=time.time()))
    # Fresh tables need no backfill. Existing catalog rows are projected in
    # dependency order, keeping their IDs and storage references.
    from types import SimpleNamespace
    rows=connection.execute(select(core.Record.__table__)).mappings().all()
    rank={'model':0,'knowledge_base':1,'document':2,'template':3,'extraction':4}
    for value in sorted(rows,key=lambda r:rank.get(r['kind'],4)):
        sync_item(connection,SimpleNamespace(**value))
    if bootstrap_assignments:
        for value in rows:
            if value['kind']!='knowledge_base':continue
            if not connection.scalar(select(core.User.id).where(core.User.id==value['owner'],core.User.role!='administrator')):continue
            connection.execute(UserDataset.__table__.insert().values(user_id=value['owner'],dataset_id=value['id'],enabled=True,created_at=time.time(),updated_at=time.time(),created_by=None,updated_by=None,created_via='migration',updated_via='migration'))
