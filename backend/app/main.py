import os, time, hashlib, secrets, json, io, csv, threading
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from jsonschema import Draft202012Validator, validate, ValidationError
from .core import *
from . import providers, reranker, workflow, temporary_files, dataset_models as routing

@asynccontextmanager
async def lifespan(app):
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
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('ALLOWED_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['Content-Type','X-CSRF-Token','Authorization'])
@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request);response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='no-store';return response

def auth(request:Request):
    token=request.cookies.get('aegis_session','');bearer=request.headers.get('authorization','')
    if bearer.startswith('Bearer '):token=bearer[7:]
    if not token:raise HTTPException(401,'Sign in required')
    with Session() as s:
        login=s.get(Login,hashlib.sha256(token.encode()).hexdigest())
        if not login or login.expires<time.time():raise HTTPException(401,'Session expired')
        if request.method not in ('GET','HEAD','OPTIONS') and not bearer.startswith('Bearer ') and not secrets.compare_digest(request.headers.get('x-csrf-token',''),login.csrf):raise HTTPException(403,'Invalid CSRF token')
        return login.owner

def get_record(id,owner,kind=None):
    with Session() as s:r=s.get(Record,id)
    if not r or r.owner!=owner or (kind and r.kind!=kind):raise HTTPException(404,'Not found')
    return r

def records(owner,kind):
    with Session() as s:return list(s.scalars(select(Record).where(Record.owner==owner,Record.kind==kind).order_by(Record.created_at.desc())))
def new_record(kind,owner,name='',parent='',data=None,status='ready'):
    id=uid();ref=f'{kind}/{id}/v1.json'
    if data is not None:store.put_json(ref,data)
    r=Record(id=id,kind=kind,owner=owner,name=name,parent_id=parent,ref=ref,status=status,created_at=time.time(),updated_at=time.time())
    with Session.begin() as s:s.add(r)
    return r

def enqueue(owner,kind,target,allow_external=False,snapshot=None):
    j=Job(id=uid(),owner=owner,kind=kind,target_id=target,status='queued',created_at=time.time(),updated_at=time.time())
    store.put_json('jobs/'+j.id+'.json',{'allow_external':allow_external,**({'execution':snapshot} if snapshot else {})})
    workflow.initialize(j.id,kind)
    with Session.begin() as s:s.add(j)
    from .queue_transport import get_transport
    get_transport(settings()['queue_provider']).notify(j.id)
    return j

def external_check(consent,embedding=False,cfg=None):
    cfg=cfg or settings();external=(cfg['embedding_provider'] in ('openai','registered') or cfg['search_provider']=='oci' or cfg['storage_provider']=='oci') if embedding else cfg['model_provider'] in ('openai','oci','registered') or cfg['embedding_provider'] in ('openai','registered') or cfg['search_provider']=='oci'
    if external and not consent:raise HTTPException(409,'This action sends document text or your query to the configured external provider. Confirm external data transmission first.')
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
            s.add(User(id='administrator',username=body.username,password_hash=password_hash(body.password)))
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
            user={'id':u.id,'username':u.username}
    _login_attempts.pop(client,None)
    response.set_cookie('aegis_session',token,httponly=True,secure=os.getenv('COOKIE_SECURE','false')=='true',samesite='strict',max_age=43200,path='/')
    return {'user':user,'csrf_token':csrf}
@app.get('/api/auth/me')
def me(request:Request,owner=Depends(auth)):
    with Session() as s:
        u=s.get(User,owner);token=request.cookies.get('aegis_session','');l=s.get(Login,hashlib.sha256(token.encode()).hexdigest())
        return {'user':{'id':u.id,'username':u.username},'csrf_token':l.csrf if l else ''}
