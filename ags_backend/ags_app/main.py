import os, time, hashlib, secrets, json, io, csv, threading
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PrivateAttr
from sqlalchemy import select, text, update
from jsonschema import Draft202012Validator, validate, ValidationError, SchemaError
from .core import *
from . import providers, reranker, workflow, temporary_files, dataset_models as routing
from .json_documents import json_document_text
from . import dataset_access as access

@asynccontextmanager
async def lifespan(app):
    from . import runtime_config
    runtime_config.validate()
    init()
    from . import reranker
    if reranker.enabled():
        import asyncio
        await asyncio.to_thread(reranker.load)
    import asyncio
    from contextlib import suppress
    cleanup = asyncio.create_task(temporary_chat.expiry_loop())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
app=FastAPI(title='Aegis AI Data Platform',version='0.1.0',lifespan=lifespan)
@app.exception_handler(RequestValidationError)
async def safe_validation_errors(request, error):
    # FastAPI's default error includes submitted values, including passwords.
    return JSONResponse(status_code=422, content={'detail':[
        {'loc':list(item['loc']), 'msg':item['msg'], 'type':item['type']}
        for item in error.errors()]})
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('ALLOWED_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['Content-Type','X-CSRF-Token','Authorization'])
@app.middleware('http')
async def security_headers(request,call_next):
    actor_token=access.request_actor.set(None)
    audit_token=relational.actor_override.set(None)
    try:
        response=await call_next(request);response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='no-store';return response
    finally:
        access.request_actor.reset(actor_token);relational.actor_override.reset(audit_token)

def authenticate(request:Request):
    token=request.cookies.get('aegis_session','');bearer=request.headers.get('authorization','')
    if bearer.startswith('Bearer '):token=bearer[7:]
    if not token:raise HTTPException(401,'Sign in required')
    with Session() as s:
        login=s.get(Login,hashlib.sha256(token.encode()).hexdigest())
        if not login or login.expires<time.time():raise HTTPException(401,'Session expired')
        if not s.get(User,login.owner):raise HTTPException(401,'Account unavailable')
        if request.method not in ('GET','HEAD','OPTIONS') and not bearer.startswith('Bearer ') and not secrets.compare_digest(request.headers.get('x-csrf-token',''),login.csrf):raise HTTPException(403,'Invalid CSRF token')
        return login.owner

async def auth(request:Request):
    from starlette.concurrency import run_in_threadpool
    owner=await run_in_threadpool(authenticate,request)
    from .workspace_reset import paused
    if paused() and not request.url.path.startswith('/api/workspace/'):
        raise HTTPException(503,'Workspace archive operation is running. Try again when it finishes.')
    access.request_actor.set(owner);relational.actor_override.set(owner)
    if request.method not in ('GET','HEAD','OPTIONS') and any(request.url.path==prefix or request.url.path.startswith(prefix+'/') for prefix in ('/api/datasets','/api/knowledge-bases','/api/models','/api/model-registrations','/api/settings')):
        access.require_admin(owner)
    return owner

def get_record(id,owner,kind=None):
    return access.get_record(id,owner,kind)

def records(owner,kind):
    return access.rows(owner,kind)
def new_record(kind,owner,name='',parent='',data=None,status='ready'):
    if kind in access.SHARED and parent:owner=get_record(parent,owner,'knowledge_base').owner
    id=uid();ref=f'{kind}/{id}/v1.json'
    if data is not None:store.put_json(ref,data)
    r=Record(id=id,kind=kind,owner=owner,name=name,parent_id=parent,ref=ref,status=status,created_at=time.time(),updated_at=time.time())
    with Session.begin() as s:s.add(r)
    return r

def enqueue(owner,kind,target,allow_external=False,snapshot=None,initial_status='queued'):
    with Session() as s:
        record=s.get(Record,target)
        if record:owner=record.owner
    j=Job(id=uid(),owner=owner,kind=kind,target_id=target,status=initial_status,created_at=time.time(),updated_at=time.time())
    store.put_json('jobs/'+j.id+'.json',{'allow_external':allow_external,**({'execution':snapshot} if snapshot else {})})
    workflow.initialize(j.id,kind)
    with Session.begin() as s:s.add(j)
    from .queue_transport import get_transport
    get_transport(settings()['queue_provider']).notify(j.id)
    return j

def external_check(consent,embedding=False,cfg=None):
    cfg=cfg or settings();external=(cfg['embedding_provider'] in ('openai','registered') or cfg['search_provider'] in ('oci','oracle') or cfg['storage_provider']=='oci') if embedding else cfg['model_provider'] in ('openai','oci','registered') or cfg['embedding_provider'] in ('openai','registered') or cfg['search_provider'] in ('oci','oracle')
    if (external or cfg.get('ocr_provider')=='gemini') and not consent:raise HTTPException(409,'This action sends document text or your query to the configured external provider. Confirm external data transmission first.')
    if (cfg['model_provider']=='mock' or cfg['embedding_provider']=='mock') and os.getenv('AEGIS_ALLOW_MOCK')!='true':raise HTTPException(400,'Mock providers require AEGIS_ALLOW_MOCK=true and are for tests only')

class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=120)
    password:str=Field(min_length=1,max_length=200)
    bootstrap_token:str=''

@app.get('/api/auth/status')
def auth_status():
    with Session() as s:return {'setup_required':not bool(s.scalar(select(User)))}
@app.post('/api/auth/setup')
def setup(body:Credentials):
    expected=os.getenv('AEGIS_BOOTSTRAP_TOKEN','')
    if not expected or not secrets.compare_digest(expected,body.bootstrap_token):raise HTTPException(403,'Invalid bootstrap token')
    if len(body.password)<12:raise HTTPException(400,'Use a password of at least 12 characters')
    with document_lock('bootstrap'):
        with Session.begin() as s:
            if s.scalar(select(User)):raise HTTPException(409,'Administrator already configured')
            s.add(User(id='administrator',username=body.username,password_hash=password_hash(body.password),role='administrator'))
    return {'ok':True}
_login_attempts={}
@app.post('/api/auth/login')
def login(body:Credentials,response:Response,request:Request):
    client=request.client.host if request.client else 'unknown';now=time.time()
    attempts=[t for t in _login_attempts.get(client,[]) if t>now-300]
    if len(attempts)>=15:raise HTTPException(429,'Too many login attempts; try again in five minutes')
    _login_attempts[client]=attempts+[now]
    with document_lock('administrator-auth'):
        with Session.begin() as s:
            u=s.scalar(select(User).where(User.username==body.username))
            if not u or not password_valid(body.password,u.password_hash):raise HTTPException(401,'Invalid username or password')
            token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
            s.add(Login(id=hashlib.sha256(token.encode()).hexdigest(),owner=u.id,expires=now+43200,csrf=csrf))
            user={'id':u.id,'username':u.username,'role':u.role,'is_admin':is_administrator(u.id,s)}
    _login_attempts.pop(client,None)
    response.set_cookie('aegis_session',token,httponly=True,secure=os.getenv('COOKIE_SECURE','false')=='true',samesite='strict',max_age=43200,path='/')
    return {'user':user,'csrf_token':csrf,'chat_session_id':hashlib.sha256(('chat:'+hashlib.sha256(token.encode()).hexdigest()).encode()).hexdigest()}
@app.get('/api/auth/me')
def me(request:Request,owner=Depends(auth)):
    with Session() as s:
        u=s.get(User,owner);token=request.cookies.get('aegis_session','');l=s.get(Login,hashlib.sha256(token.encode()).hexdigest())
        return {'user':{'id':u.id,'username':u.username,'role':u.role,'is_admin':is_administrator(u.id,s)},'csrf_token':l.csrf if l else '', 'chat_session_id':hashlib.sha256(('chat:'+l.id).encode()).hexdigest() if l else ''}
@app.post('/api/auth/logout')
def logout(request:Request,response:Response,owner=Depends(auth)):
    with Session.begin() as s:
        row=s.get(Login,hashlib.sha256(request.cookies.get('aegis_session','').encode()).hexdigest())
        if row:s.delete(row)
    response.delete_cookie('aegis_session');return {'ok':True}
from .user_management import install as install_user_management
install_user_management(app, auth)
from .storage_config import install as install_storage_config
install_storage_config(app,auth)
from .database_control import install as install_database_control
install_database_control(app,auth)
from .workspace_reset import install as install_workspace_reset
install_workspace_reset(app,auth)
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/ready')
def ready():
    try:
        with current_engine().connect() as c:c.execute(select(1))
        if settings()['search_provider'] in ('qdrant','oracle'):providers.client().get_collections()
        if settings()['search_provider']=='oci':providers.oci_vector().test_connection()
        from . import reranker
        if reranker.enabled():reranker.load()
        return {'status':'ready','database':True,'vector_store':True,'reranker':reranker.status()}
    except Exception:raise HTTPException(503,'Database, vector store or configured reranker unavailable')
@app.get('/api/overview')
def overview(owner=Depends(auth)):
    docs=records(owner,'document')
    jobs=access.jobs(owner)
    return {'documents':len(docs),'ready':sum(d.status=='ready' for d in docs),'jobs':sum(j.status in ('queued','running') for j in jobs),'knowledge_bases':len(records(owner,'knowledge_base')),'failed':sum(d.status=='failed' for d in docs)}
class KBInput(BaseModel):name:str=Field(min_length=1,max_length=200);description:str='';active:bool=Field(default=True,strict=True)
@app.get('/api/knowledge-bases')
def kbs(owner=Depends(auth)):return [routing.dataset_public(r) for r in records(owner,'knowledge_base')]
@app.post('/api/knowledge-bases')
def create_kb(body:KBInput,owner=Depends(auth)):
    access.require_admin(owner)
    return routing.dataset_public(new_record('knowledge_base',owner,body.name,data=body.model_dump()|routing.ROUTING_DEFAULTS|{'routing_version':1}))
