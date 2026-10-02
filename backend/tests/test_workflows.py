import os,tempfile
os.environ['DATA_DIR']=tempfile.mkdtemp()
os.environ['DATABASE_URL']='sqlite:///'+os.environ['DATA_DIR']+'/test.db'
os.environ['AEGIS_BOOTSTRAP_TOKEN']='test-bootstrap'
os.environ['MODEL_PROVIDER']='mock'
os.environ['EMBEDDING_PROVIDER']='mock'
os.environ['SEARCH_PROVIDER']='local'
os.environ['AEGIS_ALLOW_MOCK']='true'
from fastapi.testclient import TestClient
from app.main import app
from app.core import store,Session,Record,Job,User,password_hash
from app.worker import run_once

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import core,main,worker
@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    global Session
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    session=sessionmaker(engine,expire_on_commit=False)
    for module in (core,main,worker):monkeypatch.setattr(module,'Session',session)
    for module in (core,main):monkeypatch.setattr(module,'engine',engine)
    monkeypatch.setattr(core,'DATA',tmp_path)
    monkeypatch.setattr(core,'DEFAULTS',core.DEFAULTS|{'model_provider':'mock','embedding_provider':'mock','search_provider':'local','storage_provider':'local'})
    monkeypatch.setattr(main,'DEFAULTS',core.DEFAULTS)
    Session=session;core.init()
    yield
    engine.dispose()