@app.post('/api/auth/logout')
def logout(request:Request,response:Response,owner=Depends(auth)):
    with Session.begin() as s:
        row=s.get(Login,hashlib.sha256(request.cookies.get('aegis_session','').encode()).hexdigest())
        if row:s.delete(row)
    response.delete_cookie('aegis_session');return {'ok':True}
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/ready')
def ready():
    try:
        with engine.connect() as c:c.execute(text('SELECT 1'))
        if settings()['search_provider']=='qdrant':providers.client().get_collections()
        if settings()['search_provider']=='oci':providers.oci_vector().test_connection()
        from . import reranker
        if reranker.enabled():reranker.load()
        return {'status':'ready','database':True,'vector_store':True,'reranker':reranker.status()}
    except Exception:raise HTTPException(503,'Database, vector store or configured reranker unavailable')
@app.get('/api/overview')
def overview(owner=Depends(auth)):
    docs=records(owner,'document')
    with Session() as s:jobs=list(s.scalars(select(Job).where(Job.owner==owner)))
    return {'documents':len(docs),'ready':sum(d.status=='ready' for d in docs),'jobs':sum(j.status in ('queued','running') for j in jobs),'knowledge_bases':len(records(owner,'knowledge_base')),'failed':sum(d.status=='failed' for d in docs)}
class KBInput(BaseModel):name:str=Field(min_length=1,max_length=200);description:str='';active:bool=Field(default=True,strict=True)
@app.get('/api/knowledge-bases')
def kbs(owner=Depends(auth)):return [routing.dataset_public(r) for r in records(owner,'knowledge_base')]
@app.post('/api/knowledge-bases')
def create_kb(body:KBInput,owner=Depends(auth)):return routing.dataset_public(new_record('knowledge_base',owner,body.name,data=body.model_dump()|routing.ROUTING_DEFAULTS|{'routing_version':1}))
@app.get('/api/documents')
def documents(kb_id:str|None=None,dataset_id:str|None=None,owner=Depends(auth)):
    scope=dataset_id or kb_id
    if scope:get_record(scope,owner,'knowledge_base')
    snapshots={}
    return [routing.document_public(d,snapshots) for d in records(owner,'document') if not scope or d.parent_id==scope]
@app.post('/api/documents/upload')
async def upload(files:list[UploadFile]=File(...),kb_id:str=Form(''),dataset_id:str=Form(''),allow_external:bool=Form(False),temporary_session_id:str=Form(''),owner=Depends(auth)):
    if temporary_session_id:raise HTTPException(409,'Temporary chat uploads use /api/temporary-chat/documents and never create an index.')
    if kb_id and dataset_id and kb_id!=dataset_id:raise HTTPException(400,'Conflicting dataset identifiers')
    kb_id=dataset_id or kb_id
    if not kb_id:raise HTTPException(409,'Create or choose a dataset and map its embedding model before uploading.')
    dataset=get_record(kb_id,owner,'knowledge_base');snapshot=routing.execution_snapshot(dataset,'embedding')
    if len(files)>20:raise HTTPException(400,'Upload at most 20 files at once')
    external_check(allow_external,True,snapshot['settings']);result=[];jobs=[]
    for file in files:
        name=(file.filename or 'document').replace('\\','/').split('/')[-1][:200]
        if name.rsplit('.',1)[-1].lower() not in ('txt','pdf','docx'):raise HTTPException(400,'Only PDF, DOCX and UTF-8 TXT files are supported')
        limit=settings()['max_upload_mb']*1024*1024;raw=await file.read(limit+1)
        if len(raw)>limit:raise HTTPException(413,'File exceeds configured upload size')
        if not raw:raise HTTPException(400,'Empty file')
        id=uid();ref='documents/'+id+'/original';store.put(ref,raw)
        r=Record(id=id,kind='document',owner=owner,name=name,ref=ref,parent_id=kb_id,status='queued',size=len(raw),created_at=time.time(),updated_at=time.time())
        with Session.begin() as s:s.add(r)
        j=enqueue(owner,'index',id,allow_external,snapshot);result.append(routing.document_public(r));jobs.append(job_repr(j))
    return {'documents':result,'jobs':jobs}