@app.get('/api/documents')
def documents(kb_id:str|None=None,dataset_id:str|None=None,owner=Depends(auth)):
    scope=dataset_id or kb_id
    if scope:get_record(scope,owner,'knowledge_base')
    snapshots={}
    return [routing.document_public(d,snapshots) for d in records(owner,'document') if not scope or d.parent_id==scope]
@app.post('/api/documents/upload')
async def upload(files:list[UploadFile]=File(...),kb_id:str=Form(''),dataset_id:str=Form(''),allow_external:bool=Form(False),temporary_session_id:str=Form(''),owner=Depends(auth),merge_files:bool=Form(False),template_id:str=Form(''),display_name:str=Form(''),idempotency_key:str=Form(''),merge_records:bool=Form(False)):
    # Form defaults are descriptors on internal direct calls; normalize them.
    template_id=template_id if isinstance(template_id,str) else ''
    display_name=display_name if isinstance(display_name,str) else ''
    idempotency_key=idempotency_key if isinstance(idempotency_key,str) else ''
    merge_records=merge_records if isinstance(merge_records,bool) else False
    # Consent rejection must precede an upload receipt. Otherwise a rejected
    # request looks interrupted and cannot safely be retried after approval.
    upload_snapshot=None
    if dataset_id or kb_id:
        if dataset_id and kb_id and dataset_id!=kb_id:raise HTTPException(400,'Conflicting dataset identifiers')
        upload_snapshot=routing.execution_snapshot(get_record(dataset_id or kb_id,owner,'knowledge_base'),'embedding')
        external_check(allow_external,True,upload_snapshot['settings'])
    if template_id:
        template=get_record(template_id,owner,'template')
        scope_id=dataset_id or kb_id
        if template.parent_id and template.parent_id!=scope_id:raise HTTPException(400,'Choose a prompt belonging to the upload dataset')
        # Validate routing before accepting originals or starting expensive jobs.
        extraction_snapshot=routing.execution_snapshot(get_record(scope_id,owner,'knowledge_base'),'extraction')
        external_check(allow_external,cfg=extraction_snapshot['settings'])
    receipt='upload-receipts/'+hashlib.sha256(json.dumps([owner,idempotency_key]).encode()).hexdigest()+'.json' if idempotency_key else None
    if receipt:
        with document_lock('upload-'+hashlib.sha256(receipt.encode()).hexdigest()):
            return await _upload_with_receipt(files,kb_id,dataset_id,allow_external,temporary_session_id,owner,merge_files,template_id,display_name,idempotency_key,merge_records,receipt,upload_snapshot)
    return await _upload_with_receipt(files,kb_id,dataset_id,allow_external,temporary_session_id,owner,merge_files,template_id,display_name,idempotency_key,merge_records,None,upload_snapshot)

async def _upload_with_receipt(files,kb_id,dataset_id,allow_external,temporary_session_id,owner,merge_files,template_id,display_name,idempotency_key,merge_records,receipt,upload_snapshot=None):
    signature=hashlib.sha256(json.dumps([dataset_id or kb_id,template_id,display_name,merge_records]).encode())
    for file in files:
        signature.update((file.filename or '').encode());raw=await file.read(settings()['max_upload_mb']*1024*1024+1);await file.seek(0);signature.update(hashlib.sha256(raw).digest())
    digest=signature.hexdigest()
    if receipt:
        try:previous=store.json(receipt)
        except FileNotFoundError:previous=None
        if previous:
            if previous['signature']!=digest:raise HTTPException(409,'Upload idempotency key was already used for different inputs')
            if previous.get('response'):return previous['response']
            if not previous.get('uploaded'):raise HTTPException(409,'Upload submission was interrupted. Inspect dataset originals before resubmitting; automatic replay could duplicate files.')
    else:previous=None
    if previous and previous.get('uploaded'):response=previous['uploaded']
    else:
        if receipt:store.put_json(receipt,{'signature':digest})
        response=await _upload_documents(files,kb_id,dataset_id,allow_external,temporary_session_id,owner,False if template_id else merge_files,upload_snapshot)
        if receipt:store.put_json(receipt,{'signature':digest,'uploaded':response})
    if template_id:
        extraction=create_extraction(ExtractInput(dataset_id=dataset_id or kb_id,document_ids=[d['id'] for d in response['documents']],template_id=template_id,display_name=display_name or None,idempotency_key=idempotency_key+'-extract' if idempotency_key else None,merge_records=merge_records,wait_for_index=True,allow_external=allow_external),owner)
        response=dict(response,extractions=[extraction],extraction_id=extraction['id'])
    if receipt:store.put_json(receipt,{'signature':digest,'response':response})
    return response

async def _upload_documents(files,kb_id,dataset_id,allow_external,temporary_session_id,owner,merge_files,snapshot=None):
    if temporary_session_id:raise HTTPException(409,'Temporary chat uploads use /api/temporary-chat/documents and never create an index.')
    if kb_id and dataset_id and kb_id!=dataset_id:raise HTTPException(400,'Conflicting dataset identifiers')
    kb_id=dataset_id or kb_id
    if not kb_id:raise HTTPException(409,'Create or choose a dataset and map its embedding model before uploading.')
    dataset=get_record(kb_id,owner,'knowledge_base');snapshot=snapshot or routing.execution_snapshot(dataset,'embedding')
    if len(files)>20:raise HTTPException(400,'Upload at most 20 files at once')
    external_check(allow_external,True,snapshot['settings']);result=[];jobs=[]
    if not files:raise HTTPException(400,'Choose at least one file')
    limit=settings()['max_upload_mb']*1024*1024
    for file in files:
        name=(file.filename or '').replace('\\','/').split('/')[-1]
        if name.rsplit('.',1)[-1].lower() not in ('txt','pdf','docx','json'):raise HTTPException(400,'Only PDF, DOCX, UTF-8 TXT and JSON files are supported')
        raw=await file.read(limit+1);await file.seek(0)
        if not raw or len(raw)>limit:raise HTTPException(413,'A file is empty or exceeds the upload size limit')
        if name.lower().endswith('.txt'):
            try:raw.decode('utf-8-sig')
            except UnicodeDecodeError:raise HTTPException(400,'TXT must use UTF-8 encoding')
        if name.lower().endswith('.json'):
            try:json_document_text(raw)
            except ValueError as error:raise HTTPException(400,str(error))
    merged = None; original_parts = []
    if merge_files is True and len(files)>1:
        from . import merged_documents
        import io
        limit=settings()['max_upload_mb']*1024*1024
        for file in files:
            raw=await file.read(limit+1)
            if not raw or len(raw)>limit:raise HTTPException(413,'An original file is empty or exceeds the upload size limit.')
            original_parts.append((file.filename or 'document',raw))
        try:name,raw,merged=merged_documents.prepare(original_parts)
        except Exception as exc:raise HTTPException(422,'Cannot merge these files. Check their format, text content and page limits, or choose independent extraction.') from exc
        if len(raw)>limit:raise HTTPException(413,'The merged file exceeds the upload size limit. Choose fewer files or independent extraction.')
        files=[UploadFile(filename=name,file=io.BytesIO(raw))]
    for file in files:
        name=(file.filename or 'document').replace('\\','/').split('/')[-1][:200]
        if name.rsplit('.',1)[-1].lower() not in ('txt','pdf','docx','json'):raise HTTPException(400,'Only PDF, DOCX, UTF-8 TXT and JSON files are supported')
        limit=settings()['max_upload_mb']*1024*1024;raw=await file.read(limit+1)
        if len(raw)>limit:raise HTTPException(413,'File exceeds configured upload size')
        if not raw:raise HTTPException(400,'Empty file')
        if name.rsplit('.',1)[-1].lower()=='json':
            try:json_document_text(raw)
            except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        id=uid();ref='documents/'+id+'/original';store.put(ref,raw)
        r=Record(id=id,kind='document',owner=dataset.owner,name=name,ref=ref,parent_id=kb_id,status='queued',size=len(raw),created_at=time.time(),updated_at=time.time())
        if merged:
            merged_documents.save(id,merged,original_parts)
        with Session.begin() as s:s.add(r)
        j=enqueue(owner,'index',id,allow_external,snapshot);result.append(routing.document_public(r));jobs.append(job_repr(j))
    return {'documents':result,'jobs':jobs}
@app.get('/api/documents/{id}')
def document(id:str,owner=Depends(auth)):return routing.document_public(get_record(id,owner,'document'))
@app.get('/api/documents/{id}/preview')
def preview(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'document')
    info={'page_count':original_pdf_page_count(store.get(r.ref))} if r.name.lower().endswith('.pdf') else {}
    try:data=store.json('documents/'+id+'/chunks.json');return {'text':'\n\n'.join(c['text'] for c in data['chunks']),'chunks':data['chunks'],'document':representation(r),**info}
    except FileNotFoundError:return {'text':'Text is not available until processing completes.','chunks':[],'document':representation(r),**info}
@app.get('/api/documents/{id}/download')
def download(id:str,owner=Depends(auth)):
    from urllib.parse import quote
    r=get_record(id,owner,'document');return Response(store.get(r.ref),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r.name)})
@app.get('/api/documents/{id}/source')
def source_document(id:str,owner=Depends(auth)):
    from urllib.parse import quote
    r=get_record(id,owner,'document');ext=r.name.rsplit('.',1)[-1].lower()
    if ext not in ('pdf','txt','json'):raise HTTPException(415,'Inline original preview supports PDF, UTF-8 TXT and JSON. Download DOCX to review its original layout.')
    return Response(store.get(r.ref),media_type={'pdf':'application/pdf','json':'application/json'}.get(ext,'text/plain; charset=utf-8'),headers={'Content-Disposition':"inline; filename*=UTF-8''"+quote(r.name),'Content-Security-Policy':"sandbox"})

