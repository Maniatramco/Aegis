import os, time, hashlib, secrets, json, io, csv, threading
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from jsonschema import Draft202012Validator, validate, ValidationError
from .core import *
from . import providers, dataset_models as routing

@asynccontextmanager
async def lifespan(app):
    init();yield
app=FastAPI(title='Aegis storage-first document intelligence',version='0.1.0',lifespan=lifespan)
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
    with Session.begin() as s:s.add(j)
    from .queue_transport import get_transport
    get_transport(settings()['queue_provider']).notify(j.id)
    return j

def external_check(consent,embedding=False,cfg=None):
    cfg=cfg or settings();external=(cfg['embedding_provider']=='openai' or cfg['search_provider']=='oci' or cfg['storage_provider']=='oci') if embedding else cfg['model_provider'] in ('openai','oci') or cfg['embedding_provider']=='openai' or cfg['search_provider']=='oci'
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
        return {'status':'ready','database':True,'vector_store':True}
    except Exception:raise HTTPException(503,'Database or vector store unavailable')
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
    return [routing.document_public(d) for d in records(owner,'document') if not scope or d.parent_id==scope]
@app.post('/api/documents/upload')
async def upload(files:list[UploadFile]=File(...),kb_id:str=Form(''),dataset_id:str=Form(''),allow_external:bool=Form(False),owner=Depends(auth)):
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
class Consent(BaseModel):allow_external:bool=False
@app.post('/api/documents/{id}/reindex')
def reindex(id:str,body:Consent,owner=Depends(auth)):
    doc=get_record(id,owner,'document');dataset,_=routing.documents_scope(owner,doc.parent_id,[id]);snapshot=routing.execution_snapshot(dataset,'embedding');external_check(body.allow_external,True,snapshot['settings'])
    with Session.begin() as s:
        if s.scalar(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):raise HTTPException(409,'An indexing job is already active')
        r=s.get(Record,id);r.status='queued';r.error=''
    return job_repr(enqueue(owner,'index',id,body.allow_external,snapshot))
@app.delete('/api/documents/{id}')
def delete_document(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'document')
    with Session.begin() as s:
        for j in s.scalars(select(Job).where(Job.target_id==id,Job.status.in_(['queued','running']))):j.status='cancelled';j.lease_token=''
        s.get(Record,id).status='deleting'
    with document_lock(id):
        try:providers.delete_vectors(id)
        except Exception:raise HTTPException(503,'Vector cleanup failed; document is unavailable for retrieval. Retry deletion when vector storage recovers.')
        for suffix in ['original','parsed.json','chunks.json','index.json','index-execution.json']:store.delete('documents/'+id+'/'+suffix)
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
class TemplateInput(BaseModel):name:str=Field(min_length=1,max_length=200);schema_:dict=Field(alias='schema')
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
@app.post('/api/templates')
def create_template(body:TemplateInput,owner=Depends(auth)):
    check_schema(body.schema_);r=new_record('template',owner,body.name,data={'name':body.name,'schema':body.schema_,'version':1});return representation(r)|store.json(r.ref)
@app.put('/api/templates/{id}')
def update_template(id:str,body:TemplateInput,owner=Depends(auth)):
    check_schema(body.schema_);r=get_record(id,owner,'template');version=r.version+1;ref=f'template/{id}/v{version}.json'
    store.put_json(ref,{'name':body.name,'schema':body.schema_,'version':version})
    with Session.begin() as s:r=s.get(Record,id);r.version=version;r.ref=ref;r.name=body.name;r.updated_at=time.time()
    return representation(r)|store.json(ref)
@app.get('/api/templates/{id}/versions')
def template_versions(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'template');return [store.json(f'template/{id}/v{n}.json') for n in range(1,r.version+1)]
class ExtractInput(BaseModel):document_ids:list[str]=Field(min_length=1,max_length=20);template_id:str;dataset_id:str|None=None;model_id:str|None=None;allow_external:bool=False
@app.get('/api/extractions')
def extractions(owner=Depends(auth)):return [representation(r) for r in records(owner,'extraction')]
@app.post('/api/extractions')
def create_extraction(body:ExtractInput,owner=Depends(auth)):
    t=get_record(body.template_id,owner,'template');dataset,docs=routing.documents_scope(owner,body.dataset_id,body.document_ids)
    snapshot=routing.execution_snapshot(dataset,'extraction',body.model_id);routing.require_indexes(docs,snapshot)
    external_check(body.allow_external,cfg=snapshot['settings'])
    if any(d.status!='ready' for d in docs):raise HTTPException(409,'Documents must be ready before extraction')
    data=body.model_dump()|{'dataset_id':dataset.id,'model_selection':routing.public_selection(snapshot),'schema':store.json(t.ref)['schema'],'template_version':t.version,'result':None,'sources':[]}
    r=new_record('extraction',owner,t.name,parent=dataset.id,data=data,status='queued');j=enqueue(owner,'extract',r.id,body.allow_external,snapshot)
    return representation(r)|data|{'job':job_repr(j)}
