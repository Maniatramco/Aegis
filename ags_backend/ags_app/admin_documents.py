"""Administrator file operations with durable, resumable document cleanup."""
import time
import hashlib
import json
import threading
from contextlib import contextmanager
from contextlib import ExitStack
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import core, dataset_access as access, dataset_models as routing, document_storage

RELATED={'extraction','conversation','dataset_chat','agent_plan','agent_onboarding','temporary_session'}
_guard=threading.local()


@contextmanager
def lifecycle_guard():
    """Cross-process submission fence, reentrant for Agent -> API submissions."""
    if getattr(_guard,'active',False):yield;return
    with core.document_lock('document-lifecycle'):
        _guard.active=True
        try:yield
        finally:_guard.active=False


def administrator(actor):
    if not core.is_administrator(actor):raise HTTPException(403,'Only an administrator can manage files and processing.')


def document(id):
    with core.Session() as session:row=session.get(core.Record,id)
    if not row or row.kind!='document':raise HTTPException(404,'Document not found.')
    return row


def references(value,ids):
    if isinstance(value,str):return value in ids
    if isinstance(value,list):return any(references(v,ids) for v in value)
    if isinstance(value,dict):return any(k in ids or references(v,ids) for k,v in value.items())
    return False


def related(row):
    with core.Session() as session:
        candidates=list(session.scalars(select(core.Record).where(core.Record.kind.in_(RELATED),core.Record.parent_id.in_([row.parent_id,'']))))
    selected={};ids={row.id}
    # Include chats/workflows referencing a result rather than the document.
    while True:
        changed=False
        for candidate in candidates:
            if candidate.id in selected:continue
            found=False
            for version in range(1,candidate.version+1):
                ref=f'{candidate.kind}/{candidate.id}/v{version}.json'
                try:data=core.store.json(candidate.ref if version==candidate.version else ref)
                except FileNotFoundError:
                    if candidate.kind=='extraction':raise HTTPException(409,'A saved extraction cannot be checked. Restore its metadata before deleting this document.')
                    continue
                if references(data,ids):found=True;break
            if found:selected[candidate.id]=candidate;ids.add(candidate.id);changed=True
        if not changed:return list(selected.values())


def journal_ref(id):return 'document-cleanup/'+id+'.json'


def plan(row):
    try:return core.local_store.json(journal_ref(row.id))
    except FileNotFoundError:pass
    affected=related(row);ids={row.id,*[r.id for r in affected]}
    with core.Session() as session:
        jobs=list(session.scalars(select(core.Job).where(core.Job.target_id.in_(ids))))
    return {'id':row.id,'name':row.name,'version':row.version,'dataset_id':row.parent_id,
        'records':[{'id':r.id,'kind':r.kind,'name':r.name,'version':r.version} for r in sorted(affected,key=lambda r:r.id)],
        'job_ids':sorted(j.id for j in jobs),'stage':'planned','started_at':time.time()}


def counts(saved):
    return {'extractions':sum(r['kind']=='extraction' for r in saved['records']),
        'conversations':sum(r['kind'] in ('conversation','dataset_chat') for r in saved['records']),
        'workflows':sum(r['kind'] in ('agent_plan','agent_onboarding') for r in saved['records']),
        'jobs':len(saved['job_ids'])}


def impact_token(saved):
    return hashlib.sha256(json.dumps({key:saved[key] for key in ('id','version','records','job_ids')},sort_keys=True).encode()).hexdigest()


def cleanup_knowledge(ids):
    from . import providers
    from qdrant_client.models import PointIdsList
    root=core.local_store.path('knowledge/marker').parent
    for path in root.glob('*/manifest.json'):
        name=path.parent.name
        with core.document_lock('unified-knowledge-'+name):
            ref='knowledge/'+name+'/manifest.json';manifest=core.local_store.json(ref)
            removed={key for key,value in manifest.get('points',{}).items() if
                value.get('entity_id','').split(':',1)[0] in ids or references(value.get('document_ids',[]),ids) or value.get('extraction_id') in ids}
            for entity in ids:removed.update(manifest.get('entities',{}).get(entity,{}).get('ids',[]))
            if removed and core.settings()['search_provider'] in ('oracle','qdrant'):
                q=providers.client()
                if q.collection_exists(name):q.delete(name,PointIdsList(points=sorted(removed)),wait=True)
            for entity in ids:manifest.get('entities',{}).pop(entity,None)
            for point in removed:
                manifest.get('points',{}).pop(point,None);manifest.get('vectors',{}).pop(point,None)
            manifest['failures']=[entity for entity in manifest.get('failures',[]) if entity not in ids]
            core.local_store.put_json(ref,manifest)