def original_pdf_page_count(raw):
    import pypdfium2 as pdfium
    from .ocr import _pdf_lock
    try:
        with _pdf_lock:
            doc=pdfium.PdfDocument(raw)
            try:return len(doc)
            finally:doc.close()
    except Exception:return None

def original_page_image(raw,page):
    if page<1 or page>10000:raise HTTPException(422,'Choose a valid original PDF page.')
    from . import ocr
    try:image,_,_=ocr.render_pdf(raw,page-1,120)
    except Exception:raise HTTPException(422,'This original PDF page could not be rendered. Download the original to inspect it.') from None
    return Response(image,media_type='image/png',headers={'Cache-Control':'private, max-age=300','X-Content-Type-Options':'nosniff'})

@app.get('/api/documents/{id}/page-image')
def document_page_image(id:str,page:int=1,owner=Depends(auth)):
    r=get_record(id,owner,'document')
    if not r.name.lower().endswith('.pdf'):raise HTTPException(415,'Page images are available for original PDF files.')
    return original_page_image(store.get(r.ref),page)

@app.get('/api/documents/{id}/merged-sources/{key}/{action}')
def merged_source(id:str,key:str,action:str,page:int=1,owner=Depends(auth)):
    from . import merged_documents
    from urllib.parse import quote
    get_record(id,owner,'document')
    metadata=merged_documents.manifest(id)
    source=next((s for s in (metadata or {}).get('sources',[]) if s['key']==key),None)
    if not source or action not in ('preview','source','download','page-image'):raise HTTPException(404,'Merged source not found')
    if action=='preview':return {'text':'\n\n'.join(p['text'] for p in metadata['pages'] if p['source_key']==key),'page_count':source.get('page_count')}
    ext=source['name'].rsplit('.',1)[-1].lower()
    if action=='page-image':
        if ext!='pdf':raise HTTPException(415,'Page images are available for original PDF files.')
        return original_page_image(store.get(f'documents/{id}/merged-sources/{key}/original'),page)
    if action=='source' and ext not in ('pdf','txt','json'):raise HTTPException(415,'Download this original to inspect its layout.')
    return Response(store.get(f'documents/{id}/merged-sources/{key}/original'),media_type={'pdf':'application/pdf','json':'application/json','txt':'text/plain; charset=utf-8'}.get(ext,'application/octet-stream'),headers={'Content-Disposition':('inline' if action=='source' else 'attachment')+"; filename*=UTF-8''"+quote(source['name']),'Content-Security-Policy':'sandbox'})
class Consent(BaseModel):allow_external:bool=False
@app.post('/api/documents/{id}/reindex')
def reindex(id:str,body:Consent,owner=Depends(auth)):
    doc=get_record(id,owner,'document');dataset,_=routing.documents_scope(owner,doc.parent_id,[id]);snapshot=routing.execution_snapshot(dataset,'embedding');external_check(body.allow_external,True,snapshot['settings'])
    with document_lock('submit-'+id):
        with Session.begin() as s:
            if s.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):raise HTTPException(409,'An indexing job is already active')
            r=s.get(Record,id);r.status='queued';r.error=''
        return job_repr(enqueue(owner,'index',id,body.allow_external,snapshot))

class ReextractDocument(Consent):confirm_reviewed:bool=False
@app.post('/api/documents/{id}/reextract')
def reextract_document(id:str,body:ReextractDocument,owner=Depends(auth)):
    doc=get_record(id,owner,'document')
    reviewed=[r for r in records(owner,'extraction') if id in store.json(r.ref).get('document_ids',[]) and store.json(r.ref).get('review_status')=='reviewed']
    if reviewed and not body.confirm_reviewed:raise HTTPException(409,'Reviewed extraction results exist. Confirm re-extraction; saved structured reviews are retained and can be rerun separately.')
    with document_lock('submit-'+id):
        with Session() as s:
            if s.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):raise HTTPException(409,'A document job is already active')
        revision=doc.version+1
        for suffix in ('parsed.json','chunks.json','index.json','index-execution.json'):
            try:store.put(f'documents/{id}/versions/v{doc.version}/{suffix}',store.get('documents/'+id+'/'+suffix))
            except FileNotFoundError:pass
        dataset,_=routing.documents_scope(owner,doc.parent_id,[id]);snapshot=routing.execution_snapshot(dataset,'embedding');external_check(body.allow_external,True,snapshot['settings'])
        with Session.begin() as s:
            r=s.get(Record,id);r.version=revision;r.status='queued';r.error=''
        result=job_repr(enqueue(owner,'index',id,body.allow_external,snapshot))
        return result|{'original_retained':True,'document_version':revision,'reviewed_results_retained':True}
@app.delete('/api/documents/{id}')
def delete_document(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'document')
    with Session.begin() as s:
        for j in s.scalars(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):j.status='cancelled';j.lease_token=''
        s.get(Record,id).status='deleting'
    with document_lock(id):
        try:providers.delete_vectors(id)
        except Exception:raise HTTPException(503,'Vector cleanup failed; document is unavailable for retrieval. Retry deletion when vector storage recovers.')
        from . import merged_documents
        merged=merged_documents.manifest(id)
        for item in (merged or {}).get('sources',[]):store.delete(f'documents/{id}/merged-sources/{item["key"]}/original')
        for suffix in ['original','parsed.json','chunks.json','index.json','index-execution.json','retention.json','merged.json']:store.delete('documents/'+id+'/'+suffix)
        for n in range(1,r.version+1):
            for suffix in ('parsed.json','chunks.json','index.json','index-execution.json'):store.delete(f'documents/{id}/versions/v{n}/{suffix}')
        with Session.begin() as s:s.delete(s.get(Record,id))
    return {'ok':True}
from typing import Literal
class ConversationInput(BaseModel):title:str='New conversation';kb_id:str='';dataset_id:str='';document_ids:list[str]=Field(default_factory=list);mode:Literal['documents','general']='documents'
@app.get('/api/conversations')
def conversations(owner=Depends(auth)):return [representation(r)|{'title':r.name} for r in records(owner,'conversation')]
@app.post('/api/conversations')
def create_conversation(body:ConversationInput,owner=Depends(auth)):
    dataset_id=body.dataset_id or body.kb_id
    if body.mode=='general' and (dataset_id or body.document_ids):raise HTTPException(422,'General chat cannot include document references. Choose a document conversation.')
    if body.dataset_id and body.kb_id and body.dataset_id!=body.kb_id:raise HTTPException(400,'Conflicting dataset identifiers')
    if dataset_id or body.document_ids:dataset,_=routing.documents_scope(owner,dataset_id,body.document_ids);dataset_id=dataset.id
    for id in body.document_ids:temporary_files.keep(id)
    r=new_record('conversation',owner,body.title[:200],parent=dataset_id,data=body.model_dump()|{'dataset_id':dataset_id,'kb_id':dataset_id,'messages':[]});return representation(r)|store.json(r.ref)
@app.get('/api/conversations/{id}')
def conversation(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'conversation');return representation(r)|store.json(r.ref)
class MessageInput(BaseModel):
    text:str=Field(min_length=1,max_length=12000);document_ids:list[str]|None=None;kb_id:str|None=None;dataset_id:str|None=None;model_id:str|None=None;allow_external:bool=False
    # Only the agent reply route can set verified application state. Public
    # message bodies cannot supply this private attribute or invent successes.
    _agent_context:dict|None=PrivateAttr(default=None)
_locks={}
def message_execution(body,owner,data):
    if body.dataset_id and body.kb_id and body.dataset_id!=body.kb_id:raise HTTPException(400,'Conflicting dataset identifiers')
    ids=body.document_ids if body.document_ids is not None else data.get('document_ids',[])
    dataset_id=body.dataset_id if body.dataset_id is not None else body.kb_id if body.kb_id is not None else data.get('dataset_id') or data.get('kb_id','')
    if data.get('mode')=='general':
        if dataset_id or ids:raise HTTPException(409,'Start a document conversation to use a dataset.')
        from .temporary_chat import chat_snapshot
        snapshot=chat_snapshot(owner,body.model_id or '')
        snapshot['settings']['general_chat']=True
        if body._agent_context is not None:snapshot['settings']['agent_context']=body._agent_context
        external_check(body.allow_external,cfg=snapshot['settings'])
        return [],snapshot
    pinned=data.get('dataset_id') or data.get('kb_id')
    if not pinned and data.get('document_ids'):
        try:previous,_=routing.documents_scope(owner,'',data['document_ids']);pinned=previous.id
        except HTTPException:raise HTTPException(409,'Start a new conversation scoped to one dataset.')
    if data.get('messages') and not pinned:raise HTTPException(409,'Start a new conversation scoped to one dataset.')
    dataset,docs=routing.documents_scope(owner,dataset_id,ids)
    if pinned and dataset.id!=pinned:raise HTTPException(409,'A conversation stays within its original dataset. Start a new conversation for another dataset.')
    snapshot=routing.execution_snapshot(dataset,'chat',body.model_id);routing.require_indexes(docs,snapshot)
    snapshot['settings'].pop('general_chat',None)
    data['dataset_id']=dataset.id;data['kb_id']=dataset.id
    external_check(body.allow_external,cfg=snapshot['settings']);external_check(body.allow_external,True,snapshot['embedding_execution']['settings'])
    return [d for d in docs if d.status=='ready'],snapshot