@app.get('/api/documents/{id}')
def document(id:str,owner=Depends(auth)):return routing.document_public(get_record(id,owner,'document'))
@app.get('/api/documents/{id}/preview')
def preview(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'document')
    try:data=store.json('documents/'+id+'/chunks.json');return {'text':'\n\n'.join(c['text'] for c in data['chunks']),'chunks':data['chunks'],'document':representation(r)}
    except FileNotFoundError:return {'text':'Text is not available until processing completes.','chunks':[],'document':representation(r)}
@app.get('/api/documents/{id}/download')
def download(id:str,owner=Depends(auth)):
    from urllib.parse import quote
    r=get_record(id,owner,'document');return Response(store.get(r.ref),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r.name)})
@app.get('/api/documents/{id}/source')
def source_document(id:str,owner=Depends(auth)):
    from urllib.parse import quote
    r=get_record(id,owner,'document');ext=r.name.rsplit('.',1)[-1].lower()
    if ext not in ('pdf','txt'):raise HTTPException(415,'Inline original preview supports PDF and UTF-8 TXT. Download DOCX to review its original layout.')
    return Response(store.get(r.ref),media_type='application/pdf' if ext=='pdf' else 'text/plain; charset=utf-8',headers={'Content-Disposition':"inline; filename*=UTF-8''"+quote(r.name),'Content-Security-Policy':"sandbox"})
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
        for suffix in ['original','parsed.json','chunks.json','index.json','index-execution.json','retention.json']:store.delete('documents/'+id+'/'+suffix)
        for n in range(1,r.version+1):
            for suffix in ('parsed.json','chunks.json','index.json','index-execution.json'):store.delete(f'documents/{id}/versions/v{n}/{suffix}')
        with Session.begin() as s:s.delete(s.get(Record,id))
    return {'ok':True}
class ConversationInput(BaseModel):title:str='New conversation';kb_id:str='';dataset_id:str='';document_ids:list[str]=Field(default_factory=list)
@app.get('/api/conversations')
def conversations(owner=Depends(auth)):return [representation(r)|{'title':r.name} for r in records(owner,'conversation')]
@app.post('/api/conversations')
def create_conversation(body:ConversationInput,owner=Depends(auth)):
    dataset_id=body.dataset_id or body.kb_id
    if body.dataset_id and body.kb_id and body.dataset_id!=body.kb_id:raise HTTPException(400,'Conflicting dataset identifiers')
    if dataset_id or body.document_ids:dataset,_=routing.documents_scope(owner,dataset_id,body.document_ids);dataset_id=dataset.id
    for id in body.document_ids:temporary_files.keep(id)
    r=new_record('conversation',owner,body.title[:200],parent=dataset_id,data=body.model_dump()|{'dataset_id':dataset_id,'kb_id':dataset_id,'messages':[]});return representation(r)|store.json(r.ref)
