"""Recoverable fresh start: local archive, empty active catalog and derived indexes."""
import hashlib
import json
import shutil
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from sqlalchemy import select,delete,func
from fastapi import Depends,HTTPException
from pydantic import BaseModel
from . import core,relational,dataset_access as access,providers

KINDS={'knowledge_base','document','extraction','template','conversation','agent_plan','agent_onboarding','temporary_session','temporary_document','governance'}
FOLDERS=('knowledge_base','documents','extraction','template','conversation','agent_plan','agent_onboarding',
         'temporary_session','temporary_document','temporary-sessions','temporary-documents','jobs','agent-checkpoints','agent-state','executions','knowledge','vectors','upload-receipts','governance')
TABLES=(relational.Review,relational.Extraction,relational.Prompt,relational.Document,relational.DatasetModel,relational.UserDataset,relational.Dataset)
FLAG='configuration/workspace-maintenance.json'

def paused():
    try:return bool(core.local_store.json(FLAG).get('active'))
    except FileNotFoundError:return False

def archives():
    root=core.DATA/'workspace-archives'
    return [core.local_store.json(str(path.relative_to(core.DATA))) for path in sorted(root.glob('*/receipt.json'),reverse=True)]

def catalog():
    with core.Session() as session:
        counts=dict(session.execute(select(core.Record.kind,func.count()).where(core.Record.kind.in_(KINDS)).group_by(core.Record.kind)).all())
        jobs=session.scalar(select(func.count()).select_from(core.Job).where(core.Job.status.in_(['queued','running'])))
        all_jobs=session.scalar(select(func.count()).select_from(core.Job))
    names=[]
    if core.settings()['search_provider'] in ('qdrant','oracle'):names=[c.name for c in providers.client().get_collections().collections if c.name.startswith('aegis_')]
    return {'counts':counts,'jobs':all_jobs,'active_jobs':jobs,'index_collections':names,'archives':archives(),
        'retained':['Users and sign-in','Registered models and credentials','Installed model weights','Storage configuration'],
        'note':'Archives stay on this laptop. Existing files are not uploaded to OCI.'}

def safe(path):
    value=Path(path).resolve()
    if core.DATA not in value.parents:raise ValueError('Archive path is outside the storage root')
    return value

def rows(model,session):return [{c.key:getattr(row,c.key) for c in model.__table__.columns} for row in session.scalars(select(model))]

def _restore(id):
    if not uuid.UUID(id):raise ValueError('Invalid archive')
    directory=safe(core.DATA/'workspace-archives'/id)
    manifest=core.local_store.json('workspace-archives/'+id+'/manifest.json')
    for name,checksum in manifest['files'].items():
        source=safe(directory/'files'/name)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=checksum:raise ValueError('Workspace archive integrity check failed')
    for folder in manifest['folders']:
        source=safe(directory/'files'/folder);target=safe(core.DATA/folder)
        shutil.copytree(source,target,dirs_exist_ok=True)
    with core.Session.begin() as session:
        # Canonical files are restored before projection hooks read their refs.
        rank={'knowledge_base':0,'document':1,'template':2,'extraction':3}
        for item in sorted(manifest['records'],key=lambda row:rank.get(row['kind'],4)):
            if not session.get(core.Record,item['id']):session.add(core.Record(**item));session.flush()
        for item in manifest['jobs']:
            if not session.get(core.Job,item['id']):session.add(core.Job(**item))
        session.flush()
        for model in TABLES:
            for item in manifest['tables'][model.__name__]:
                keys={column.key:item[column.key] for column in model.__table__.primary_key}
                existing=session.get(model,keys)
                if existing:
                    for key,value in item.items():setattr(existing,key,value)
                else:session.add(model(**item))
    if manifest['collections']:
        from qdrant_client.models import VectorParams,PointStruct
        q=providers.client()
        for name,data in manifest['collections'].items():
            if not q.collection_exists(name):q.create_collection(name,vectors_config=VectorParams(**data['vectors']))
            for start in range(0,len(data['points']),100):q.upsert(name,[PointStruct(**point) for point in data['points'][start:start+100]],wait=True)
    receipt=core.local_store.json('workspace-archives/'+id+'/receipt.json')
    receipt.update(status='restored',restored_at=time.time());core.local_store.put_json('workspace-archives/'+id+'/receipt.json',receipt)
    return receipt