@app.post('/api/conversations/{id}/messages')
def message(id:str,body:MessageInput,owner=Depends(auth)):
    r=get_record(id,owner,'conversation');lock=_locks.setdefault(id,threading.Lock())
    if not lock.acquire(blocking=False):raise HTTPException(409,'This conversation already has a response in progress')
    try:
        data=store.json(r.ref);docs,snapshot=message_execution(body,owner,data);selection=routing.public_selection(snapshot)
        for doc in docs:temporary_files.keep(doc.id)
        data['document_ids']=[doc.id for doc in docs]
        request_id=uid();store.put_json('executions/'+request_id+'.json',snapshot)
        data['messages'].append({'id':request_id,'role':'user','text':body.text,'created_at':time.time(),'model_selection':selection});store.put_json(r.ref,data)
        try:
            sources=[]
            if not snapshot['settings'].get('general_chat'):
                with execution_context(snapshot['embedding_execution']):sources=providers.search(body.text,owner,docs,settings()['top_k'])
            with execution_context(snapshot):text_answer=providers.answer(body.text,sources,data['messages'][:-1])
        except providers.ProviderError as e:raise HTTPException(502,str(e))
        except Exception:raise HTTPException(502,'Retrieval or generation failed; check configured provider connectivity')
        import re
        used={int(x) for x in re.findall(r'\[(\d+)\]',text_answer)}
        citations=[{'index':i+1,**source,'url':'/api/documents/'+source['document_id']+'/preview'} for i,source in enumerate(sources) if i+1 in used]
        msg={'id':uid(),'role':'assistant','text':text_answer,'citations':citations,'created_at':time.time(),'mock':snapshot['settings']['model_provider']=='mock','model_selection':selection}
        data['messages'].append(msg);store.put_json(r.ref,data)
        return {'message':msg,'conversation_id':id}
    finally:lock.release()
class Feedback(BaseModel):rating:str
@app.post('/api/messages/{id}/feedback')
def feedback(id:str,body:Feedback,owner=Depends(auth)):
    if body.rating not in ('up','down','positive','negative'):raise HTTPException(400,'Choose up or down')
    for r in records(owner,'conversation'):
        data=store.json(r.ref)
        for m in data['messages']:
            if m['id']==id:m['feedback']=body.rating;store.put_json(r.ref,data);return {'ok':True}
    raise HTTPException(404,'Message not found')
@app.get('/api/conversations/{id}/export')
def export_conversation(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'conversation');return Response(store.get(r.ref),media_type='application/json',headers={'Content-Disposition':'attachment; filename="conversation.json"'})
class TemplateInput(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    schema_:dict=Field(alias='schema')
    dataset_id:str|None=None
    instructions:str=Field(default='',max_length=12000)
    source_filename:str|None=Field(default=None,max_length=200,pattern=r'(?i)^[^/\\\x00-\x1f\x7f]+\.json$')

def uploaded_template(body,owner):
    if not body.source_filename:return None
    matches=[r for r in records(owner,'template') if r.parent_id==(body.dataset_id or '') and (store.json(r.ref).get('source_filename') or '').casefold()==body.source_filename.casefold()]
    if len(matches)>1:raise HTTPException(409,'Multiple templates have this filename in the selected dataset. Resolve the duplicate filenames before uploading again.')
    return matches[0] if matches else None
def check_schema(schema):
    def location(path):return '$'+''.join('['+str(part)+']' if isinstance(part,int) else '.'+str(part) for part in path)
    try:Draft202012Validator.check_schema(schema)
    except SchemaError as exc:raise HTTPException(400,'Invalid JSON Schema at '+location(exc.absolute_path)+': '+exc.message) from exc
    except Exception:raise HTTPException(400,'Invalid JSON Schema')
    if schema.get('type')!='object':raise HTTPException(400,'Extraction schema at $ must have type:"object"')
    def safe_refs(node,path=()):
        if isinstance(node,dict):
            for key,value in node.items():
                if key in ('$ref','$dynamicRef') and (not isinstance(value,str) or not value.startswith('#')):raise HTTPException(400,'Only local JSON Schema references are supported at '+location((*path,key)))
                safe_refs(value,(*path,key))
        elif isinstance(node,list):
            for index,child in enumerate(node):safe_refs(child,(*path,index))
    safe_refs(schema)
    def strict(node,path=()):
        if not isinstance(node,dict):return
        kind=node.get('type')
        if kind=='object' or isinstance(kind,list) and 'object' in kind:
            if node.get('additionalProperties') is not False:raise HTTPException(400,'Strict extraction requires additionalProperties:false at '+location(path))
            if set(node.get('required',[]))!=set(node.get('properties',{})):raise HTTPException(400,'Strict extraction requires every property in required at '+location(path)+'. Use a nullable type for optional values.')
        for key,value in node.items():
            if key in ('properties','$defs','definitions'):
                for name,child in value.items():strict(child,(*path,key,name))
            elif key=='items':strict(value,(*path,key))
            elif key in ('anyOf','oneOf','allOf'):
                for index,child in enumerate(value):strict(child,(*path,key,index))
    strict(schema)
@app.get('/api/templates')
def templates(owner=Depends(auth)):
    result=[]
    for r in records(owner,'template'):
        data=store.json(r.ref)
        result.append(representation(r)|data|{'name':data.get('source_filename') or data['name']})
    return result
@app.post('/api/templates/validate')
def validate_template(body:TemplateInput,owner=Depends(auth)):
    if body.dataset_id:get_record(body.dataset_id,owner,'knowledge_base')
    check_schema(body.schema_)
    existing=uploaded_template(body,owner)
    return {'valid':True,'name':body.source_filename or body.name,'schema':body.schema_,'dataset_id':body.dataset_id}|({'existing_template_id':existing.id if existing else None} if body.source_filename else {})
@app.post('/api/templates')
def create_template(body:TemplateInput,owner=Depends(auth)):
    if body.dataset_id:get_record(body.dataset_id,owner,'knowledge_base')
    check_schema(body.schema_)
    def save():
        existing=uploaded_template(body,owner)
        if existing:return update_template(existing.id,body,owner)
        name=body.source_filename or body.name
        r=new_record('template',owner,name,parent=body.dataset_id or '',data={'name':name,'schema':body.schema_,'instructions':body.instructions,'version':1,'dataset_id':body.dataset_id,'source_filename':body.source_filename})
        return representation(r)|store.json(r.ref)
    if not body.source_filename:return save()
    key=hashlib.sha256(json.dumps([owner,body.dataset_id or '',body.source_filename.casefold()]).encode()).hexdigest()
    with document_lock('template-import-'+key):return save()
@app.put('/api/templates/{id}')
def update_template(id:str,body:TemplateInput,owner=Depends(auth)):
    check_schema(body.schema_)
    get_record(id,owner,'template')
    with document_lock('template-'+id):
        r=get_record(id,owner,'template');version=r.version+1;ref=f'template/{id}/v{version}.json'
        if body.dataset_id and body.dataset_id!=r.parent_id:raise HTTPException(400,'Template dataset association cannot be changed. Import a new template for the destination dataset.')
        source_filename=body.source_filename or store.json(r.ref).get('source_filename')
        name=source_filename or body.name
        store.put_json(ref,{'name':name,'schema':body.schema_,'instructions':body.instructions,'version':version,'dataset_id':r.parent_id or None,'source_filename':source_filename})
        with Session.begin() as s:r=s.get(Record,id);r.version=version;r.ref=ref;r.name=name;r.updated_at=time.time()
        return representation(r)|store.json(ref)
@app.get('/api/templates/{id}/versions')
def template_versions(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'template');return [store.json(f'template/{id}/v{n}.json') for n in range(1,r.version+1)]
@app.get('/api/templates/{id}/export')
def export_template(id:str,version:int|None=None,owner=Depends(auth)):
    from urllib.parse import quote
    import re
    r=get_record(id,owner,'template');number=r.version if version is None else version
    if number<1 or number>r.version:raise HTTPException(404,'Template version not found')
    data=store.json(r.ref if number==r.version else f'template/{id}/v{number}.json')
    name=data.get('source_filename') or data['name'];safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','-',name.strip())[:100].rstrip('. ') or 'prompt-template'
    filename=data.get('source_filename') or f'{safe}-v{number}.json'
    disposition=f"attachment; filename=\"prompt-template-v{number}.json\"; filename*=UTF-8''{quote(filename,safe='')}"
    return Response(json.dumps({'name':name,'schema':data['schema'],'instructions':data.get('instructions','')},ensure_ascii=False,indent=2)+'\n',media_type='application/json',headers={'Content-Disposition':disposition})
class ExtractInput(BaseModel):
    document_ids:list[str]=Field(min_length=1,max_length=20)
    template_id:str
    dataset_id:str|None=None
    model_id:str|None=None
    allow_external:bool=False
    merge_records:bool=False
    display_name:str|None=Field(default=None,min_length=1,max_length=200)
    idempotency_key:str|None=Field(default=None,min_length=1,max_length=160)
    wait_for_index:bool=False
@app.get('/api/extractions')
def extractions(owner=Depends(auth)):
    output=[]
    for r in records(owner,'extraction'):
        data=store.json(r.ref)
        result=data.get('result')
        profile_count=len(result['records']) if isinstance(result,dict) and isinstance(result.get('records'),list) else (1 if result is not None else 0)
        output.append(representation(r)|{'profile_count':profile_count}|{key:data.get(key) for key in ('document_ids','template_id','template_version','review_status','model_selection','merge','merge_records')})
    return output
def extract_data_table(owner, dataset_id='', template_id=''):
    from . import extract_data, parquet_results
    if not template_id:raise HTTPException(400,'Choose one prompt template to view or export results.')
    if dataset_id:get_record(dataset_id,owner,'knowledge_base')
    if template_id:get_record(template_id,owner,'template')
    datasets={r.id:r.name for r in records(owner,'knowledge_base')}
    templates={r.id:r.name for r in records(owner,'template')}
    documents={r.id:r.name for r in records(owner,'document')}
    items=[]
    for r in records(owner,'extraction'):
        if r.status!='ready' or (dataset_id and r.parent_id!=dataset_id):continue
        try:
            data=store.json(r.ref)
            if template_id and data.get('template_id')!=template_id:continue
            data=parquet_results.load(data)
        except (ValueError,OSError,KeyError):
            raise HTTPException(503,'A saved extraction could not be read. Reload or retry before exporting; no partial results were returned.')
        if data.get('result') is None:raise HTTPException(409,'A completed extraction has no saved result.')
        items.append((r,data,datasets.get(r.parent_id,'Dataset unavailable'),
                      templates.get(data.get('template_id'),'Prompt unavailable'),
                      [documents[id] for id in data.get('document_ids',[]) if id in documents]))
    return extract_data.table(items)

@app.get('/api/extract-data')
def list_extract_data(dataset_id:str='',template_id:str=Query(...,min_length=1),offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),owner=Depends(auth)):
    data=extract_data_table(owner,dataset_id,template_id)
    return data|{'rows':data['rows'][offset:offset+limit],'offset':offset,'limit':limit}