def test_complete_storage_first_workflow():
    with TestClient(app) as c:
        assert c.get('/api/documents').status_code==401
        assert c.post('/api/auth/setup',json={'username':'admin','password':'secure-test-pass','bootstrap_token':'bad'}).status_code==403
        assert c.post('/api/auth/setup',json={'username':'admin','password':'secure-test-pass','bootstrap_token':'test-bootstrap'}).status_code==200
        res=c.post('/api/auth/login',json={'username':'admin','password':'secure-test-pass'});assert res.status_code==200,res.text
        csrf=res.json()['csrf_token'];c.headers['X-CSRF-Token']=csrf
        kb=c.post('/api/knowledge-bases',json={'name':'Test corpus'}).json()
        migrated=c.post('/api/datasets/'+kb['id']+'/migrate-settings');assert migrated.status_code==200,migrated.text
        res=c.post('/api/documents/upload',files=[('files',('manual.txt',b'Aegis stores original files privately. The project owner is Alice.','text/plain'))],data={'kb_id':kb['id']});assert res.status_code==200,res.text
        doc=res.json()['documents'][0];assert run_once()
        assert c.get('/api/documents/'+doc['id']).json()['status']=='ready'
        assert c.get('/api/documents/'+doc['id']+'/download').content.startswith(b'Aegis')
        conversation=c.post('/api/conversations',json={'title':'Question','document_ids':[doc['id']]}).json()
        reply=c.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'Who owns the project?'});assert reply.status_code==200,reply.text
        assert reply.json()['message']['citations'][0]['document_id']==doc['id']
        template=c.post('/api/templates',json={'name':'Owner','schema':{'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}}).json()
        ext=c.post('/api/extractions',json={'document_ids':[doc['id']],'template_id':template['id']});assert ext.status_code==200,ext.text
        assert run_once()
        extracted=c.get('/api/extractions/'+ext.json()['id']).json();assert extracted['result']=={'owner':'MOCK TEST VALUE'}
        assert c.patch('/api/extractions/'+ext.json()['id'],json={'result':{'owner':'Alice'}}).status_code==200
        assert b'Alice' in c.get('/api/extractions/'+ext.json()['id']+'/export?format=csv').content
        assert c.get('/api/index').json()['documents'][0]['chunk_count']>0
        assert c.delete('/api/documents/'+doc['id']).status_code==200
        assert c.get('/api/documents/'+doc['id']).status_code==404
        reply=c.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'Who owns the project?','document_ids':[]});assert reply.status_code==200
        assert not reply.json()['message']['citations']
        c.headers.pop('X-CSRF-Token');c.headers['Authorization']='garbage'
        assert c.post('/api/knowledge-bases',json={'name':'CSRF attack'}).status_code==403

def test_storage_traversal():
    import pytest
    with pytest.raises(ValueError):store.put('../../escape',b'no')

def test_chunk_determinism():
    from app.worker import chunk_pages
    p=[{'page':1,'text':'A sufficiently lengthy example '*20}]
    a=chunk_pages('doc',p,200,30);b=chunk_pages('doc',p,200,30)
    assert a==b and len(a)>1 and a[1]['offset']==170

def test_stale_exhausted_job_recovery():
    from app.worker import claim
    with Session.begin() as s:s.add(Job(id='exhausted',owner='administrator',kind='index',target_id='missing',status='running',attempts=3,lease_until=1))
    assert claim() is None
    with Session() as s:assert s.get(Job,'exhausted').status=='failed'

def test_schema_rejects_external_refs_and_requires_strict_objects():
    from app.main import check_schema
    from fastapi import HTTPException
    with pytest.raises(HTTPException):check_schema({'type':'object','properties':{'x':{'$ref':'http://127.0.0.1/private'}},'required':['x'],'additionalProperties':False})
    with pytest.raises(HTTPException):check_schema({'type':'object','properties':{}})

def test_docx_archive_expansion_guard():
    import zipfile,io
    from app.worker import parse_document
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('../escape.xml','bad')
    with pytest.raises(ValueError,match='Unsafe DOCX'):parse_document('bad.docx',out.getvalue())

def test_encrypted_credentials_never_exported(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('AEGIS_MASTER_KEY',Fernet.generate_key().decode())
    main.app.dependency_overrides[main.auth]=lambda:'test-owner'
    try:
        with TestClient(app) as c:
            r=c.patch('/api/settings',json={'api_key':'sk-secret-test'});assert r.status_code==200,r.text
            assert 'sk-secret-test' not in r.text
            assert 'sk-secret-test' not in c.get('/api/settings/export').text
            assert b'sk-secret-test' not in store.get('secrets/provider.enc')
    finally:main.app.dependency_overrides.clear()

def test_worker_cancelled_index_cannot_publish(monkeypatch):
    import time
    from app import providers
    from app.worker import process
    did='cancel-safety';jid='cancel-safety-job'
    store.put('documents/'+did+'/original',b'Cancellation must never publish searchable vectors.')
    dataset=main.new_record('knowledge_base','alice','Cancellation test',data={'index_generation':1})
    snapshot={'settings':core.settings()|{'_index_namespace':dataset.id+':1'},'secret_refs':{},'dataset_id':dataset.id,'index_generation':1}
    store.put_json('jobs/'+jid+'.json',{'allow_external':False,'execution':snapshot})
    with Session.begin() as s:
        s.add(Record(parent_id=dataset.id,id=did,kind='document',owner='alice',name='safe.txt',ref='documents/'+did+'/original',status='queued'))
        s.add(Job(id=jid,owner='alice',kind='index',target_id=did,status='running',lease_token='lease',lease_until=time.time()+900))
    def interrupted(*args):
        with Session.begin() as s:s.get(Job,jid).status='cancelled'
    monkeypatch.setattr(providers,'put_vectors',interrupted)
    with pytest.raises(InterruptedError):process(jid,'lease')
    with Session() as s:assert s.get(Record,did).status!='ready'

def test_named_profiles_mask_keys_and_restore_versions(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('AEGIS_MASTER_KEY',Fernet.generate_key().decode())
    main.app.dependency_overrides[main.auth]=lambda:'profile-owner'
    try:
        with TestClient(app) as c:
            assert c.patch('/api/settings',json={'api_key':'sk-profile-test','top_k':3}).status_code==200
            saved=c.post('/api/settings/profiles',json={'name':'Local saved'});assert saved.status_code==200,saved.text
            profile=saved.json();assert profile['api_key_configured'] is True
            assert 'sk-profile-test' not in c.get('/api/settings/profiles').text
            assert 'sk-profile-test' not in c.get('/api/settings/profiles/'+profile['id']+'/export').text
            c.patch('/api/settings',json={'api_key':'','top_k':7})
            restored=c.post('/api/settings/profiles/'+profile['id']+'/activate');assert restored.status_code==200,restored.text
            assert restored.json()['top_k']==3 and restored.json()['api_key_configured']
            changed=c.put('/api/settings/profiles/'+profile['id'],json={'name':'Updated saved'});assert changed.json()['version']==2
    finally:main.app.dependency_overrides.clear()

def test_openai_stream_requires_completed_event(monkeypatch):
    import asyncio,httpx
    from app import providers
    core.store.put_json('configuration/settings.json',core.settings()|{'model_provider':'openai'})
    monkeypatch.setattr(providers,'api_key',lambda:'test-key')
    original=httpx.AsyncClient
    def client(**kw):return original(**kw,transport=httpx.MockTransport(lambda req:httpx.Response(200,text='data: {"type":"response.output_text.delta","delta":"Partial"}\n\n')))
    monkeypatch.setattr(providers.httpx,'AsyncClient',client)
    async def consume():return [piece async for piece in providers.answer_stream_async('question',[{'document_name':'test','text':'evidence'}])]
    with pytest.raises(providers.ProviderError,match='before completion'):asyncio.run(consume())

def test_openai_stream_forwards_real_delta(monkeypatch):
    import asyncio,httpx
    from app import providers
    core.store.put_json('configuration/settings.json',core.settings()|{'model_provider':'openai'})
    monkeypatch.setattr(providers,'api_key',lambda:'test-key')
    original=httpx.AsyncClient
    def handler(req):
        assert req.url.host=='api.openai.com'
        assert req.headers['authorization']=='Bearer test-key'
        return httpx.Response(200,text='data: {"type":"response.output_text.delta","delta":"Evidence [1]."}\n\ndata: {"type":"response.completed"}\n\n')
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(handler)))
    async def consume():return [piece async for piece in providers.answer_stream_async('question',[{'document_name':'test','text':'evidence'}])]
    assert asyncio.run(consume())==['Evidence [1].']

def test_profile_records_do_not_block_empty_storage_switch(monkeypatch):
    main.app.dependency_overrides[main.auth]=lambda:'profile-owner'
    class ReadyStorage:
        def test_connection(self):return {'ok':True}
    monkeypatch.setattr(main,'oci_storage',lambda cfg=None:ReadyStorage())
    try:
        with TestClient(app) as c:
            assert c.post('/api/settings/profiles',json={'name':'Empty local workspace'}).status_code==200
            result=c.patch('/api/settings',json={'storage_provider':'oci','oci_storage_namespace':'test','oci_storage_bucket':'test'})
            assert result.status_code==200,result.text
            assert result.json()['storage_provider']=='oci'
    finally:main.app.dependency_overrides.clear()

def test_profile_without_keys_does_not_inherit_environment(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('AEGIS_MASTER_KEY',Fernet.generate_key().decode())
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('OCI_GENAI_API_KEY',raising=False)
    main.app.dependency_overrides[main.auth]=lambda:'profile-owner'
    try:
        with TestClient(app) as c:
            saved=c.post('/api/settings/profiles',json={'name':'No credentials'}).json()
            monkeypatch.setenv('OPENAI_API_KEY','env-openai-must-not-forward')
            monkeypatch.setenv('OCI_GENAI_API_KEY','env-oci-must-not-forward')
            result=c.post('/api/settings/profiles/'+saved['id']+'/activate')
            assert result.status_code==200,result.text
            assert core.api_key()=='' and core.oci_api_key()==''
            assert not result.json()['api_key_configured'] and not result.json()['oci_api_key_configured']
            assert c.patch('/api/settings',json={'api_key':'new-explicit-key','oci_api_key':'new-explicit-oci'}).status_code==200
            assert core.api_key()=='new-explicit-key' and core.oci_api_key()=='new-explicit-oci'
            assert c.patch('/api/settings',json={'api_key':'','oci_api_key':''}).status_code==200
            assert core.api_key()=='' and core.oci_api_key()==''
    finally:main.app.dependency_overrides.clear()

def test_openai_unicode_chunks_respect_byte_limit_and_offsets():
    from app.worker import chunk_pages
    from app import providers
    cfg=core.settings()|{'embedding_provider':'openai','search_provider':'local'}
    store.put_json('configuration/settings.json',cfg)
    text='😀漢é'*2500
    chunks=chunk_pages('unicode-document',[{'page':1,'text':text}],6000,0)
    assert len(chunks)>2
    assert ''.join(chunk['text'] for chunk in chunks)==text
    assert all(len(chunk['text'].encode('utf-8'))<=8000 for chunk in chunks)
    assert all(text[chunk['offset']:chunk['offset']+len(chunk['text'])]==chunk['text'] for chunk in chunks)
    assert chunks==chunk_pages('unicode-document',[{'page':1,'text':text}],6000,0)
    assert len({chunk['id'] for chunk in chunks})==len(chunks)

def test_openai_rejects_overlong_unicode_query_before_external_request(monkeypatch):
    from app import providers
    store.put_json('configuration/settings.json',core.settings()|{'embedding_provider':'openai'})
    calls=[]
    monkeypatch.setattr(providers,'openai_request',lambda *args:calls.append(args))
    with pytest.raises(providers.ProviderError,match='8000 UTF-8 byte'):providers.embed(['😀'*2001])
    assert calls==[]
