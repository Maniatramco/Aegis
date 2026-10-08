"""API-to-worker routing, authorization, pinned runs and explicit migration contracts."""
import json
from types import SimpleNamespace
import pytest
import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import core, main, worker, providers, dataset_models as routing

@pytest.fixture
def system(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'control.db'),connect_args={'check_same_thread':False});session=sessionmaker(engine,expire_on_commit=False)
    for module in (core,main,worker):monkeypatch.setattr(module,'Session',session)
    for module in (core,main):monkeypatch.setattr(module,'engine',engine)
    monkeypatch.setattr(core,'DATA',tmp_path);monkeypatch.setenv('AEGIS_MASTER_KEY',Fernet.generate_key().decode());monkeypatch.setenv('AEGIS_ALLOW_MOCK','true')
    monkeypatch.setattr(core,'DEFAULTS',core.DEFAULTS|{'model_provider':'mock','embedding_provider':'mock','search_provider':'local','storage_provider':'local'})
    monkeypatch.setattr(main,'DEFAULTS',core.DEFAULTS);state=SimpleNamespace(owner='alice',session=session)
    main.app.dependency_overrides[main.auth]=lambda:state.owner
    with TestClient(main.app) as client:state.api=client;yield state
    main.app.dependency_overrides.clear();engine.dispose()

def post(s,path,body=None,**kwargs):
    r=s.api.post(path,json=body,**kwargs);assert r.status_code==200,r.text;return r.json()
def dataset(s,name='Dataset',mapped=True):
    d=post(s,'/api/datasets',{'name':name})
    return post(s,'/api/datasets/'+d['id']+'/migrate-settings') if mapped else d

def model(s,profile,name='Alternative',caps=None,**values):
    return post(s,'/api/models',{'name':name,'connection_profile_id':profile,'provider_model':name,'capabilities':caps or ['chat','extraction'],'enabled':True}|values)
def mapping(s,d,**values):
    config=s.api.get('/api/datasets/'+d['id']+'/models').json();body={k:config[k] for k in ('mappings','default_chat_model_id','default_extraction_model_id','embedding_model_id')}|values
    r=s.api.put('/api/datasets/'+d['id']+'/models',json=body|{'acknowledge_reindex':True});assert r.status_code==200,r.text;return r.json()
def upload(s,d,run=True):
    r=s.api.post('/api/documents/upload',files={'files':('invoice.txt',b'Invoice total 42. Alice is the owner.','text/plain')},data={'dataset_id':d['id'],'allow_external':'true'})
    assert r.status_code==200,r.text
    if run:
        assert worker.run_once();assert s.api.get('/api/documents/'+r.json()['documents'][0]['id']).json()['status']=='ready'
    return r.json()