@app.get('/api/extract-data/export')
def export_extract_data(dataset_id:str='',template_id:str=Query(...,min_length=1),format:str='xlsx',owner=Depends(auth)):
    from .extract_data import render
    if format not in ('xlsx','csv','json'):raise HTTPException(400,'Export format must be xlsx, csv or json')
    data=extract_data_table(owner,dataset_id,template_id)
    try:payload,media=render(data,format)
    except ValueError as error:raise HTTPException(400,str(error))
    return Response(payload,media_type=media,headers={'Content-Disposition':f'attachment; filename="aegis-extract-data.{format}"'})

@app.post('/api/extractions')
def create_extraction(body:ExtractInput,owner=Depends(auth)):
    key=hashlib.sha256(json.dumps([owner,body.idempotency_key or uid()]).encode()).hexdigest()
    with document_lock('extraction-submit-'+key):
        if body.idempotency_key:
            for existing in records(owner,'extraction'):
                previous=store.json(existing.ref)
                if previous.get('idempotency_key')==body.idempotency_key:
                    if previous.get('document_ids')!=body.document_ids or previous.get('template_id')!=body.template_id or previous.get('dataset_id')!=(body.dataset_id or existing.parent_id):raise HTTPException(409,'Idempotency key was already used for different extraction inputs')
                    if any(previous.get(key)!=body.model_dump().get(key) for key in ('model_id','display_name','merge_records','allow_external')):raise HTTPException(409,'Idempotency key was already used for different extraction inputs')
                    with Session() as session:job=session.scalar(select(Job).where(Job.target_id==existing.id).order_by(Job.created_at.desc()))
                    return representation(existing)|previous|{'job':job_repr(job) if job else None}
        return _create_extraction(body,owner)

def _create_extraction(body,owner):
    t=get_record(body.template_id,owner,'template');dataset,docs=routing.documents_scope(owner,body.dataset_id,body.document_ids)
    if t.parent_id and t.parent_id!=dataset.id:raise HTTPException(400,'Choose a prompt template belonging to the selected dataset.')
    snapshot=routing.execution_snapshot(dataset,'extraction',body.model_id)
    pending=[d for d in docs if d.status!='ready']
    if not pending:routing.require_indexes(docs,snapshot)
    external_check(body.allow_external,cfg=snapshot['settings'])
    if pending and (not body.wait_for_index or any(d.status not in ('queued','processing') for d in pending)):raise HTTPException(409,'Documents must be ready before extraction')
    for doc in docs:temporary_files.keep(doc.id)
    from . import merged_documents
    original_schema=store.json(t.ref)['schema'];merged=None;combined=None
    if len(docs)==1:
        value=merged_documents.manifest(docs[0].id)
        if value:merged=merged_documents.public(value)|{'document_id':docs[0].id}
    elif len(docs)>1 and body.wait_for_index:
        merged={'filename':body.display_name or 'merged-'+docs[0].name.rsplit('.',1)[0]+'-'+str(len(docs))+'-files',
            'logical':True,'source_count':len(docs),'sources':[{'key':str(n+1),'name':d.name,'size':d.size,'document_id':d.id} for n,d in enumerate(docs)]}
    elif len(docs)>1:
        try:
            filename,combined,value=merged_documents.prepare([(d.name,store.get(d.ref)) for d in docs])
            merged=merged_documents.public(value)
            for source,doc in zip(merged['sources'],docs):source['document_id']=doc.id
        except Exception as exc:raise HTTPException(422,'Could not create the merged file. Choose independent extraction or check the original files.') from exc
    schema=merged_documents.records_schema(original_schema,merged['sources']) if body.merge_records and merged else original_schema
    data=body.model_dump()|{'dataset_id':dataset.id,'model_selection':routing.public_selection(snapshot),'schema':schema,'record_schema':original_schema,'merge':merged,'template_version':t.version,'result':None,'sources':[]}
    name=body.display_name or (merged['filename'] if merged else docs[0].name.rsplit('.',1)[0])
    if merged:merged['filename']=name
    data['prompt_instructions']=store.json(t.ref).get('instructions','')
    data['schema']=dict(schema,description='\n'.join(filter(None,[schema.get('description',''),data['prompt_instructions']])))
    data['record_schema']=dict(original_schema,description='\n'.join(filter(None,[original_schema.get('description',''),data['prompt_instructions']])))
    r=new_record('extraction',owner,name,parent=dataset.id,data=data,status='queued')
    if combined is not None:store.put(f'extraction/{r.id}/merged-original',combined)
    j=enqueue(owner,'extract',r.id,body.allow_external,snapshot,initial_status='blocked' if pending else 'queued')
    if pending:
        with Session.begin() as session:session.get(Job,j.id).status='blocked'
        j.status='blocked'
        workflow.transition(j.id,'prepare','blocked')
    return representation(r)|data|{'job':job_repr(j)}
@app.get('/api/extractions/{id}')
def extraction(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'extraction')
    from .parquet_results import load
    try:data=load(store.json(r.ref)) if r.status=='ready' else store.json(r.ref)
    except (ValueError,OSError):raise HTTPException(503,'Saved Parquet could not be read. Retry loading; no draft was overwritten.')
    return representation(r)|data|{'extraction_id':r.id,'prompt_version':data.get('template_version'),'status_name':'completed' if r.status=='ready' else r.status,'output_url':f'/api/extractions/{id}/export?format=parquet' if data.get('output_reference') else None}

@app.get('/api/extractions/{id}/merged-file')
def merged_extraction_file(id:str,owner=Depends(auth)):
    from urllib.parse import quote
    r=get_record(id,owner,'extraction');data=store.json(r.ref);merged=data.get('merge')
    if not merged or merged.get('logical'):raise HTTPException(404,'This run retains separate originals. Download each source document.')
    raw=store.get(get_record(merged['document_id'],owner,'document').ref) if merged.get('document_id') else store.get(f'extraction/{id}/merged-original')
    return Response(raw,media_type='application/pdf' if merged['filename'].endswith('.pdf') else 'text/plain; charset=utf-8',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(merged['filename'])})
class ReviewInput(BaseModel):
    result:Any
    version:int=Field(ge=1)
@app.patch('/api/extractions/{id}')
def review_extraction(id:str,body:ReviewInput,owner=Depends(auth)):
    with document_lock(id):
        r=get_record(id,owner,'extraction');data=store.json(r.ref)
        from . import parquet_results
        try:data=parquet_results.load(data)
        except (ValueError,OSError):raise HTTPException(503,'Saved Parquet could not be read. Your edits are retained; retry loading.')
        if r.status!='ready':raise HTTPException(409,'Wait for extraction to complete')
        if body.version!=r.version:raise HTTPException(409,'This result changed in another session. Reload the latest saved version before saving; your draft is retained.')
        if data.get('review_status')=='reviewed':raise HTTPException(409,'This extraction is Reviewed and locked. Create a separate re-extraction to change its results.')
        try:validate(body.result,data['schema'])
        except ValidationError as error:raise HTTPException(400,'Result does not match the template schema at '+('/'.join(str(p) for p in error.path) or 'root'))
        try:json.dumps(body.result,ensure_ascii=False,allow_nan=False).encode('utf-8')
        except (ValueError,UnicodeError):raise HTTPException(400,'Saved values must contain valid Unicode and finite JSON numbers.')
        from .result_exports import leaves
        before=dict(leaves(data['result']));after=dict(leaves(body.result))
        changed={path for path in before.keys()|after.keys() if before.get(path)!=after.get(path)}
        prior_evidence=data.get('evidence',[])
        data['original_evidence']=data.get('original_evidence',prior_evidence)
        data['evidence']=[item for item in prior_evidence if not any((item.get('field') or item.get('path') or item.get('json_pointer') or '')==path or path.startswith((item.get('field') or item.get('path') or item.get('json_pointer') or '')+'/') for path in changed)]
        data.update(result=body.result,review_status='reviewed',review_locked=True,reviewed_at=time.time(),reviewed_by=owner,reviewed_extraction_version=r.version,evidence_notice='Edited fields are unverified; original quotes and source provenance are retained.',edited_fields=sorted(set(data.get('edited_fields',[]))|changed))
        try:data.update(parquet_results.persist(r.id,r.version+1,data))
        except ValueError as error:raise HTTPException(503,str(error))
        r=routing.write_version(r,data)
        return extraction(id,owner)

class ReextractInput(Consent):
    version:int=Field(ge=1)
    confirm_reviewed:bool=False

class ResumeExtraction(Consent):
    version:int=Field(ge=1)
    template_id:str