@app.get('/api/extractions/{id}')
def extraction(id:str,owner=Depends(auth)):
    r=get_record(id,owner,'extraction');return representation(r)|store.json(r.ref)
class ReviewInput(BaseModel):result:Any
@app.patch('/api/extractions/{id}')
def review_extraction(id:str,body:ReviewInput,owner=Depends(auth)):
    r=get_record(id,owner,'extraction');data=store.json(r.ref)
    if r.status!='ready':raise HTTPException(409,'Wait for extraction to complete')
    try:validate(body.result,data['schema'])
    except ValidationError:raise HTTPException(400,'Result does not match the template schema')
    store.put_json(f'extraction/{id}/review-{uid()}.json',data)
    data['result']=body.result;data['evidence']=[];data['evidence_notice']='Result manually edited. Original extraction sources are retained, but field evidence must be rechecked.';data['review_status']='reviewed';data['reviewed_at']=time.time();store.put_json(r.ref,data);return representation(r)|data
@app.get('/api/extractions/{id}/export')
def export_extraction(id:str,format:str='json',owner=Depends(auth)):
    r=get_record(id,owner,'extraction');data=store.json(r.ref)
    if r.status!='ready':raise HTTPException(409,'Extraction is not complete')
    if format=='json':payload=json.dumps(data['result'],indent=2);media='application/json'
    elif format=='csv':
        rows=data['result'] if isinstance(data['result'],list) else [data['result']];out=io.StringIO();keys=sorted({k for row in rows for k in row});writer=csv.DictWriter(out,fieldnames=keys);writer.writeheader()
        for row in rows:
            safe={k:json.dumps(v) if isinstance(v,(dict,list)) else str(v if v is not None else '') for k,v in row.items()}
            safe={k:"'"+v if v.startswith(('=','+','-','@','\t','\r')) else v for k,v in safe.items()};writer.writerow(safe)
        payload=out.getvalue();media='text/csv'
    else:raise HTTPException(400,'Export format must be json or csv')
    store.put(f'extraction/{id}/export.{format}',payload.encode());return Response(payload,media_type=media,headers={'Content-Disposition':f'attachment; filename="extraction.{format}"'})
@app.get('/api/jobs')
def jobs(owner=Depends(auth)):
    with Session() as s:return [job_repr(j) for j in s.scalars(select(Job).where(Job.owner==owner).order_by(Job.created_at.desc()))]
@app.post('/api/jobs/{id}/retry')
def retry_job(id:str,owner=Depends(auth)):
    with Session.begin() as s:
        j=s.get(Job,id)
        if not j or j.owner!=owner:raise HTTPException(404,'Not found')
        if j.status not in ('failed','cancelled'):raise HTTPException(409,'Only failed or cancelled jobs can be retried')
        target=s.get(Record,j.target_id)
        if not target or target.owner!=owner:raise HTTPException(404,'Target deleted')
        if target.parent_id:routing.require_active(routing.owned(target.parent_id,owner,'knowledge_base'))
        j.status='queued';j.progress=0;j.attempts=0;j.error='';j.lease_until=0;target.status='queued'
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
    return settings()|{'api_key_configured':has_key,'oci_api_key_configured':has_oci_key,'api_key':'********' if has_key else '', 'local_only':os.getenv('AEGIS_LOCAL_ONLY')=='true','ollama_endpoint':'http://127.0.0.1:11434','mock_allowed':os.getenv('AEGIS_ALLOW_MOCK')=='true','requires_reindex_on_embedding_change':True,'openai_endpoint':'https://api.openai.com/v1','external_data_notice':'Selected external providers receive data: OpenAI receives query/document text for its model or embeddings; OCI receives originals for Object Storage and query/document text for managed indexing or generation. Explicit consent is required per processing operation.'}
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
    return {'queue':get_transport(settings()['queue_provider']).status(),'local':{'storage':True,'qdrant':True,'postgresql':True,'openai_responses':True,'sentence_transformers':True,'ollama':True,'ocr':False,'streaming':True},'oci':capability_report(),'active':settings()}