@app.get('/api/conversations/{id}')
def conversation(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'conversation');return representation(r)|store.json(r.ref)
class MessageInput(BaseModel):text:str=Field(min_length=1,max_length=12000);document_ids:list[str]|None=None;kb_id:str|None=None;dataset_id:str|None=None;model_id:str|None=None;allow_external:bool=False
_locks={}
def message_execution(body,owner,data):
    if body.dataset_id and body.kb_id and body.dataset_id!=body.kb_id:raise HTTPException(400,'Conflicting dataset identifiers')
    ids=body.document_ids if body.document_ids is not None else data.get('document_ids',[])
    dataset_id=body.dataset_id if body.dataset_id is not None else body.kb_id if body.kb_id is not None else data.get('dataset_id') or data.get('kb_id','')
    pinned=data.get('dataset_id') or data.get('kb_id')
    if not pinned and data.get('document_ids'):
        try:previous,_=routing.documents_scope(owner,'',data['document_ids']);pinned=previous.id
        except HTTPException:raise HTTPException(409,'Start a new conversation scoped to one dataset.')
    if data.get('messages') and not pinned:raise HTTPException(409,'Start a new conversation scoped to one dataset.')
    dataset,docs=routing.documents_scope(owner,dataset_id,ids)
    if pinned and dataset.id!=pinned:raise HTTPException(409,'A conversation stays within its original dataset. Start a new conversation for another dataset.')
    snapshot=routing.execution_snapshot(dataset,'chat',body.model_id);routing.require_indexes(docs,snapshot)
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
class TemplateInput(BaseModel):name:str=Field(min_length=1,max_length=200);schema_:dict=Field(alias='schema');dataset_id:str|None=None
def check_schema(schema):
    try:Draft202012Validator.check_schema(schema)
    except Exception:raise HTTPException(400,'Invalid JSON Schema')
    if schema.get('type')!='object':raise HTTPException(400,'Extraction schema must be an object')
    def safe_refs(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key in ('$ref','$dynamicRef') and (not isinstance(value,str) or not value.startswith('#')):raise HTTPException(400,'Only local JSON Schema references are supported')
                safe_refs(value)
        elif isinstance(node,list):
            for child in node:safe_refs(child)
    safe_refs(schema)
    def strict(node):
        if not isinstance(node,dict):return
        if node.get('type')=='object':
            if node.get('additionalProperties') is not False:raise HTTPException(400,'Strict extraction requires additionalProperties:false on every object')
            if set(node.get('required',[]))!=set(node.get('properties',{})):raise HTTPException(400,'Strict extraction requires every property in required. Use a nullable type for optional values.')
        for key,value in node.items():
            if key in ('properties','$defs','definitions'):
                for child in value.values():strict(child)
            elif key=='items':strict(value)
            elif key in ('anyOf','oneOf','allOf'):
                for child in value:strict(child)
    strict(schema)
@app.get('/api/templates')
def templates(owner=Depends(auth)):return [representation(r)|store.json(r.ref) for r in records(owner,'template')]
@app.post('/api/templates/validate')
def validate_template(body:TemplateInput,owner=Depends(auth)):
    if body.dataset_id:get_record(body.dataset_id,owner,'knowledge_base')
    check_schema(body.schema_)
    return {'valid':True,'name':body.name,'schema':body.schema_,'dataset_id':body.dataset_id}
@app.post('/api/templates')
def create_template(body:TemplateInput,owner=Depends(auth)):
    if body.dataset_id:get_record(body.dataset_id,owner,'knowledge_base')
    check_schema(body.schema_);r=new_record('template',owner,body.name,parent=body.dataset_id or '',data={'name':body.name,'schema':body.schema_,'version':1,'dataset_id':body.dataset_id});return representation(r)|store.json(r.ref)
@app.put('/api/templates/{id}')
def update_template(id:str,body:TemplateInput,owner=Depends(auth)):
    check_schema(body.schema_);r=get_record(id,owner,'template');version=r.version+1;ref=f'template/{id}/v{version}.json'
    if body.dataset_id and body.dataset_id!=r.parent_id:raise HTTPException(400,'Template dataset association cannot be changed. Import a new template for the destination dataset.')
    store.put_json(ref,{'name':body.name,'schema':body.schema_,'version':version,'dataset_id':r.parent_id or None})
    with Session.begin() as s:r=s.get(Record,id);r.version=version;r.ref=ref;r.name=body.name;r.updated_at=time.time()
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
    name=data['name'];safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','-',name.strip())[:100].rstrip('. ') or 'prompt-template'
    filename=f'{safe}-v{number}.json'
    disposition=f"attachment; filename=\"prompt-template-v{number}.json\"; filename*=UTF-8''{quote(filename,safe='')}"
    return Response(json.dumps({'name':name,'schema':data['schema']},ensure_ascii=False,indent=2)+'\n',media_type='application/json',headers={'Content-Disposition':disposition})
class ExtractInput(BaseModel):document_ids:list[str]=Field(min_length=1,max_length=20);template_id:str;dataset_id:str|None=None;model_id:str|None=None;allow_external:bool=False
@app.get('/api/extractions')
def extractions(owner=Depends(auth)):
    output=[]
    for r in records(owner,'extraction'):
        data=store.json(r.ref)
        output.append(representation(r)|{key:data.get(key) for key in ('document_ids','template_id','template_version','review_status','model_selection')})
    return output
@app.post('/api/extractions')
def create_extraction(body:ExtractInput,owner=Depends(auth)):
    t=get_record(body.template_id,owner,'template');dataset,docs=routing.documents_scope(owner,body.dataset_id,body.document_ids)
    if t.parent_id and t.parent_id!=dataset.id:raise HTTPException(400,'Choose a prompt template belonging to the selected dataset.')
    snapshot=routing.execution_snapshot(dataset,'extraction',body.model_id);routing.require_indexes(docs,snapshot)
    external_check(body.allow_external,cfg=snapshot['settings'])
    if any(d.status!='ready' for d in docs):raise HTTPException(409,'Documents must be ready before extraction')
    for doc in docs:temporary_files.keep(doc.id)
    data=body.model_dump()|{'dataset_id':dataset.id,'model_selection':routing.public_selection(snapshot),'schema':store.json(t.ref)['schema'],'template_version':t.version,'result':None,'sources':[]}
    r=new_record('extraction',owner,t.name,parent=dataset.id,data=data,status='queued');j=enqueue(owner,'extract',r.id,body.allow_external,snapshot)
    return representation(r)|data|{'job':job_repr(j)}
@app.get('/api/extractions/{id}')
def extraction(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'extraction');return representation(r)|store.json(r.ref)
class ReviewInput(BaseModel):
    result:Any
    version:int=Field(ge=1)
@app.patch('/api/extractions/{id}')
def review_extraction(id:str,body:ReviewInput,owner=Depends(auth)):
    with document_lock(id):
        r=get_record(id,owner,'extraction');data=store.json(r.ref)
        if r.status!='ready':raise HTTPException(409,'Wait for extraction to complete')
        if body.version!=r.version:raise HTTPException(409,'This result changed in another session. Reload the latest saved version before saving; your draft is retained.')
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
        data.update(result=body.result,review_status='reviewed',reviewed_at=time.time(),reviewed_by=owner,evidence_notice='Edited fields are unverified; original quotes and source provenance are retained.',edited_fields=sorted(set(data.get('edited_fields',[]))|changed))
        r=routing.write_version(r,data)
        return representation(r)|data

class ReextractInput(Consent):
    version:int=Field(ge=1)
    confirm_reviewed:bool=False
@app.post('/api/extractions/{id}/reextract')
def reextract_result(id:str,body:ReextractInput,owner=Depends(auth)):
    if get_record(id,owner,'extraction').status!='ready':raise HTTPException(409,'Wait for extraction to complete.')
    with document_lock('submit-'+id),document_lock(id):
        r=get_record(id,owner,'extraction');data=store.json(r.ref)
        if r.status!='ready' or r.version!=body.version:raise HTTPException(409,'Reload the completed extraction before re-extracting.')
        if data.get('review_status')=='reviewed' and not body.confirm_reviewed:raise HTTPException(409,'Confirm before replacing reviewed edits. The saved version is preserved.')
        dataset,docs=routing.documents_scope(owner,r.parent_id,data['document_ids']);snapshot=routing.execution_snapshot(dataset,'extraction',data.get('model_id'));routing.require_indexes(docs,snapshot)
        if any(d.status!='ready' for d in docs):raise HTTPException(409,'Wait for document indexing to finish.')
        external_check(body.allow_external,cfg=snapshot['settings'])
        with Session() as s:
            if s.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):raise HTTPException(409,'An extraction job is already active')
        for key in ('reviewed_at','reviewed_by','evidence_notice'):
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
@app.get('/api/extractions/{id}/export')
def export_extraction(id:str,format:str='json',owner=Depends(auth)):
    r=get_record(id,owner,'extraction');data=store.json(r.ref)
    if r.status!='ready':raise HTTPException(409,'Extraction is not complete')
    from .result_exports import render
    try:payload,media=render(r,data,format)
    except ValueError as error:raise HTTPException(400,str(error))
    return Response(payload,media_type=media,headers={'Content-Disposition':f'attachment; filename="extraction-v{r.version}.{format}"'})