@app.post('/api/extractions/{id}/resume')
def resume_extraction(id:str,body:ResumeExtraction,owner=Depends(auth)):
    with document_lock('submit-'+id),document_lock(id):
        r=get_record(id,owner,'extraction')
        if r.status!='failed' or r.version!=body.version:raise HTTPException(409,'Reload the failed extraction before correcting its prompt')
        with Session() as session:
            if session.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running','blocked']))):raise HTTPException(409,'This extraction already has an active job')
        data=store.json(r.ref)
        if data.get('review_status')=='reviewed':raise HTTPException(409,'This extraction is Reviewed and locked. Create a separate result.')
        template=get_record(body.template_id,owner,'template')
        if template.parent_id and template.parent_id!=r.parent_id:raise HTTPException(400,'Choose a prompt in this extraction dataset')
        prompt=store.json(template.ref);check_schema(prompt['schema'])
        dataset,docs=routing.documents_scope(owner,r.parent_id,data['document_ids'])
        snapshot=routing.execution_snapshot(dataset,'extraction',data.get('model_id'))
        if all(d.status=='ready' for d in docs):routing.require_indexes(docs,snapshot)
        if any(d.status not in ('ready','queued','processing') for d in docs):raise HTTPException(409,'Correct/retry failed document indexing before resuming extraction')
        external_check(body.allow_external,cfg=snapshot['settings'])
        from .merged_documents import records_schema
        schema=records_schema(prompt['schema'],data['merge']['sources']) if data.get('merge_records') and data.get('merge') else prompt['schema']
        for key in ('output_reference','output_sha256','output_format','review_revision','retrieval','index_versions','record_results','record_progress'):
            data.pop(key,None)
        instructions=prompt.get('instructions','')
        data.update(template_id=template.id,template_version=template.version,prompt_instructions=instructions,
            schema=dict(schema,description='\n'.join(filter(None,[schema.get('description',''),instructions]))),
            record_schema=dict(prompt['schema'],description='\n'.join(filter(None,[prompt['schema'].get('description',''),instructions]))),
            result=None,evidence=[],sources=[],previous_version=r.version,model_selection=routing.public_selection(snapshot),allow_external=body.allow_external)
        r=routing.write_version(r,data)
        with Session.begin() as session:session.get(Record,id).status='queued';session.get(Record,id).error=''
        waiting=any(d.status!='ready' for d in docs)
        job=enqueue(owner,'extract',id,body.allow_external,snapshot,initial_status='blocked' if waiting else 'queued')
        return extraction(id,owner)|{'job':job_repr(job)}

@app.post('/api/extractions/{id}/reextract')
def reextract_result(id:str,body:ReextractInput,owner=Depends(auth)):
    if get_record(id,owner,'extraction').status!='ready':raise HTTPException(409,'Wait for extraction to complete.')
    with document_lock('submit-'+id),document_lock(id):
        r=get_record(id,owner,'extraction');data=store.json(r.ref)
        if r.status!='ready' or r.version!=body.version:raise HTTPException(409,'Reload the completed extraction before re-extracting.')
        if data.get('review_status')=='reviewed':raise HTTPException(409,'This extraction is Reviewed and locked. Use Re-extract from the Review list or Aegis Agent to create a separate result.')
        dataset,docs=routing.documents_scope(owner,r.parent_id,data['document_ids']);snapshot=routing.execution_snapshot(dataset,'extraction',data.get('model_id'));routing.require_indexes(docs,snapshot)
        if any(d.status!='ready' for d in docs):raise HTTPException(409,'Wait for document indexing to finish.')
        external_check(body.allow_external,cfg=snapshot['settings'])
        with Session() as s:
            if s.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):raise HTTPException(409,'An extraction job is already active')
        for key in ('reviewed_at','reviewed_by','evidence_notice','record_results','record_progress','output_reference','output_sha256','output_format','review_revision','retrieval','index_versions'):
            data.pop(key,None)
        data.update(result=None,evidence=[],original_evidence=[],edited_fields=[],sources=[],review_status='unreviewed',previous_version=r.version,allow_external=body.allow_external,model_selection=routing.public_selection(snapshot))
        r=routing.write_version(r,data)
        with Session.begin() as s:s.get(Record,id).status='queued'
        j=enqueue(owner,'extract',id,body.allow_external,snapshot)
        return representation(get_record(id,owner,'extraction'))|data|{'job':job_repr(j)}

@app.get('/api/extractions/{id}/versions')
def extraction_versions(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'extraction')
    return [{'version':n,**store.json(f'extraction/{id}/v{n}.json')} for n in range(1,r.version+1)]

@app.get('/api/extractions/{id}/source-evidence')
def extraction_source_evidence(id:str,version:int|None=Query(None,ge=1),record_index:int=Query(0,ge=0),owner=Depends(auth)):
    from . import review_sources
    import sys
    return review_sources.evidence(id,owner,version,record_index,sys.modules[__name__])
@app.get('/api/extractions/{id}/export')
def export_extraction(id:str,format:str='json',owner=Depends(auth)):
    r=get_record(id,owner,'extraction');data=store.json(r.ref)
    if r.status!='ready':raise HTTPException(409,'Extraction is not complete')
    from .parquet_results import load
    try:data=load(data)
    except (ValueError,OSError):raise HTTPException(503,'Persisted result could not be read; retry.')
    if format=='parquet':
        if not data.get('output_reference'):raise HTTPException(409,'This historical result predates Parquet. Save a review revision or re-extract to create Parquet.')
        return Response(store.get(data['output_reference']),media_type='application/vnd.apache.parquet',headers={'Content-Disposition':f'attachment; filename="extraction-v{r.version}.parquet"'})
    from .result_exports import render
    try:payload,media=render(r,data,format)
    except ValueError as error:raise HTTPException(400,str(error))
    return Response(payload,media_type=media,headers={'Content-Disposition':f'attachment; filename="extraction-v{r.version}.{format}"'})
@app.get('/api/jobs')
def jobs(owner=Depends(auth),ids:str=''):
    selected=set(ids.split(',')) if ids else None
    if selected and (len(ids)>5000 or len(selected)>120 or any(not id or len(id)>100 or not all(c.isalnum() or c in '-_' for c in id) for id in selected)):
        raise HTTPException(422,'Choose up to 120 job references.')
    return [job_repr(j) for j in access.jobs(owner) if selected is None or j.id in selected]
@app.post('/api/jobs/{id}/retry')
def retry_job(id:str,owner=Depends(auth)):
    initial=None
    with Session() as s:initial=s.get(Job,id)
    with Session() as s:
        if not access.job_allowed(initial,owner,s):raise HTTPException(404,'Not found')
    with document_lock('submit-'+initial.target_id),document_lock(initial.target_id),Session.begin() as s:
        j=s.get(Job,id)
        if not access.job_allowed(j,owner,s):raise HTTPException(404,'Not found')
        if j.status not in ('failed','cancelled'):raise HTTPException(409,'Only failed or cancelled jobs can be retried')
        target=s.get(Record,j.target_id)
        if not target or not access.allowed(target,owner,s):raise HTTPException(404,'Target deleted')
        if target.parent_id:routing.require_active(routing.owned(target.parent_id,owner,'knowledge_base'))
        if s.scalar(select(Job).where(Job.target_id==j.target_id,Job.id!=id,Job.status.in_(['queued','running']))):raise HTTPException(409,'Another job is already active for this target')
        if j.kind=='extract':
            data=store.json(target.ref)
            if data.get('review_status')=='reviewed':raise HTTPException(409,'This extraction is Reviewed and locked. Create a separate re-extraction.')
            docs=[s.get(Record,did) for did in data['document_ids']]
            waiting=any(d and d.status in ('queued','processing') for d in docs)
            if any(not d or d.status in ('failed','deleting') for d in docs):raise HTTPException(409,'Retry the failed source indexing jobs first')
        else:waiting=False
        j.status='blocked' if waiting else 'queued';j.progress=0;j.attempts=0;j.error='';j.lease_until=0;target.status='queued'
        target.error='';workflow.retry(id)
    from .queue_transport import get_transport
    get_transport(settings()['queue_provider']).notify(j.id)
    return job_repr(j)
@app.post('/api/jobs/{id}/cancel')
def cancel_job(id:str,owner=Depends(auth)):
    with Session.begin() as s:
        j=s.get(Job,id)
        if not access.job_allowed(j,owner,s):raise HTTPException(404,'Not found')
        if j.status not in ('queued','running'):raise HTTPException(409,'Job already finished')
        j.status='cancelled';j.lease_token='';j.error='Cancelled by user';r=s.get(Record,j.target_id)
        if r:r.status='cancelled'
        state=workflow.read(id)
        if state.get('current'):workflow.transition(id,state['current'],'cancelled','Cancelled by user')
    return job_repr(j)
@app.get('/api/index')
def inspect_index(document_id:str|None=None,dataset_id:str|None=None,owner=Depends(auth)):
    docs=[get_record(document_id,owner,'document')] if document_id else [d for d in records(owner,'document') if not dataset_id or d.parent_id==dataset_id];items=[]
    for d in docs:
        try:
            idx=store.json('documents/'+d.id+'/index.json');chunks=store.json('documents/'+d.id+'/chunks.json')
            items.append(idx|routing.document_public(d)|{'chunks':chunks['chunks'],'chunk_size':chunks['chunk_size'],'chunk_overlap':chunks['chunk_overlap']})
        except FileNotFoundError:items.append(routing.document_public(d)|{'chunks':[],'chunk_count':0,'requires_reindex':True})
    return {'documents':items,'embedding_fingerprint':None,'settings':{k:settings()[k] for k in ['embedding_provider','embedding_model','chunk_size','chunk_overlap']}}
@app.get('/api/settings')
def get_settings(owner=Depends(auth)):
    try:has_key=bool(api_key())
    except Exception:has_key=False
    try:has_oci_key=bool(oci_api_key())
    except Exception:has_oci_key=False
    return settings()|{'model_defaults':runtime_config.model_defaults(),'reranker':reranker.status(),'api_key_configured':has_key,'oci_api_key_configured':has_oci_key,'api_key':'********' if has_key else '', 'local_only':os.getenv('AEGIS_LOCAL_ONLY')=='true','ollama_endpoint':__import__('ags_app.ollama_provider',fromlist=['base_url']).base_url(),'mock_allowed':os.getenv('AEGIS_ALLOW_MOCK')=='true','requires_reindex_on_embedding_change':True,'openai_endpoint':'https://api.openai.com/v1','external_data_notice':'Selected external providers receive data: OpenAI receives query/document text for its model or embeddings; OCI receives originals for Object Storage and query/document text for managed indexing or generation. Explicit consent is required per processing operation.'}