def conversation(s,d,docs=None):return post(s,'/api/conversations',{'dataset_id':d['id'],'document_ids':docs or []})
def message(s,c,**values):return s.api.post('/api/conversations/'+c['id']+'/messages',json={'text':'Who is the owner?','allow_external':True}|values)
def template(s):return post(s,'/api/templates',{'name':'Owner','schema':{'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}})

def test_new_dataset_never_uses_global_defaults(system):
    s=system;d=dataset(s,mapped=False);assert not d['migration_required'];assert d['mappings']==[]
    r=s.api.post('/api/documents/upload',files={'files':('x.txt',b'Example text','text/plain')},data={'dataset_id':d['id']});assert r.status_code==409
    c=conversation(s,d);assert message(s,c).status_code==409
    assert s.api.get('/api/jobs').json()==[]
    assert s.api.get('/api/models').json()==[]

def test_defaults_explicit_selection_capability_and_dataset_scope(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']]);generation=next(m for m in d['models'] if 'chat' in m['capabilities'])
    extra=model(s,generation['connection_profile_id'],'Careful model');unmapped=model(s,generation['connection_profile_id'],'Unmapped')
    mapping(s,d,mappings=d['mappings']+[{'model_id':extra['id'],'enabled':True}])
    default=message(s,c);assert default.status_code==200;assert default.json()['message']['model_selection']['model_id']==generation['id']
    explicit=message(s,c,model_id=extra['id']);assert explicit.status_code==200;assert explicit.json()['message']['model_selection']['model_id']==extra['id']
    assert message(s,c,model_id=unmapped['id']).status_code==409
    assert message(s,c,model_id=d['embedding_model_id']).status_code==409
    config=s.api.get('/api/datasets/'+d['id']+'/models').json()
    body={k:config[k] for k in ('mappings','default_chat_model_id','default_extraction_model_id','embedding_model_id')}
    assert s.api.put('/api/datasets/'+d['id']+'/models',json=body|{'default_chat_model_id':None}).status_code==400
    assert message(s,c).status_code==200
    mapping(s,d,mappings=[m|{'enabled':False} if m['model_id']==extra['id'] else m for m in config['mappings']])
    assert message(s,c).json()['message']['model_selection']['model_id']==generation['id']
    other=dataset(s,'Other');other_doc=upload(s,other)['documents'][0]
    assert message(s,c,document_ids=[other_doc['id']]).status_code==400
    assert s.api.post('/api/extractions',json={'dataset_id':d['id'],'document_ids':[doc['id'],other_doc['id']],'template_id':template(s)['id']}).status_code==400
    s.owner='bob'
    assert s.api.get('/api/datasets/'+d['id']).status_code==404
    assert s.api.put('/api/datasets/'+d['id']+'/models',json={'mappings':[]}).status_code==404
    assert s.api.post('/api/models',json={'name':'Stolen profile','connection_profile_id':generation['connection_profile_id'],'provider_model':'x','capabilities':['chat']}).status_code==404
    assert message(s,c).status_code==404

def test_disabled_catalog_models_and_invalid_defaults_rejected(system):
    s=system;d=dataset(s);g=next(m for m in d['models'] if 'chat' in m['capabilities']);c=conversation(s,d)
    wrong={'mappings':d['mappings'],'default_chat_model_id':d['embedding_model_id'],'embedding_model_id':d['embedding_model_id']}
    assert s.api.put('/api/datasets/'+d['id']+'/models',json=wrong).status_code==400
    body={k:g[k] for k in ('name','connection_profile_id','provider_model','capabilities')}|{'enabled':False}
    assert s.api.put('/api/models/'+g['id'],json=body).status_code==200
    assert message(s,c,model_id=g['id']).status_code==409
    assert s.api.post('/api/models',json=body|{'capabilities':['embedding','chat']}).status_code==400

def test_embedding_generation_changes_fail_closed_and_reindex(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']]);emb=next(m for m in d['models'] if m['id']==d['embedding_model_id'])
    replacement=model(s,emb['connection_profile_id'],'Embedding two',['embedding'])
    updated=mapping(s,d,mappings=d['mappings']+[{'model_id':replacement['id'],'enabled':True}],embedding_model_id=replacement['id'])
    assert updated['index_generation']==2
    assert s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    assert message(s,c).status_code==409
    post(s,'/api/documents/'+doc['id']+'/reindex',{'allow_external':True});assert worker.run_once()
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    assert message(s,c).status_code==200
    assert core.store.json('documents/'+doc['id']+'/index.json')['index_generation']==2

def test_stale_queued_index_cannot_publish(system):
    s=system;d=dataset(s);uploaded=upload(s,d,run=False);emb=next(m for m in d['models'] if m['id']==d['embedding_model_id'])
    replacement=model(s,emb['connection_profile_id'],'New embedding',['embedding'])
    mapping(s,d,mappings=d['mappings']+[{'model_id':replacement['id'],'enabled':True}],embedding_model_id=replacement['id'])
    assert worker.run_once()
    job=next(j for j in s.api.get('/api/jobs').json() if j['id']==uploaded['jobs'][0]['id']);assert job['status']=='failed';assert 'changed' in job['error']
    with pytest.raises(FileNotFoundError):core.store.get('documents/'+uploaded['documents'][0]['id']+'/index.json')

def test_profile_revision_and_globals_cannot_change_queued_extraction(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    assert s.api.patch('/api/settings',json={'model_provider':'openai','model':'first-model','api_key':'first-secret'}).status_code==200
    profile=post(s,'/api/settings/profiles',{'name':'Shared API connection'});first=model(s,profile['id'],'first-model')
    mapping(s,d,mappings=d['mappings']+[{'model_id':first['id'],'enabled':True}],default_extraction_model_id=first['id'])
    # Change global settings before submitting: mapped profile must still win.
    assert s.api.patch('/api/settings',json={'model':'global-other','api_key':'second-secret'}).status_code==200
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':template(s)['id'],'allow_external':True})
    revised=s.api.put('/api/settings/profiles/'+profile['id'],json={'name':'Revised profile'});assert revised.status_code==200
    payloads=[]
    def fake(path,payload):
        payloads.append((payload['model'],core.api_key()));return {'output':[{'content':[{'type':'output_text','text':json.dumps({'data':{'owner':'Alice'},'evidence':[]})}]}]}
    monkeypatch.setattr(providers,'openai_request',fake)
    assert worker.run_once();result=s.api.get('/api/extractions/'+ex['id']);assert result.json()['status']=='ready',result.text
    assert payloads==[('first-model','first-secret')]
    assert result.json()['model_selection']['connection_profile_version']==1
    assert result.json()['model_selection']['model_id']==first['id']
    for text in (result.text,s.api.get('/api/models').text,s.api.get('/api/datasets').text,s.api.get('/api/index').text,s.api.get('/api/extractions/'+ex['id']+'/export').text):
        assert 'first-secret' not in text and 'second-secret' not in text and 'secret_refs' not in text and 'secrets/profiles/' not in text
    # New requests resolve the revised profile, preserving old-run reproducibility.
    ex2=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':template(s)['id'],'model_id':first['id'],'allow_external':True})
    assert worker.run_once();assert payloads[-1]==('first-model','second-secret');assert ex2['model_selection']['connection_profile_version']==2


def test_legacy_metadata_is_explicit_and_unassigned_documents_can_recover(system):
    s=system;legacy=main.new_record('knowledge_base','alice','Legacy dataset',data={'description':'Before mappings'})
    assert s.api.get('/api/datasets/'+legacy.id).json()['migration_required']
    original='documents/old/original';core.store.put(original,b'Legacy original retained.')
    with core.Session.begin() as db:db.add(core.Record(id='old',kind='document',owner='alice',name='old.txt',ref=original,status='ready'))
    assert s.api.get('/api/documents/old').json()['requires_reindex']
    post(s,'/api/datasets/'+legacy.id+'/assign-documents',{'document_ids':['old']})
    migrated=post(s,'/api/datasets/'+legacy.id+'/migrate-settings');assert not migrated['migration_required'];assert migrated['index_generation']==1
    assert core.store.get(original)==b'Legacy original retained.'
    post(s,'/api/documents/old/reindex',{'allow_external':True});assert worker.run_once()
    assert s.api.get('/api/documents/old').json()['status']=='ready'
    assert not s.api.get('/api/documents/old').json()['requires_reindex']
    assert s.api.post('/api/datasets/'+legacy.id+'/migrate-settings').status_code==409


def test_model_selection_controls_actual_openai_request(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']])
    assert s.api.patch('/api/settings',json={'model_provider':'openai','api_key':'mapped-key'}).status_code==200
    p=post(s,'/api/settings/profiles',{'name':'OpenAI connection'});a=model(s,p['id'],'fast-model');b=model(s,p['id'],'careful-model')
    mapping(s,d,mappings=d['mappings']+[{'model_id':a['id'],'enabled':True},{'model_id':b['id'],'enabled':True}],default_chat_model_id=a['id'])
    sent=[];real=httpx.Client
    def handle(req):
        sent.append((json.loads(req.content)['model'],req.headers['authorization']))
        return httpx.Response(200,json={'status':'completed','output':[{'content':[{'type':'output_text','text':'Alice [1].'}]}]})
    monkeypatch.setattr(providers.httpx,'Client',lambda **kw:real(**kw,transport=httpx.MockTransport(handle)))
    assert message(s,c,model_id=b['id']).status_code==200
    assert message(s,c).status_code==200
    assert sent==[('careful-model','Bearer mapped-key'),('fast-model','Bearer mapped-key')]
    assert core.settings()['model']!='careful-model'


def test_consent_uses_selected_profile_not_active_global(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']])
    assert s.api.patch('/api/settings',json={'model_provider':'openai','api_key':'configured'}).status_code==200
    profile=post(s,'/api/settings/profiles',{'name':'External'});m=model(s,profile['id'],'external')
    mapping(s,d,mappings=d['mappings']+[{'model_id':m['id'],'enabled':True}],default_chat_model_id=m['id'])
    assert s.api.patch('/api/settings',json={'model_provider':'mock'}).status_code==200
    assert message(s,c,allow_external=False).status_code==409
    assert len(s.api.get('/api/conversations/'+c['id']).json()['messages'])==0


def test_conversation_history_never_crosses_dataset_boundaries(system):
    s=system;first=dataset(s,'Private accounts');second=dataset(s,'Public manuals');doc=upload(s,first)['documents'][0];other=upload(s,second)['documents'][0]
    c=conversation(s,first,[doc['id']]);assert message(s,c).status_code==200
    r=message(s,c,dataset_id=second['id'],document_ids=[other['id']]);assert r.status_code==409
    stream=s.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Continue','dataset_id':second['id'],'document_ids':[other['id']],'allow_external':True});assert stream.status_code==409
    assert len(s.api.get('/api/conversations/'+c['id']).json()['messages'])==2
    # Empty conversations become pinned at their first submitted message.
    blank=post(s,'/api/conversations',{'title':'Fresh'})
    assert message(s,blank,dataset_id=first['id'],document_ids=[doc['id']]).status_code==200
    assert message(s,blank,dataset_id=second['id'],document_ids=[other['id']]).status_code==409


def set_active(s,d,active):
    response=s.api.patch('/api/datasets/'+d['id']+'/status',json={'active':active})
    assert response.status_code==200,response.text
    assert response.json()['active'] is active
    return response.json()


@pytest.mark.parametrize('path',['/api/datasets','/api/knowledge-bases'])
def test_dataset_activity_defaults_and_create_persistence(system,path):
    s=system
    default=post(s,path,{'name':'Default active'})
    inactive=post(s,path,{'name':'Created inactive','active':False})
    assert default['active'] is True
    assert inactive['active'] is False
    for d in (default,inactive):
        stored=routing.dataset_config(routing.owned(d['id'],s.owner,'knowledge_base'))
        assert stored['active'] is d['active']
        assert s.api.get('/api/datasets/'+d['id']).json()['active'] is d['active']
    listed={d['id']:d['active'] for d in s.api.get(path).json()}
    assert listed=={default['id']:True,inactive['id']:False}
    assert s.api.post(path,json={'name':'Invalid','active':'false'}).status_code==422


def test_legacy_dataset_defaults_active_without_rewriting_config(system):
    s=system;original={'description':'Legacy dataset','future_metadata':{'retain':True}}
    legacy=main.new_record('knowledge_base',s.owner,'Legacy',data=original)
    response=s.api.get('/api/datasets/'+legacy.id)
    assert response.status_code==200
    assert response.json()['active'] is True
    assert response.json()['migration_required'] is True
    assert s.api.get('/api/datasets').json()[0]['active'] is True
    assert s.api.get('/api/knowledge-bases').json()[0]['active'] is True
    assert core.store.json(legacy.ref)==original
    inactive=set_active(s,response.json(),False)
    assert inactive['migration_required'] is True
    record=routing.owned(legacy.id,s.owner,'knowledge_base')
    assert routing.dataset_config(record)==original|{'active':False}
    migrated=post(s,'/api/datasets/'+legacy.id+'/migrate-settings')
    assert migrated['active'] is False
    assert migrated['migration_required'] is False


def test_dataset_status_preserves_configuration_and_index_validity(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    record=routing.owned(d['id'],s.owner,'knowledge_base')
    original=routing.dataset_config(record)|{'future_metadata':{'retain':['custom-value']}}
    record=routing.write_version(record,original)
    index=core.store.get('documents/'+doc['id']+'/index.json')
    response=s.api.patch('/api/datasets/'+d['id']+'/status',json={'active':False,'name':'Must not rename','mappings':[],'index_generation':999})
    assert response.status_code==200,response.text
    inactive=response.json()
    assert inactive['active'] is False
    assert inactive['name']==d['name']
    assert inactive['status']=='ready'
    assert inactive['version']==record.version+1
    # Fresh database reads resolve a new persisted config reference, not cached state.
    persisted=routing.owned(d['id'],s.owner,'knowledge_base')
    assert persisted.ref!=record.ref
    assert core.store.json(persisted.ref)==original|{'active':False}
    assert core.store.json(record.ref)==original
    assert inactive['index_generation']==d['index_generation']
    assert inactive['mappings']==d['mappings']
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    assert not s.api.get('/api/index',params={'dataset_id':d['id']}).json()['documents'][0]['requires_reindex']
    # Mapping saves on an inactive dataset preserve its status and pinned index space.
    updated=mapping(s,d)
    assert updated['index_generation']==d['index_generation']
    assert s.api.get('/api/datasets/'+d['id']).json()['active'] is False
    restored=set_active(s,d,True)
    assert restored['index_generation']==d['index_generation']
    assert core.store.get('documents/'+doc['id']+'/index.json')==index
    assert routing.dataset_config(routing.owned(d['id'],s.owner,'knowledge_base'))['future_metadata']==original['future_metadata']
    assert message(s,conversation(s,d,[doc['id']])).status_code==200


@pytest.mark.parametrize('body',[{}, {'active':None}, {'active':0}, {'active':1}, {'active':'true'}, {'active':'false'}, {'active':[]}, {'active':{}}])
def test_dataset_status_requires_an_explicit_boolean(system,body):
    s=system;d=dataset(s,mapped=False)
    assert s.api.patch('/api/datasets/'+d['id']+'/status',json=body).status_code==422
    unchanged=s.api.get('/api/datasets/'+d['id']).json()
    assert unchanged['active'] is True
    assert unchanged['version']==d['version']


def test_dataset_status_respects_owner_isolation_and_record_kind(system):
    s=system;d=dataset(s,mapped=False);c=conversation(s,d)
    for owner in ('bob','administrator'):
        s.owner=owner
        assert s.api.get('/api/datasets').json()==[]
        assert s.api.patch('/api/datasets/'+d['id']+'/status',json={'active':False}).status_code==404
    s.owner='alice'
    assert s.api.patch('/api/datasets/'+c['id']+'/status',json={'active':False}).status_code==404
    assert s.api.patch('/api/datasets/missing/status',json={'active':False}).status_code==404
    assert s.api.get('/api/datasets/'+d['id']).json()['active'] is True


def test_dataset_status_requires_session_and_csrf(system):
    s=system;s.owner='administrator';d=dataset(s,mapped=False)
    with core.Session.begin() as db:
        db.add(core.User(id='administrator',username='admin',password_hash=core.password_hash('secure-test-pass')))
    main.app.dependency_overrides.clear()
    path='/api/datasets/'+d['id']+'/status'
    assert s.api.patch(path,json={'active':False}).status_code==401
    signed_in=post(s,'/api/auth/login',{'username':'admin','password':'secure-test-pass'})
    assert s.api.patch(path,json={'active':False}).status_code==403
    assert s.api.patch(path,json={'active':False},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert s.api.get('/api/datasets/'+d['id']).json()['active'] is True
    response=s.api.patch(path,json={'active':False},headers={'X-CSRF-Token':signed_in['csrf_token']})
    assert response.status_code==200,response.text
    assert response.json()['active'] is False


def test_inactive_dataset_blocks_new_execution_but_keeps_history_readable(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];c=conversation(s,d,[doc['id']]);t=template(s)
    assert message(s,c).status_code==200
    extracted=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id'],'allow_external':True})
    assert worker.run_once()
    set_active(s,d,False)
    previous_jobs=s.api.get('/api/jobs').json()
    previous_documents=s.api.get('/api/documents').json()
    previous_history=s.api.get('/api/conversations/'+c['id']).json()
    def unexpected_provider(*args,**kwargs):pytest.fail('Inactive dataset reached a provider')
    monkeypatch.setattr(providers,'search',unexpected_provider)
    monkeypatch.setattr(providers,'answer',unexpected_provider)
    for field in ('dataset_id','kb_id'):
        response=s.api.post('/api/documents/upload',files={'files':('blocked.txt',b'New content','text/plain')},data={field:d['id'],'allow_external':'true'})
        assert response.status_code==409,response.text
        assert 'inactive' in response.json()['detail']
    for path,body in [
        ('/api/documents/'+doc['id']+'/reindex',{'allow_external':True}),
        ('/api/conversations/'+c['id']+'/messages',{'text':'New question','allow_external':True}),
        ('/api/conversations/'+c['id']+'/messages/stream',{'text':'Stream question','allow_external':True}),
        ('/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id'],'allow_external':True}),
        ('/api/index/search',{'dataset_id':d['id'],'text':'New query','allow_external':True}),
    ]:
        response=s.api.post(path,json=body)
        assert response.status_code==409,response.text
        assert 'inactive' in response.json()['detail']
    assert s.api.get('/api/jobs').json()==previous_jobs
    assert s.api.get('/api/documents').json()==previous_documents
    assert s.api.get('/api/conversations/'+c['id']).json()==previous_history
    assert s.api.get('/api/documents/'+doc['id']+'/download').content==b'Invoice total 42. Alice is the owner.'
    assert s.api.get('/api/documents/'+doc['id']+'/preview').json()['chunks']
    assert s.api.get('/api/datasets/'+d['id']+'/models').json()['mappings']==d['mappings']
    assert s.api.get('/api/extractions/'+extracted['id']).json()['status']=='ready'
    assert s.api.get('/api/extractions/'+extracted['id']+'/export').status_code==200
    assert s.api.get('/api/conversations/'+c['id']+'/export').status_code==200


def test_inactive_unmapped_dataset_reports_status_before_model_configuration(system):
    s=system;d=post(s,'/api/datasets',{'name':'Inactive with no mappings','active':False})
    response=message(s,conversation(s,d))
    assert response.status_code==409
    assert 'inactive' in response.json()['detail']


def test_deactivation_preserves_already_accepted_jobs(system):
    s=system;d=dataset(s);ready=upload(s,d)['documents'][0]
    pending=upload(s,d,run=False)
    extracted=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[ready['id']],'template_id':template(s)['id'],'allow_external':True})
    set_active(s,d,False)
    assert worker.run_once()
    assert worker.run_once()
    assert s.api.get('/api/documents/'+pending['documents'][0]['id']).json()['status']=='ready'
    assert not s.api.get('/api/documents/'+pending['documents'][0]['id']).json()['requires_reindex']
    assert s.api.get('/api/extractions/'+extracted['id']).json()['status']=='ready'


def test_inactive_dataset_job_retries_are_rejected_until_reactivation(system):
    s=system;d=dataset(s);ready=upload(s,d)['documents'][0]
    pending=upload(s,d,run=False)
    extracted=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[ready['id']],'template_id':template(s)['id'],'allow_external':True})
    jobs=[pending['jobs'][0],extracted['job']]
    for job in jobs:post(s,'/api/jobs/'+job['id']+'/cancel')
    set_active(s,d,False)
    before=s.api.get('/api/jobs').json()
    for job in jobs:
        response=s.api.post('/api/jobs/'+job['id']+'/retry')
        assert response.status_code==409,response.text
        assert 'inactive' in response.json()['detail']
    assert s.api.get('/api/jobs').json()==before
    set_active(s,d,True)
    for job in jobs:assert post(s,'/api/jobs/'+job['id']+'/retry')['status']=='queued'
    assert worker.run_once()
    assert worker.run_once()
    assert s.api.get('/api/documents/'+pending['documents'][0]['id']).json()['status']=='ready'
    assert s.api.get('/api/extractions/'+extracted['id']).json()['status']=='ready'