@app.get('/api/jobs')
def jobs(owner=Depends(auth)):
    with Session() as s:return [job_repr(j) for j in s.scalars(select(Job).where(Job.owner==owner).order_by(Job.created_at.desc()))]
@app.post('/api/jobs/{id}/retry')
def retry_job(id:str,owner=Depends(auth)):
    initial=None
    with Session() as s:initial=s.get(Job,id)
    if not initial or initial.owner!=owner:raise HTTPException(404,'Not found')
    with document_lock('submit-'+initial.target_id),Session.begin() as s:
        j=s.get(Job,id)
        if not j or j.owner!=owner:raise HTTPException(404,'Not found')
        if j.status not in ('failed','cancelled'):raise HTTPException(409,'Only failed or cancelled jobs can be retried')
        target=s.get(Record,j.target_id)
        if not target or target.owner!=owner:raise HTTPException(404,'Target deleted')
        if target.parent_id:routing.require_active(routing.owned(target.parent_id,owner,'knowledge_base'))
        if s.scalar(select(Job).where(Job.target_id==j.target_id,Job.id!=id,Job.status.in_(['queued','running']))):raise HTTPException(409,'Another job is already active for this target')
        j.status='queued';j.progress=0;j.attempts=0;j.error='';j.lease_until=0;target.status='queued'
        target.error='';workflow.retry(id)
    from .queue_transport import get_transport
    get_transport(settings()['queue_provider']).notify(j.id)
    return job_repr(j)
