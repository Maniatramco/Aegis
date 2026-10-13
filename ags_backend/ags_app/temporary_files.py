"""File expiry metadata only: never conversation or message history."""
import time, logging
from fastapi import Depends, HTTPException
from sqlalchemy import select
from . import core
RETENTION_SECONDS=3600

def marker(id):
    try:return core.store.json('documents/'+id+'/retention.json')
    except FileNotFoundError:return {}

def keep(id):
    with core.document_lock('retention-'+id):
        with core.Session() as s:doc=s.get(core.Record,id)
        if not doc or doc.status=='deleting':raise HTTPException(404,'Document no longer available')
        core.store.delete('documents/'+id+'/retention.json')

def attach(id,session,owner):
    from .main import get_record
    record=get_record(session,owner,'temporary_session');data=core.store.json(record.ref)
    if data['expires_at']<=time.time():raise HTTPException(409,'Temporary session expired. Start a new temporary chat.')
    core.store.put_json('documents/'+id+'/retention.json',{'temporary_session_id':session,'expires_at':data['expires_at']})

def protected(id,owner):
    from .main import records
    for kind in ('conversation','extraction'):
        for r in records(owner,kind):
            if id in core.store.json(r.ref).get('document_ids',[]):return True
    return False

def cleanup(session,owner,expired_only=False):
    from .main import records,delete_document
    removed=[];preserved=[];pending=[]
    for doc in records(owner,'document'):
        with core.document_lock('retention-'+doc.id):
            # Recheck under the same lock used by permanent promotion.
            if marker(doc.id).get('temporary_session_id')!=session:continue
            if protected(doc.id,owner):core.store.delete('documents/'+doc.id+'/retention.json');preserved.append(doc.id);continue
            with core.Session() as s:current=s.get(core.Record,doc.id)
            if not current:continue
            if expired_only and current.status in ('queued','processing'):pending.append(doc.id);continue
            try:delete_document(doc.id,owner);removed.append(doc.id)
            except HTTPException as error:
                if error.status_code!=404:pending.append(doc.id)
    return {'deleted_document_ids':removed,'preserved_document_ids':preserved,'pending_document_ids':pending}

def purge_expired():
    with core.Session() as s:sessions=list(s.scalars(select(core.Record).where(core.Record.kind=='temporary_session')))
    for session in sessions:
        try:
            if core.store.json(session.ref)['expires_at']>time.time():continue
            result=cleanup(session.id,session.owner,True)
            if result['pending_document_ids']:continue
            core.store.delete(session.ref)
            with core.Session.begin() as s:
                current=s.get(core.Record,session.id)
                if current:s.delete(current)
        except Exception:
            # Leave the expiry record for the next sweep; an unavailable store
            # must not kill the worker or turn a failed cleanup into success.
            logging.getLogger(__name__).exception('Temporary file cleanup will retry for session %s',session.id)

def install(app,auth):
    @app.post('/api/temporary-chat/sessions')
    def create(owner=Depends(auth)):
        from .main import new_record
        expires=time.time()+RETENTION_SECONDS
        r=new_record('temporary_session',owner,data={'expires_at':expires})
        return {'id':r.id,'expires_at':expires,'retention_seconds':RETENTION_SECONDS}
    @app.delete('/api/temporary-chat/sessions/{id}')
    def remove(id:str,owner=Depends(auth)):
        from .main import get_record
        get_record(id,owner,'temporary_session');return cleanup(id,owner)
    @app.post('/api/documents/{id}/keep')
    def keep_document(id:str,owner=Depends(auth)):
        from .main import get_record
        get_record(id,owner,'document');keep(id);return {'ok':True,'temporary':False}