def reset(actor):
    with core.document_lock('workspace-reset'):
        preview=catalog()
        if preview['active_jobs']:raise HTTPException(409,'Finish or cancel processing jobs before a fresh start.')
        if paused():raise HTTPException(409,'A workspace operation is already running.')
        core.local_store.put_json(FLAG,{'active':True})
        locks=ExitStack()
        id=str(uuid.uuid4());directory=safe(core.DATA/'workspace-archives'/id)
        receipt={'id':id,'created_at':time.time(),'status':'preparing','counts':preview['counts'],'jobs':preview['jobs'],'collections':len(preview['index_collections'])}
        try:
            for name in preview['index_collections']:
                if name.startswith('aegis_knowledge_'):locks.enter_context(core.document_lock('unified-knowledge-'+name))
            manifest={'records':[],'jobs':[],'tables':{},'collections':{},'files':{},'folders':[]}
            with core.Session() as session:
                manifest['records']=[row for row in rows(core.Record,session) if row['kind'] in KINDS]
                manifest['jobs']=rows(core.Job,session)
                manifest['tables']={model.__name__:rows(model,session) for model in TABLES}
            roots={core.DATA}
            for path in (core.DATA/'storage-routes').glob('*.json'):
                entry=json.loads(path.read_text(encoding='utf-8'))
                destination=entry['destination']
                if destination['storage_provider']=='local' and entry['key'].split('/',1)[0] in FOLDERS:
                    root=Path(destination.get('local_storage_path') or core.DATA).resolve()
                    if root!=core.DATA:safe(root)
                    roots.add(root)
            folders=sorted({str((root/folder).relative_to(core.DATA)).replace('\\','/') for root in roots for folder in FOLDERS})
            for folder in folders:
                source=safe(core.DATA/folder)
                if not source.exists():continue
                for path in source.rglob('*'):
                    if path.is_symlink():raise ValueError('Workspace archive cannot include symbolic links')
                    if path.is_file():
                        relative=str(path.relative_to(core.DATA)).replace('\\','/')
                        target=safe(directory/'files'/relative);target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(path,target)
                        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
                        if hashlib.sha256(target.read_bytes()).hexdigest()!=checksum:raise ValueError('Archive copy verification failed')
                        manifest['files'][relative]=checksum
                manifest['folders'].append(folder)
            if preview['index_collections']:
                q=providers.client()
                for name in preview['index_collections']:
                    info=q.get_collection(name);points=[];offset=None
                    while True:
                        batch,offset=q.scroll(name,limit=100,offset=offset,with_payload=True,with_vectors=True)
                        points.extend({'id':p.id,'vector':p.vector,'payload':p.payload} for p in batch)
                        if offset is None:break
                    manifest['collections'][name]={'vectors':info.config.params.vectors.model_dump(mode='json'),'points':points}
            core.local_store.put_json('workspace-archives/'+id+'/manifest.json',manifest)
            receipt['status']='archived';core.local_store.put_json('workspace-archives/'+id+'/receipt.json',receipt)
            # Relational dependants first; users, model registrations and profiles stay.
            with core.Session.begin() as session:
                session.execute(delete(core.Job))
                for model in TABLES:session.execute(delete(model))
                session.execute(delete(core.Record).where(core.Record.kind.in_(KINDS)))
            for name in preview['index_collections']:q.delete_collection(name)
            for folder in manifest['folders']:
                source=safe(core.DATA/folder)
                if source.exists():shutil.rmtree(source)
            receipt.update(status='active_workspace_cleared',file_count=len(manifest['files']))
            core.local_store.put_json('workspace-archives/'+id+'/receipt.json',receipt)
            return receipt
        except Exception:
            if receipt['status']=='archived':
                try:_restore(id)
                except Exception:
                    receipt['status']='restore_required';core.local_store.put_json('workspace-archives/'+id+'/receipt.json',receipt)
            raise HTTPException(500,'Fresh start failed. The local archive is preserved; restore it before continuing.') from None
        finally:
            locks.close()
            core.local_store.put_json(FLAG,{'active':False})

class Confirm(BaseModel):
    confirmation:str

def install(app,auth):
    @app.get('/api/workspace/reset-preview')
    def preview(actor=Depends(auth)):
        access.require_admin(actor);return catalog()
    @app.post('/api/workspace/reset')
    def fresh(body:Confirm,actor=Depends(auth)):
        access.require_admin(actor)
        if body.confirmation!='START FRESH':raise HTTPException(400,'Type START FRESH to archive and clear the active workspace.')
        return reset(actor)
    @app.post('/api/workspace/archives/{id}/restore')
    def restore(id:str,body:Confirm,actor=Depends(auth)):
        access.require_admin(actor)
        if body.confirmation!='RESTORE':raise HTTPException(400,'Type RESTORE to restore this archive.')
        with core.document_lock('workspace-reset'):
            if catalog()['counts']:raise HTTPException(409,'Archive the current datasets before restoring an earlier workspace.')
            core.local_store.put_json(FLAG,{'active':True})
            try:return _restore(id)
            except (ValueError,FileNotFoundError):raise HTTPException(400,'Archive is unavailable or failed its integrity check.') from None
            finally:core.local_store.put_json(FLAG,{'active':False})