def cleanup(id,actor,confirmation,expected_version,expected_impact):
    administrator(actor);row=document(id)
    if confirmation!=row.name:raise HTTPException(400,'Type the exact filename to confirm permanent deletion.')
    if expected_version!=row.version:raise HTTPException(409,'Document changed. Reload before deleting.')
    # Worker order is target then dataset. Retain that order to avoid deadlocks.
    with lifecycle_guard(),core.document_lock('submit-'+id),core.document_lock(id):
        row=document(id);saved=plan(row)
        if row.version!=expected_version or impact_token(saved)!=expected_impact:raise HTTPException(409,'The document or affected results changed. Reload the deletion preview before confirming again.')
        from .dataset_lifecycle import ensure_idle
        with core.Session() as session:
            if session.scalar(select(core.Job.id).where(core.Job.id.in_(saved['job_ids']),core.Job.status.in_(['queued','running'])).limit(1)):
                raise HTTPException(409,'Wait for document processing to finish before deleting this file.')
            dataset=session.get(core.Record,row.parent_id)
            if dataset:ensure_idle(dataset,session,ignore_workflows=[r['id'] for r in saved['records']] if row.status=='deleting' else ())
        with ExitStack() as locks:
            for item in sorted(saved['records'],key=lambda r:r['id']):
                prefix={'conversation':'agent-turn-','dataset_chat':'dataset-chat-','agent_plan':'agent-','agent_onboarding':'onboarding-'}.get(item['kind'],'')
                try:locks.enter_context(core.document_lock(prefix+item['id'],blocking=False))
                except Exception:raise HTTPException(409,'A related chat, review or workflow is active. Wait for it to finish, then retry deletion.') from None
            # A review/chat may have changed while we waited for its lock.
            checked=plan(row)
            if impact_token(checked)!=expected_impact:raise HTTPException(409,'Affected results changed. Reload the deletion preview before confirming again.')
            ids={id,*[r['id'] for r in saved['records']]}
            core.local_store.put_json(journal_ref(id),saved)
            with core.Session.begin() as session:
                for target in ids:
                    current=session.get(core.Record,target)
                    if current:current.status='deleting';current.error='Document cleanup in progress.'
                for jid in saved['job_ids']:
                    job=session.get(core.Job,jid)
                    if job:job.status='cancelled';job.lease_token='';job.lease_until=0
            def stage(value):
                saved['stage']=value;core.local_store.put_json(journal_ref(id),saved)
            try:
                from . import providers
                stage('vectors');providers.delete_vectors(id);cleanup_knowledge(ids)
                stage('files')
                prefixes=['documents/'+id+'/']+[r['kind']+'/'+r['id']+'/' for r in saved['records']]
                prefixes+=['jobs/'+jid+'/' for jid in saved['job_ids']]
                prefixes+=['agent-state/'+target+'/' for target in ids|set(saved['job_ids'])]
                keys=['vectors/'+id+'.json']+['jobs/'+jid+'.json' for jid in saved['job_ids']]
                # Conversations save execution snapshots separately from their thread.
                if 'execution_keys' not in saved:
                    execution_keys=[]
                    for item in saved['records']:
                        if item['kind']!='conversation':continue
                        with core.Session() as session:record=session.get(core.Record,item['id'])
                        if record:
                            data=core.store.json(record.ref)
                            execution_keys.extend('executions/'+m['id']+'.json' for m in data.get('messages',[]) if m.get('role')=='user' and m.get('id'))
                    saved['execution_keys']=execution_keys;core.local_store.put_json(journal_ref(id),saved)
                if 'upload_receipts' not in saved:
                    receipt_keys={r['key'] for r in document_storage.routes() if r['key'].startswith('upload-receipts/')}
                    receipt_keys.update('upload-receipts/'+p.name for p in core.local_store.path('upload-receipts/marker').parent.glob('*.json'))
                    saved['upload_receipts']={}
                    for key in receipt_keys:
                        try:receipt=core.store.json(key)
                        except FileNotFoundError:continue
                        if references(receipt,ids):saved['upload_receipts'][key]=receipt['signature']
                    core.local_store.put_json(journal_ref(id),saved)
                for key,signature in saved['upload_receipts'].items():
                    # Keep only the idempotency guard, never stale document or
                    # extraction response bodies that could resurrect references.
                    core.store.put_json(key,{'signature':signature,'deleted':True})
                removed=document_storage.erase(prefixes,keys+saved['execution_keys'])
                stage('cache')
                from .object_cache import purge_payloads
                purge_payloads()
                stage('catalog')
                with core.Session.begin() as session:
                    # Keep content-free terminal queue tombstones so delayed OCI
                    # notifications can be acknowledged without resurrecting work.
                    for jid in saved['job_ids']:
                        job=session.get(core.Job,jid)
                        if job:job.status='cancelled';job.target_id='deleted';job.document_id=None;job.extract_id=None;job.error='';job.lease_token='';job.lease_until=0
                    session.flush()
                    for target in ids:
                        current=session.get(core.Record,target)
                        if current:session.delete(current)
                core.local_store.delete(journal_ref(id))
                return {'ok':True,'id':id,'deleted':True,'objects_removed':removed,'removed':counts(saved)}
            except Exception:
                with core.Session.begin() as session:
                    current=session.get(core.Record,id)
                    if current:current.error='Cleanup paused at '+saved['stage']+'. Retry deletion to finish.'
                raise HTTPException(503,'Cleanup paused at '+saved['stage']+'. The document is unavailable for retrieval. Retry deletion to finish; completed cleanup is safe to repeat.') from None