@app.post('/api/conversations/{id}/messages/stream')
async def stream_message(id:str,body:MessageInput,request:Request,owner=Depends(auth)):
    import asyncio,re
    r=get_record(id,owner,'conversation');lock=_locks.setdefault(id,threading.Lock())
    if not lock.acquire(blocking=False):raise HTTPException(409,'A response is already in progress')
    try:
        data=store.json(r.ref);docs,snapshot=message_execution(body,owner,data);selection=routing.public_selection(snapshot)
        with execution_context(snapshot['embedding_execution']):sources=await asyncio.to_thread(providers.search,body.text,owner,docs,settings()['top_k'])
        request_id=uid();store.put_json('executions/'+request_id+'.json',snapshot)
        data['messages'].append({'id':request_id,'role':'user','text':body.text,'created_at':time.time(),'model_selection':selection});store.put_json(r.ref,data)
    except HTTPException:lock.release();raise
    except Exception:lock.release();raise HTTPException(502,'Retrieval failed; check provider connectivity and indexed documents')
    async def events():
        msg={'id':uid(),'role':'assistant','text':'','citations':[],'created_at':time.time(),'status':'streaming','mock':snapshot['settings']['model_provider']=='mock','model_selection':selection}
        iterator=None
        try:
            with execution_context(snapshot):
                iterator=providers.answer_stream_async(body.text,sources,data['messages'][:-1])
                async for piece in iterator:
                    if await request.is_disconnected():msg['status']='aborted';break
                    msg['text']+=piece
                    yield 'event: delta\ndata: '+json.dumps({'text':piece})+'\n\n'
            if msg['status']=='streaming':msg['status']='completed'
            used={int(x) for x in re.findall(r'\[(\d+)\]',msg['text'])}
            msg['citations']=[{'index':i+1,**source,'url':'/api/documents/'+source['document_id']+'/preview'} for i,source in enumerate(sources) if i+1 in used]
            yield 'event: done\ndata: '+json.dumps({'message':msg,'conversation_id':id})+'\n\n'
        except (GeneratorExit,asyncio.CancelledError):msg['status']='aborted';raise
        except Exception:
            msg['status']='failed';yield 'event: error\ndata: '+json.dumps({'detail':'Response interrupted or provider unavailable; partial text was saved'})+'\n\n'
        finally:
            try:
                if iterator is not None:
                    with execution_context(snapshot):await iterator.aclose()
                data['messages'].append(msg);store.put_json(r.ref,data)
            finally:lock.release()
    return StreamingResponse(events(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

@app.post('/api/index/search')
def diagnose_retrieval(body:MessageInput,owner=Depends(auth)):
    dataset,docs=routing.documents_scope(owner,body.dataset_id or body.kb_id,body.document_ids)
    snapshot=routing.execution_snapshot(dataset,'embedding');routing.require_indexes(docs,snapshot);external_check(body.allow_external,True,snapshot['settings'])
    ready=[d for d in docs if d.status=='ready'];started=time.monotonic()
    try:
        with execution_context(snapshot):hits=providers.search(body.text,owner,ready,settings()['top_k'])
    except Exception:raise HTTPException(502,'Retrieval failed; verify the selected provider and matching index configuration')
    return {'matches':hits,'count':len(hits),'duration_ms':round((time.monotonic()-started)*1000),'scoped_documents':len(docs),'ready_documents':len(ready),'embedding_fingerprint':providers.fingerprint(snapshot['settings']),'top_k':snapshot['settings']['top_k'],'provider':snapshot['settings']['search_provider'],'note':'Scores are provider-specific similarity values, not probabilities. Only permitted ready documents and canonical stored excerpts are returned.'}

class ProfileInput(BaseModel):
    name:str=Field(min_length=1,max_length=120)

def profile_public(record):
    data=local_store.json(record.ref)
    return representation(record)|{'api_key_configured':data.get('api_key_configured',False),'oci_api_key_configured':data.get('oci_api_key_configured',False)}

def write_profile(owner,name,id=None):
    with document_lock('settings-config'):
        with document_lock('profile-'+(id or 'new')):return _write_profile(owner,name,id)

def _write_profile(owner,name,id=None):
    existing=get_record(id,owner,'config_profile') if id else None
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

from .browser_recovery import router as browser_recovery_router
app.include_router(browser_recovery_router)