@app.patch('/api/settings')
def save_settings(body:dict,owner=Depends(auth)):
    with document_lock('settings-config'):return _save_settings(body,owner)

def _save_settings(body,owner):
    if any(lock.locked() for lock in _locks.values()):raise HTTPException(409,'Wait for active chat responses before changing settings')
    permitted=set(DEFAULTS)|{'api_key','oci_api_key'}
    if set(body)-permitted:raise HTTPException(400,'Unknown setting or unsupported endpoint; provider endpoints are fixed for credential safety')
    with Session() as session:
        if session.scalar(select(Job).where(Job.status.in_(['queued','running'])).limit(1)):raise HTTPException(409,'Wait for or cancel active jobs before changing settings')
    cfg=settings()|{k:v for k,v in body.items() if k not in ('api_key','oci_api_key')}
    if cfg['model_provider'] not in ('mock','openai','oci','ollama') or cfg['embedding_provider'] not in ('mock','openai','sentence_transformers','ollama') or cfg['search_provider'] not in ('local','qdrant','oracle','oci') or cfg['storage_provider'] not in ('local','oci'):raise HTTPException(400,'Selected provider is not implemented; see capabilities')
    try:
        enforce_local_only(cfg)
        from .ollama_provider import local_model_name
        if cfg['model_provider']=='ollama':local_model_name(cfg['model'])
        if cfg['embedding_provider']=='ollama':local_model_name(cfg['embedding_model'])
    except (ValueError,RuntimeError) as exc:raise HTTPException(400,str(exc))
    if os.getenv('AEGIS_LOCAL_ONLY')=='true' and any(body.get(k) not in (None,'','********') for k in ('api_key','oci_api_key')):raise HTTPException(400,'Provider credentials are disabled in local-only mode.')
    if any(cfg[k]!=settings()[k] for k in ('oci_region','oci_project_id','oci_vector_store_id')):
        with Session() as session:known_docs=list(session.scalars(select(Record).where(Record.kind=='document')))
        for doc in known_docs:
            try:store.get('documents/'+doc.id+'/oci-index.json')
            except FileNotFoundError:continue
            # Dataset-managed indexes retain their own immutable cleanup destination.
            # Legacy indexes have no such guarantee and must keep their original global destination.
            try:store.get('documents/'+doc.id+'/index-execution.json')
            except FileNotFoundError:raise HTTPException(409,'Legacy OCI indexes require cleanup under the original project/region/vector store before changing that destination. Delete or migrate indexed documents first.')
    if cfg['queue_provider'] not in ('database','oci'):raise HTTPException(400,'Unsupported queue provider')
    if cfg['queue_provider']=='oci' and cfg['queue_provider']!=settings()['queue_provider']:
        from .queue_transport import get_transport
        try:get_transport('oci').test_connection()
        except Exception:raise HTTPException(400,'OCI Queue is not configured or reachable')
    if 'mock' in (cfg['model_provider'],cfg['embedding_provider']) and os.getenv('AEGIS_ALLOW_MOCK')!='true':raise HTTPException(400,'Mock providers require AEGIS_ALLOW_MOCK=true')
    for key,low,high in [('chunk_size',200,6000),('chunk_overlap',0,2000),('top_k',1,20),('timeout',5,1800),('max_upload_mb',1,100)]:
        if not isinstance(cfg[key],int) or not low<=cfg[key]<=high:raise HTTPException(400,'Invalid '+key)
    if cfg['chunk_overlap']>=cfg['chunk_size']:raise HTTPException(400,'Chunk overlap must be smaller than chunk size')
    if any(cfg[k]!=settings()[k] for k in ('storage_provider','oci_storage_namespace','oci_storage_bucket','oci_storage_prefix','oci_storage_region')):
        with Session() as session:
            if session.scalar(select(Record).where(Record.kind!='config_profile').limit(1)):raise HTTPException(409,'Storage switching requires an empty workspace or an operator-led data migration; existing objects cannot be silently moved')
        if cfg['storage_provider']=='oci':
            from .oci_adapters import OCIStorageAdapter
            try:oci_storage(cfg).test_connection()
            except Exception:raise HTTPException(400,'OCI Object Storage connection is not ready; configure server-side credentials, namespace and bucket')
    if cfg['storage_provider']=='oci' and any(cfg[k]!=settings()[k] for k in ('oci_storage_auth_mode','oci_storage_profile')):
        try:oci_storage(cfg).test_connection()
        except Exception:raise HTTPException(400,'OCI storage authentication check failed')
    if 'oci_api_key' in body and body['oci_api_key']!='********':
        if body['oci_api_key']:
            store.put('secrets/oci-provider.enc',secret_cipher().encrypt(body['oci_api_key'].encode()));store.delete('secrets/oci-provider.enc.disabled')
        else:
            store.put('secrets/oci-provider.enc.disabled',b'cleared');store.delete('secrets/oci-provider.enc')
    if 'api_key' in body and body['api_key']!='********':
        if body['api_key']:
            try:store.put('secrets/provider.enc',secret_cipher().encrypt(body['api_key'].encode()));store.delete('secrets/provider.enc.disabled')
            except ValueError as e:raise HTTPException(400,str(e))
        else:
            store.put('secrets/provider.enc.disabled',b'cleared');store.delete('secrets/provider.enc')
    store.put_json('configuration/settings.json',cfg);return get_settings(owner)