class DeleteFile(BaseModel):
    confirmation:str=Field(max_length=250)
    expected_version:int=Field(ge=1)
    expected_impact:str=Field(min_length=64,max_length=64)


class Recover(BaseModel):
    allow_external:bool=False


def install(app,auth):
    @app.get('/api/admin/documents')
    def listing(owner=Depends(auth),search:str=Query('',max_length=200),dataset_id:str='',offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
        administrator(owner)
        with core.Session() as session:
            docs=list(session.scalars(select(core.Record).where(core.Record.kind=='document').order_by(core.Record.created_at.desc())))
            datasets={r.id:r for r in session.scalars(select(core.Record).where(core.Record.kind=='knowledge_base'))}
            extractions=list(session.scalars(select(core.Record).where(core.Record.kind=='extraction').order_by(core.Record.created_at.desc())))
            jobs=list(session.scalars(select(core.Job).order_by(core.Job.created_at.desc())))
        grouped={};warnings=0
        for result in extractions:
            try:data=core.store.json(result.ref)
            except (FileNotFoundError,ValueError):warnings+=1;continue
            for did in data.get('document_ids',[]):grouped.setdefault(did,[]).append(core.representation(result)|{'review_status':data.get('review_status','unreviewed'),'template_id':data.get('template_id')})
        docs=[d for d in docs if (not dataset_id or d.parent_id==dataset_id) and (not search or search.casefold() in (d.name+' '+datasets.get(d.parent_id,d).name+' '+d.id).casefold())]
        items=[]
        snapshots={}
        for row in docs[offset:offset+limit]:
            try:public=routing.document_public(row,snapshots)
            except HTTPException:public=core.representation(row)|{'requires_reindex':None}
            index=next((j for j in jobs if j.target_id==row.id),None)
            try:ocr=core.store.json('documents/'+row.id+'/parsed.json').get('ocr')
            except FileNotFoundError:ocr=None
            items.append(public|{'dataset_name':datasets.get(row.parent_id,row).name,'dataset_deleted':bool(datasets.get(row.parent_id) and datasets[row.parent_id].status=='deleted'),
                'storage':document_storage.original(row),'index_job':core.job_repr(index) if index else None,'ocr':ocr,'extractions':grouped.get(row.id,[])})
        return {'items':items,'total':len(docs),'offset':offset,'limit':limit,'metadata_warnings':warnings,'datasets':[{'id':r.id,'name':r.name} for r in datasets.values()]}

    @app.get('/api/admin/documents/{id}/deletion-preview')
    def preview(id:str,owner=Depends(auth)):
        administrator(owner);row=document(id);saved=plan(row)
        return {'id':id,'name':row.name,'version':row.version,'impact_token':impact_token(saved),'affected':counts(saved),'records':saved['records'],'cleanup_stage':saved['stage'],
            'note':'Permanently removes this original, OCR/cache, index/vectors, revisions, related extraction JSON/Parquet and affected chats/workflows. Multi-document results are removed as a whole; other originals and shared prompts/models remain. Content-free queue audit rows are retained.'}

    @app.delete('/api/admin/documents/{id}')
    def remove(id:str,body:DeleteFile,owner=Depends(auth)):
        return cleanup(id,owner,body.confirmation,body.expected_version,body.expected_impact)

    @app.post('/api/admin/documents/{id}/retry')
    def recover(id:str,body:Recover,owner=Depends(auth)):
        administrator(owner);row=document(id)
        if row.status=='deleting':raise HTTPException(409,'Retry deletion to finish cleanup before processing this file.')
        from . import main
        return main.reindex(id,main.Consent(allow_external=body.allow_external),owner)