@app.post('/api/jobs/{id}/cancel')
def cancel_job(id:str,owner=Depends(auth)):
    with Session.begin() as s:
        j=s.get(Job,id)
        if not j or j.owner!=owner:raise HTTPException(404,'Not found')
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
    return settings()|{'reranker':reranker.status(),'api_key_configured':has_key,'oci_api_key_configured':has_oci_key,'api_key':'********' if has_key else '', 'local_only':os.getenv('AEGIS_LOCAL_ONLY')=='true','ollama_endpoint':__import__('app.ollama_provider',fromlist=['base_url']).base_url(),'mock_allowed':os.getenv('AEGIS_ALLOW_MOCK')=='true','requires_reindex_on_embedding_change':True,'openai_endpoint':'https://api.openai.com/v1','external_data_notice':'Selected external providers receive data: OpenAI receives query/document text for its model or embeddings; OCI receives originals for Object Storage and query/document text for managed indexing or generation. Explicit consent is required per processing operation.'}
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
    if cfg['model_provider'] not in ('mock','openai','oci','ollama') or cfg['embedding_provider'] not in ('mock','openai','sentence_transformers','ollama') or cfg['search_provider'] not in ('local','qdrant','oci') or cfg['storage_provider'] not in ('local','oci'):raise HTTPException(400,'Selected provider is not implemented; see capabilities')
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
    for key,low,high in [('chunk_size',200,6000),('chunk_overlap',0,2000),('top_k',1,20),('timeout',5,180),('max_upload_mb',1,100)]:
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
        with engine.connect() as c:c.execute(text('SELECT 1'));status['database']=True
    except Exception:pass
    try:
        if cfg['search_provider']=='qdrant':providers.client().get_collections()
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
    from .oci_adapters import capability_report
    from .queue_transport import get_transport
    return {'reranker':reranker.status(),'queue':get_transport(settings()['queue_provider']).status(),'local':{'storage':True,'qdrant':True,'postgresql':True,'openai_responses':True,'sentence_transformers':True,'ollama':True,'ocr':False,'streaming':True},'oci':capability_report(),'active':settings()}

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

from . import api_documentation
api_documentation.install(app,auth)