@app.get('/api/settings/export')
def export_settings(owner=Depends(auth)):return Response(json.dumps(settings(),indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="aegis-config.json"'})
@app.post('/api/settings/test')
def test_settings(owner=Depends(auth)):
    cfg=settings();status={'storage':False,'database':False,'vector_store':False,'openai_key_configured':False,'queue':False}
    try:
        if cfg['storage_provider']=='oci':oci_storage(cfg).test_connection();status['storage']=True
        else:store.put('diagnostics/probe',b'ok');status['storage']=store.get('diagnostics/probe')==b'ok';store.delete('diagnostics/probe')
    except Exception:pass
    try:
        with current_engine().connect() as c:c.execute(text('SELECT 1'));status['database']=True
    except Exception:pass
    try:
        if cfg['search_provider'] in ('qdrant','oracle'):providers.client().get_collections()
        elif cfg['search_provider']=='oci':providers.oci_vector().test_connection()
        status['vector_store']=True
    except Exception:pass
    try:
        from .queue_transport import get_transport
        get_transport(cfg['queue_provider']).test_connection();status['queue']=True
    except Exception:pass
    try:status['openai_key_configured']=bool(api_key())
    except Exception:pass
    return {'ok':all(status[k] for k in ('storage','database','vector_store','queue')),'checks':status,'note':'Storage, database, vector and queue checks may contact configured services. OpenAI key presence is not live authentication. No model inference was requested; OCI storage check is read-only bucket access, not a full write/delete validation.'}
@app.get('/api/capabilities')
def capabilities(owner=Depends(auth)):
    from . import ocr
    from .oci_adapters import capability_report
    from .queue_transport import get_transport
    return {'reranker':reranker.status(),'queue':get_transport(settings()['queue_provider']).status(),'local':{'storage':True,'qdrant':True,'postgresql':True,'openai_responses':True,'sentence_transformers':True,'ollama':True,'ocr':ocr.config()['enabled'],'streaming':True},'ocr':{'enabled':ocr.config()['enabled'],'model':ocr.config()['model'],'provider':'ollama','availability':'Check the container OCR smoke test; enabled does not imply a loaded model.'},'oci':capability_report(),'active':settings()}

CHAT_HEARTBEAT_SECONDS=10

@app.post('/api/conversations/{id}/messages/stream')
async def stream_message(id:str,body:MessageInput,request:Request,owner=Depends(auth)):
    import asyncio,re
    r=get_record(id,owner,'conversation');lock=_locks.setdefault(id,threading.Lock())
    if not lock.acquire(blocking=False):raise HTTPException(409,'A response is already in progress')
    try:
        data=store.json(r.ref);docs,snapshot=message_execution(body,owner,data);selection=routing.public_selection(snapshot)
        for doc in docs:temporary_files.keep(doc.id)
        data['document_ids']=[doc.id for doc in docs]
        sources=[]
        if not snapshot['settings'].get('general_chat'):
            with execution_context(snapshot['embedding_execution']):sources=await asyncio.to_thread(providers.search,body.text,owner,docs,settings()['top_k'])
        request_id=uid();store.put_json('executions/'+request_id+'.json',snapshot)
        data['messages'].append({'id':request_id,'role':'user','text':body.text,'created_at':time.time(),'model_selection':selection});store.put_json(r.ref,data)
    except HTTPException:lock.release();raise
    except Exception:lock.release();raise HTTPException(502,'Retrieval failed; check provider connectivity and indexed documents')
    async def events():
        from contextlib import suppress
        msg={'id':uid(),'role':'assistant','text':'','citations':[],'created_at':time.time(),'status':'streaming','mock':snapshot['settings']['model_provider']=='mock','model_selection':selection}
        iterator=None;pending=None;saved=False
        def persist():
            nonlocal saved
            used={int(x) for x in re.findall(r'\[(\d+)\]',msg['text'])}
            msg['citations']=[{'index':i+1,**source,'url':'/api/documents/'+source['document_id']+'/preview'} for i,source in enumerate(sources) if i+1 in used]
            if not saved:
                data['messages'].append(msg);store.put_json(r.ref,data);saved=True
        try:
            with execution_context(snapshot):
                iterator=providers.answer_stream_async(body.text,sources,data['messages'][:-1])
                while True:
                    if pending is None:pending=asyncio.create_task(anext(iterator))
                    ready,_=await asyncio.wait({pending},timeout=CHAT_HEARTBEAT_SECONDS)
                    if await request.is_disconnected():msg['status']='aborted';break
                    if not ready:
                        yield ': keep-alive\n\n';continue
                    try:piece=pending.result()
                    except StopAsyncIteration:pending=None;break
                    pending=None
                    msg['text']+=piece
                    yield 'event: delta\ndata: '+json.dumps({'text':piece})+'\n\n'
            if msg['status']=='streaming':msg['status']='completed'
            persist()
            yield 'event: done\ndata: '+json.dumps({'message':msg,'user_message':data['messages'][-2],'conversation_id':id})+'\n\n'
        except (GeneratorExit,asyncio.CancelledError):msg['status']='aborted';raise
        except Exception as exc:
            msg['status']='failed'
            local=snapshot['settings']['model_provider']=='ollama'
            detail=str(exc) if local and isinstance(exc,providers.ProviderError) else 'The model could not complete this response. Try again or check its connection.'
            code='provider_unavailable'
            if 'incomplete' in detail:code='incomplete_answer'
            elif 'context budget' in detail:code='context_limit'
            detail+=(' Any partial response has been kept for reference.' if msg['text'] else ' No answer was generated.')
            msg['error']={'code':code,'detail':detail,'retryable':True}
            persist()
            yield 'event: error\ndata: '+json.dumps({'detail':detail,'code':code,'message':msg,'user_message':data['messages'][-2]})+'\n\n'
        finally:
            try:
                if pending is not None:
                    pending.cancel()
                    with suppress(asyncio.CancelledError,Exception):await pending
                if iterator is not None:
                    with execution_context(snapshot):await iterator.aclose()
                persist()
            finally:lock.release()
    return StreamingResponse(events(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache, no-transform'})

@app.post('/api/index/search')
def diagnose_retrieval(body:MessageInput,owner=Depends(auth)):
    dataset,docs=routing.documents_scope(owner,body.dataset_id or body.kb_id,body.document_ids)
    snapshot=routing.execution_snapshot(dataset,'embedding');routing.require_indexes(docs,snapshot);external_check(body.allow_external,True,snapshot['settings'])
    ready=[d for d in docs if d.status=='ready'];started=time.monotonic()
    reranking={}
    try:
        with execution_context(snapshot):hits=providers.search(body.text,owner,ready,settings()['top_k'],diagnostics=reranking)
    except Exception:raise HTTPException(502,'Retrieval failed; verify the selected provider and matching index configuration')
    return {'matches':hits,'count':len(hits),'duration_ms':round((time.monotonic()-started)*1000),'scoped_documents':len(docs),'ready_documents':len(ready),'embedding_fingerprint':providers.fingerprint(snapshot['settings']),'top_k':snapshot['settings']['top_k'],'provider':snapshot['settings']['search_provider'],'reranking':reranking,'note':'Vector scores and reranker logits are not probabilities. With reranking enabled, results are sorted by rerank_score; score retains the original vector similarity. Only permitted ready documents and canonical stored excerpts are returned.'}

class ProfileInput(BaseModel):
    name:str=Field(min_length=1,max_length=120)

def profile_public(record):
    data=local_store.json(record.ref)
    return representation(record)|{'api_key_configured':data.get('api_key_configured',False),'oci_api_key_configured':data.get('oci_api_key_configured',False),'connection_credentials_configured':data.get('connection_credentials_configured',False),'registration_model_id':data.get('registration_model_id')}

def write_profile(owner,name,id=None):
    with document_lock('settings-config'):
        with document_lock('profile-'+(id or 'new')):return _write_profile(owner,name,id)

def _write_profile(owner,name,id=None):
    existing=get_record(id,owner,'config_profile') if id else None
    if existing and local_store.json(existing.ref).get('registration_model_id'):raise HTTPException(400,'Edit this connection through Model Registration.')
    id=id or uid();version=(existing.version+1) if existing else 1;ref=f'configuration/profiles/{id}/v{version}.json'
    data={'settings':settings(),'api_key_configured':False,'oci_api_key_configured':False,'saved_at':time.time()}
    for source,target,key in [('secrets/provider.enc','openai.enc','api_key_configured'),('secrets/oci-provider.enc','oci.enc','oci_api_key_configured')]:
        try:value=local_store.get(source)
        except FileNotFoundError:
            raw=api_key() if key=='api_key_configured' else oci_api_key()
            if not raw:continue
            try:value=secret_cipher().encrypt(raw.encode())
            except ValueError as e:raise HTTPException(400,str(e))
        local_store.put(f'secrets/profiles/{id}/v{version}/{target}',value);data[key]=True
    local_store.put_json(ref,data)
    with Session.begin() as session:
        if existing:r=session.get(Record,id);r.version=version;r.name=name;r.ref=ref;r.updated_at=time.time()
        else:r=Record(id=id,kind='config_profile',owner=owner,name=name,ref=ref,version=version,created_at=time.time(),updated_at=time.time());session.add(r)
    return profile_public(r)

@app.get('/api/settings/profiles')
def profiles(owner=Depends(auth)):return [profile_public(r) for r in records(owner,'config_profile')]
@app.post('/api/settings/profiles')
def create_profile(body:ProfileInput,owner=Depends(auth)):return write_profile(owner,body.name)
@app.put('/api/settings/profiles/{id}')
def revise_profile(id:str,body:ProfileInput,owner=Depends(auth)):return write_profile(owner,body.name,id)
@app.post('/api/settings/profiles/{id}/activate')
def activate_profile(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'config_profile');data=local_store.json(r.ref);cfg=data['settings'].copy()
    if data.get('registration_model_id'):raise HTTPException(400,'Apply registered models through the dataset Model Mapping screen.')
    for target,key in [('openai.enc','api_key'),('oci.enc','oci_api_key')]:
        try:
            encrypted=local_store.get(f'secrets/profiles/{id}/v{r.version}/{target}');cfg[key]=secret_cipher().decrypt(encrypted).decode()
        except FileNotFoundError:cfg[key]=''
        except Exception:raise HTTPException(400,'Profile credentials cannot be decrypted with the active master key')
    return save_settings(cfg,owner)
@app.get('/api/settings/profiles/{id}/export')
def export_profile(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'config_profile');data=local_store.json(r.ref)
    return Response(json.dumps({'name':r.name,'version':r.version,'settings':data['settings']},indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="aegis-profile.json"'})


routing.install_routes(app,auth,write_profile)
from . import dataset_lifecycle
dataset_lifecycle.install(app,auth)
from . import model_registration
model_registration.install_routes(app,auth)

from .browser_recovery import router as browser_recovery_router
app.include_router(browser_recovery_router)


@app.get('/api/local-models')
def local_models(owner=Depends(auth)):
    from . import ollama_provider
    return ollama_provider.installed()

@app.post('/api/datasets/{id}/local-models')
def configure_local_models(id:str,owner=Depends(auth)):
    """Explicit setup convenience: preserve existing embedding selection/generation."""
    cfg=settings();dataset=get_record(id,owner,'knowledge_base');routing.require_active(dataset)
    if cfg['model_provider']!='ollama' or cfg['embedding_provider']!='ollama' or cfg['search_provider']!='local' or cfg['storage_provider']!='local':raise HTTPException(409,'Local setup requires local Ollama, embeddings, search and storage in deployment settings.')
    from .ollama_provider import installed
    names={m['name'] for m in installed()['models']}
    chat_names=[name for name in ('qwen3:4b','smollm2:1.7b-instruct-q4_K_M') if name in names]
    nomic=next((name for name in ('nomic-embed-text:latest','nomic-embed-text') if name in names),None)
    if not chat_names or not nomic:raise HTTPException(409,'Install Qwen3 or SmolLM2 and Nomic locally first. No model is downloaded by this action.')
    with document_lock('dataset-'+id):
        dataset=get_record(id,owner,'knowledge_base');existing=routing.routing_public(dataset)
        profile=write_profile(owner,'Local Ollama models')
        mappings=existing['mappings'].copy();selected=[]
        catalog=[routing.model_public(r) for r in routing.rows(owner,'model')]
        def choose(name,capabilities,label):
            model=next((m for m in catalog if m['provider']=='ollama' and m['provider_model']==name and m['capabilities']==capabilities and m.get('enabled',True)),None)
            if not model:
                r=routing.create('model',owner,label,{'name':label,'connection_profile_id':profile['id'],'provider_model':name,'capabilities':capabilities,'enabled':True});model=routing.model_public(r)
            if not any(m['model_id']==model['id'] for m in mappings):mappings.append({'model_id':model['id'],'enabled':True})
            return model['id']
        for name in chat_names:selected.append(choose(name,['chat'],'Qwen3 chat' if name.startswith('qwen3') else 'SmolLM2 chat'))
        extraction=existing['default_extraction_model_id'] or choose(chat_names[0],['extraction'],'Local extraction')
        embedding=existing['embedding_model_id'] or choose(nomic,['embedding'],'Nomic embeddings')
        updated=routing.save_mappings(dataset,routing.MappingInput(mappings=mappings,default_chat_model_id=existing['default_chat_model_id'] or selected[0],default_extraction_model_id=extraction,embedding_model_id=embedding))
        return routing.dataset_public(updated)

temporary_files.install(app,auth)

from . import temporary_chat
temporary_chat.install(app,auth)

from . import runtime_config
runtime_config.install(app,auth)

from . import agent_workspace
agent_workspace.install(app, auth, __import__(__name__, fromlist=['app']))
from .ags_agent import dataset_chat
dataset_chat.install(app, auth, __import__(__name__, fromlist=['app']))
from .ags_agent import extraction_rerun
extraction_rerun.install(app, auth, __import__(__name__, fromlist=['app']))
from . import agent_onboarding
agent_onboarding.install(app, auth)

from . import knowledge
knowledge.install(app, auth)

from . import metadata_relationships
metadata_relationships.install(app, auth)

from . import api_documentation
api_documentation.install(app,auth)
