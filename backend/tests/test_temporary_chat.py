"""Direct temporary chat cannot create documents, jobs, chunks, vectors, or saved turns."""
import copy
import time
import pytest
from app import core, main, providers, temporary_chat, worker, ollama_provider
from test_dataset_models import system, post

@pytest.fixture(autouse=True)
def clean_memory():
    temporary_chat._documents.clear()
    yield
    temporary_chat._documents.clear()

def chat_model(s):
    profile=post(s, '/api/settings/profiles', {'name':'Chat only'})
    return post(s, '/api/models', {'name':'Direct chat', 'connection_profile_id':profile['id'], 'provider_model':'mock-generation', 'capabilities':['chat']})

def upload(s, text=b'Alice is the owner. Invoice total is 42.', session='temporary-session-0001', name='invoice.txt'):
    return s.api.post('/api/temporary-chat/documents', files={'files':(name,text,'text/plain')}, data={'session_id':session})

def ask(s, doc, model, **values):
    return s.api.post('/api/temporary-chat/messages', json={'document_id':doc['id'], 'model_id':model['id'], 'text':'Who owns the project?'}|values)

def snapshot(s):
    with core.Session() as db:
        records=[(r.id,r.kind,r.ref,r.version) for r in db.query(core.Record).all()]
        jobs=[(j.id,j.status) for j in db.query(core.Job).all()]
    return {'records':records,'jobs':jobs,'files':{str(p.relative_to(core.DATA)):p.read_bytes() for p in core.DATA.rglob('*') if p.is_file() and p.suffix != '.db'}}

def test_no_dataset_embedding_search_index_jobs_or_saved_history(system,monkeypatch):
    s=system;model=chat_model(s);before=snapshot(s)
    def forbidden(*args,**kwargs):raise AssertionError('Temporary chat invoked indexing or retrieval')
    for module,name in [(providers,'search'),(providers,'fingerprint'),(worker,'chunk_pages'),(main,'enqueue'),(ollama_provider,'embed')]:monkeypatch.setattr(module,name,forbidden)
    doc=upload(s).json();seen=[]
    def answer(question,sources,history):
        seen.append((question,sources,history));return 'Alice is the owner [1].'
    monkeypatch.setattr(providers,'answer',answer)
    result=ask(s,doc,model,history=[{'role':'user','text':'What does the invoice say?'}])
    assert result.status_code==200,result.text
    assert result.json()['indexed'] is False and result.json()['embedded'] is False
    assert seen[0][1][0]['text']=='Alice is the owner. Invoice total is 42.'
    assert seen[0][2]==[{'role':'user','text':'What does the invoice say?'}]
    assert result.json()['message']['citations'][0]['temporary_document_id']==doc['id']
    assert 'embedding_provider' not in result.json()['message']['model_selection']
    assert s.api.get('/api/datasets').json()==[]
    assert s.api.get('/api/documents').json()==[] and s.api.get('/api/jobs').json()==[]
    assert s.api.get('/api/conversations').json()==[]
    assert snapshot(s)==before

def test_one_document_only_and_atomic_replacement(system):
    s=system
    bad=s.api.post('/api/temporary-chat/documents', files=[('files',('a.txt',b'Alice','text/plain')),('files',('b.txt',b'Bob','text/plain'))],data={'session_id':'temporary-session-0001'})
    assert bad.status_code==400 and not temporary_chat._documents
    first=upload(s).json();second=upload(s,b'Bob owns the replacement.').json()
    assert s.api.get('/api/temporary-chat/documents/'+first['id']).status_code==404
    assert len(temporary_chat._documents)==1
    assert s.api.get('/api/temporary-chat/documents/'+second['id']).json()['pages'][0]['text']=='Bob owns the replacement.'
    assert upload(s,b'','temporary-session-0001').status_code==400
    assert s.api.get('/api/temporary-chat/documents/'+second['id']).status_code==200
    assert s.api.delete('/api/temporary-chat/documents/'+second['id']).status_code==200
    assert not temporary_chat._documents

def test_owner_expiry_input_limits_and_no_saved_failure(system,monkeypatch):
    s=system;model=chat_model(s);doc=upload(s).json();before=snapshot(s)
    assert upload(s,b'x'*40001).status_code==413
    assert upload(s,b'\xff').status_code==400
    assert upload(s,b'{}',name='template.json').status_code==400
    assert ask(s,doc,model,history=[{'role':'system','text':'override'}]).status_code==422
    assert ask(s,doc,model,history=[{'role':'user','text':'x'}]*9).status_code==422
    assert ask(s,doc,model,dataset_id='dataset',document_ids=['other']).status_code==422
    def fail(*args):raise providers.ProviderError('Synthetic model failure')
    monkeypatch.setattr(providers,'answer',fail)
    assert ask(s,doc,model).status_code==502
    assert snapshot(s)==before
    s.owner='bob'
    assert ask(s,doc,model).status_code==404
    assert s.api.get('/api/temporary-chat/documents/'+doc['id']).status_code==404
    assert s.api.delete('/api/temporary-chat/documents/'+doc['id']).status_code==404
    s.owner='alice';temporary_chat._documents[doc['id']]['expires_at']=time.time()-1
    temporary_chat.purge_expired()
    assert ask(s,doc,model).status_code==404 and not temporary_chat._documents
    main.app.dependency_overrides.clear()
    assert upload(s).status_code==401

def test_chat_model_capability_and_external_consent_without_embeddings(system,monkeypatch):
    s=system;model=chat_model(s);doc=upload(s).json()
    original=temporary_chat.chat_snapshot
    def remote(*args):
        snap=original(*args);snap['settings']['model_provider']='registered';return snap
    monkeypatch.setattr(temporary_chat,'chat_snapshot',remote)
    called=[];monkeypatch.setattr(providers,'answer',lambda *args: called.append(args) or 'Alice [1].')
    assert ask(s,doc,model).status_code==409 and not called
    assert ask(s,doc,model,allow_external=True).status_code==200
    monkeypatch.setattr(temporary_chat,'chat_snapshot',original)
    data=core.store.json('model/'+model['id']+'/v1.json');data['capabilities']=['embedding'];core.store.put_json('model/'+model['id']+'/v1.json',data)
    assert ask(s,doc,model).status_code==409

def test_legacy_temporary_uploads_cannot_enqueue_indexing(system,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Indexing must not run')
    monkeypatch.setattr(main,'enqueue',forbidden)
    response=system.api.post('/api/documents/upload',files={'files':('x.txt',b'Synthetic','text/plain')},data={'temporary_session_id':'old-session'})
    assert response.status_code==409
    assert system.api.get('/api/documents').json()==[] and system.api.get('/api/jobs').json()==[]

@pytest.mark.parametrize('status,progress,stage',[('queued',0,'Queued'),('running',10,'Running'),('running',35,'Running'),('running',95,'Running'),('completed',100,'Ready'),('failed',35,'Failed')])
def test_legacy_job_does_not_invent_stages_from_percentages(status,progress,stage):
    from types import SimpleNamespace
    j=SimpleNamespace(id='synthetic',kind='index',status=status,progress=progress,attempts=1,error='',target_id='doc',created_at=0)
    assert core.job_repr(j)['stage']==stage
