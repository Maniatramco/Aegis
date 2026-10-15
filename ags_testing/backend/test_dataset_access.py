"""Real authentication and grants across the shared dataset workflow."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from ags_app import core, main, worker, relational, providers
from test_user_management import accounts, login, body, OLD
from test_dataset_models import system, dataset
from test_agent_workspace import plan, proposal, planner
from test_agent_graph import sequence, tool


def assign(client,datasets,user='colleague'):
    login(client)
    result=client.put('/api/users/'+user+'/datasets',json={'dataset_ids':[d['id'] for d in datasets]})
    assert result.status_code==200,result.text
    return result.json()


def scoped_prompt(client,d):
    response=client.post('/api/templates',json={'name':'invoice.json','source_filename':'invoice.json','dataset_id':d['id'],
        'schema':{'type':'object','properties':{'total':{'type':'number'}},'required':['total'],'additionalProperties':False}})
    assert response.status_code==200,response.text
    return response.json()


def test_user_only_sees_assignments_and_cannot_configure_or_self_assign(accounts):
    client=accounts;login(client);a=dataset(SimpleNamespace(api=client));b=dataset(SimpleNamespace(api=client),name='Private')
    assign(client,[a]);login(client,'Colleague')
    assert [row['id'] for row in client.get('/api/datasets').json()]==[a['id']]
    assert [row['id'] for row in client.get('/api/knowledge-bases').json()]==[a['id']]
    catalog=client.get('/api/agent-v2/catalog').json();assert [row['id'] for row in catalog['datasets']]==[a['id']]
    assert set(row['id'] for row in catalog['models'])==set(row['id'] for row in a['models'])
    selectors=client.get('/api/agent-v2/catalog?selectors_only=true').json()
    assert [row['id'] for row in selectors['datasets']]==[a['id']]
    assert set(row['id'] for row in selectors['models'])==set(row['id'] for row in a['models'])
    assert client.get('/api/datasets/'+b['id']).status_code==404
    for path,method,values in [('/api/datasets','post',{'name':'Unauthorized'}),('/api/datasets/'+a['id']+'/status','patch',{'active':False}),('/api/datasets/'+a['id']+'/models','put',{'mappings':[]}),('/api/users/colleague/datasets','put',{'dataset_ids':[b['id']]}),('/api/settings','patch',{'model_provider':'mock'})]:
        assert getattr(client,method)(path,json=values).status_code==403

def test_agent_selectors_do_not_wait_for_index_checks_or_retired_profiles(accounts,monkeypatch):
    from ags_app import dataset_models as routing
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client),name='Resume Extraction')
    with core.Session() as session:owner=session.get(core.Record,d['id']).owner
    ref='model/retired-selector-fixture/v1.json'
    core.store.put_json(ref,{'enabled':False,'capabilities':['chat'],'connection_profile_id':'missing-retired-profile'})
    with core.Session.begin() as session:session.add(core.Record(id='retired-selector-fixture',kind='model',owner=owner,name='Retired QA',ref=ref))
    monkeypatch.setattr(routing,'document_public',lambda *args,**kwargs:pytest.fail('Selectors must not probe document/index readiness'))
    monkeypatch.setattr(routing,'mapped_model',lambda *args,**kwargs:pytest.fail('Selectors must reuse already-authorized models'))
    response=client.get('/api/agent-v2/catalog?selectors_only=true')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['can_onboard_datasets']
    assert [row['id'] for row in data['datasets']]==[d['id']]
    assert data['datasets'][0]['models_complete']
    assert len(data['datasets'][0]['models'])==len(d['models'])
    assert 'Retired QA' not in response.text


def test_mapped_upload_chat_extract_review_and_reextract_are_shared_and_audited(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client));assign(client,[d]);login(client,'Colleague')
    uploaded=client.post('/api/documents/upload',files={'files':('invoice.txt',b'Invoice total 42','text/plain')},data={'dataset_id':d['id'],'allow_external':'true'})
    assert uploaded.status_code==200,uploaded.text
    doc=uploaded.json()['documents'][0];assert worker.run_once()
    prompt=scoped_prompt(client,d)
    conversation=client.post('/api/conversations',json={'dataset_id':d['id']}).json()
    answer=client.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'What is the invoice total?','allow_external':True})
    assert answer.status_code==200,answer.text
    assert answer.json()['message']['citations']
    result=client.post('/api/extractions',json={'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id'],'allow_external':True})
    assert result.status_code==200,result.text
    extraction=result.json();assert worker.run_once()
    saved=client.patch('/api/extractions/'+extraction['id'],json={'version':1,'result':{'total':42}})
    assert saved.status_code==200,saved.text
    assert client.post('/api/extractions/'+extraction['id']+'/reextract',json={'version':2,'confirm_reviewed':True,'allow_external':True}).status_code==409
    assert client.post('/api/extractions',json={'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id'],'allow_external':True}).status_code==200
    assert worker.run_once()
    assert client.get('/api/extractions/'+extraction['id']).json()['status']=='ready'
    with core.Session() as session:
        assert session.get(core.Record,doc['id']).owner=='administrator'
        assert session.get(core.Record,doc['id']).created_by=='colleague'
        assert session.get(core.Record,prompt['id']).created_by=='colleague'
        assert session.get(core.Record,extraction['id']).created_by=='colleague'
        job=session.scalar(select(core.Job).where(core.Job.target_id==extraction['id']))
        assert job.created_by=='colleague'
    login(client)
    assert client.get('/api/documents/'+doc['id']).status_code==200
    assert client.get('/api/extractions/'+extraction['id']).status_code==200
    # Conversations stay personal even though dataset results are shared.
    assert client.get('/api/conversations/'+conversation['id']).status_code==404
    client.post('/api/users',json=body(username='User2'))
    with core.Session() as session:user2=session.scalar(select(core.User).where(core.User.username=='User2')).id
    assign(client,[d],user2);login(client,'User2',body()['password'])
    assert client.get('/api/documents/'+doc['id']).status_code==200
    assert client.get('/api/templates').json()[0]['id']==prompt['id']
    assert client.get('/api/extractions/'+extraction['id']).status_code==200


def test_revocation_blocks_old_ids_history_exports_jobs_and_new_work_without_deleting_content(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client));assign(client,[d]);login(client,'Colleague')
    uploaded=client.post('/api/documents/upload',files={'files':('invoice.txt',b'Invoice total 42','text/plain')},data={'dataset_id':d['id'],'allow_external':'true'}).json()
    doc=uploaded['documents'][0];assert worker.run_once();prompt=scoped_prompt(client,d)
    conversation=client.post('/api/conversations',json={'dataset_id':d['id']}).json()
    result=client.post('/api/extractions',json={'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id'],'allow_external':True}).json();assert worker.run_once()
    with TestClient(main.app) as admin:
        assign(admin,[])
    assert client.get('/api/datasets').json()==[]
    assert client.get('/api/documents').json()==[] and client.get('/api/extractions').json()==[]
    assert client.get('/api/templates').json()==[] and client.get('/api/jobs').json()==[]
    for path in ['/api/datasets/'+d['id'],'/api/documents/'+doc['id'],'/api/documents/'+doc['id']+'/download','/api/documents/'+doc['id']+'/preview','/api/templates/'+prompt['id']+'/export','/api/extractions/'+result['id'],'/api/extractions/'+result['id']+'/export','/api/conversations/'+conversation['id']]:
        assert client.get(path).status_code==404,path
    assert client.post('/api/jobs/'+uploaded['jobs'][0]['id']+'/retry').status_code==404
    assert client.post('/api/jobs/'+uploaded['jobs'][0]['id']+'/cancel').status_code==404
    assert client.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'Show old evidence','allow_external':True}).status_code==404
    assert client.post('/api/documents/upload',files={'files':('blocked.txt',b'Blocked','text/plain')},data={'dataset_id':d['id']}).status_code==404
    login(client);assert client.get('/api/extractions/'+result['id']).status_code==200
    assign(client,[d]);login(client,'Colleague');assert client.get('/api/extractions/'+result['id']).status_code==200


def test_mapping_validation_csrf_and_audit(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client));assign(client,[d])
    for ids,status in [([d['id'],d['id']],400),([d['id'],'missing'],404)]:
        assert client.put('/api/users/colleague/datasets',json={'dataset_ids':ids}).status_code==status
        assert client.get('/api/users/colleague/datasets').json()['dataset_ids']==[d['id']]
    with core.Session() as session:
        row=session.get(relational.UserDataset,('colleague',d['id']))
        assert row.created_by==row.updated_by=='administrator' and row.updated_at>=row.created_at
        created=row.created_at
    assign(client,[])
    with core.Session() as session:
        row=session.get(relational.UserDataset,('colleague',d['id']))
        assert not row.enabled and row.created_at==created and row.updated_by=='administrator'
    # Database startup must never reinstate a revoked legacy-owner assignment.
    core.init()
    with core.Session() as session:
        assert not session.get(relational.UserDataset,('colleague',d['id'])).enabled
    assign(client,[d])
    with core.Session() as session:
        row=session.get(relational.UserDataset,('colleague',d['id']))
        assert row.enabled and row.created_at==created
    assert client.put('/api/users/administrator/datasets',json={'dataset_ids':[]}).status_code==400
    assert client.get('/api/users/administrator/datasets').json()['all_datasets']
    client.headers.pop('X-CSRF-Token')
    assert client.put('/api/users/colleague/datasets',json={'dataset_ids':[]}).status_code==403


def test_assistant_upload_extract_autocontinuation_uses_mapping(accounts,monkeypatch):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client));prompt=scoped_prompt(client,d);assign(client,[d]);login(client,'Colleague')
    planner(monkeypatch,proposal())
    request=plan(SimpleNamespace(api=client),d,text='Upload and extract invoice',template_id=prompt['id'])
    upload=client.post('/api/agent-v2/plans/'+request['id']+'/calls/0/upload',files={'files':('agent-invoice.txt',b'Invoice total 42','text/plain')},data={'dataset_id':d['id'],'template_id':prompt['id'],'confirmed':'true','allow_external':'true','continue_extraction':'true'})
    assert upload.status_code==200,upload.text
    assert worker.run_once();assert worker.run_once()
    status=client.get('/api/agent-v2/plans/'+request['id']);assert status.status_code==200,status.text
    assert all(call['status']=='completed' for call in status.json()['calls'])
    extracted=client.get('/api/extractions').json();assert len(extracted)==1
    assert client.get('/api/extractions/'+extracted[0]['id']).json()['result'] is not None


def test_existing_owner_backfill_once_and_admin_models_on_legacy_user_dataset(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client))
    # Simulate an existing colleague-owned dataset with centrally managed models.
    with core.Session.begin() as session:
        session.get(core.Record,d['id']).owner='colleague'
    with core.engine.begin() as connection:
        relational.UserDataset.__table__.drop(connection)
    core.init()
    with core.Session() as session:
        grant=session.get(relational.UserDataset,('colleague',d['id']))
        assert grant.enabled and grant.created_via=='migration' and grant.created_by is None
    login(client,'Colleague')
    assert client.get('/api/datasets').json()[0]['id']==d['id']
    upload=client.post('/api/documents/upload',files={'files':('legacy.txt',b'Invoice total 42','text/plain')},data={'dataset_id':d['id'],'allow_external':'true'})
    assert upload.status_code==200,upload.text
    assert worker.run_once()
    conversation=client.post('/api/conversations',json={'dataset_id':d['id']}).json()
    reply=client.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'What is the invoice total?','allow_external':True})
    assert reply.status_code==200,reply.text
    assert reply.json()['message']['citations']
    assign(client,[]);core.init();login(client,'Colleague')
    assert client.get('/api/datasets').json()==[]


def test_langgraph_member_reads_shared_results_and_rejects_other_dataset(accounts,monkeypatch):
    import json
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client));private=dataset(SimpleNamespace(api=client),name='Unassigned')
    prompt=scoped_prompt(client,d)
    uploaded=client.post('/api/documents/upload',files={'files':('invoice.txt',b'Invoice total 42','text/plain')},data={'dataset_id':d['id'],'allow_external':'true'}).json()
    assert worker.run_once()
    ex=client.post('/api/extractions',json={'dataset_id':d['id'],'document_ids':[uploaded['documents'][0]['id']],'template_id':prompt['id'],'allow_external':True}).json();assert worker.run_once()
    assign(client,[d]);login(client,'Colleague')
    seen=sequence(monkeypatch,tool('find_extractions'),tool('read_extraction_results',extraction_id=ex['id']),{'text':'Saved extraction is available.','calls':[]})
    response=plan(SimpleNamespace(api=client),d,text='Summarize the saved extracted fields.')
    assert response['runtime']=='langgraph' and not response['calls']
    observation=json.loads(next(m['content'] for m in seen[-1] if m.get('tool_name')=='read_extraction_results'))
    assert observation['records'][0]['fields']==client.get('/api/extractions/'+ex['id']).json()['result']
    assert client.post('/api/agent-v2/plans',json={'text':'Read this dataset','dataset_id':private['id'],'planner_model_id':d['default_chat_model_id']}).status_code==404


def test_retrieval_uses_index_storage_owners_not_signed_in_user(monkeypatch):
    from ags_app import reranker
    monkeypatch.setattr(reranker,'enabled',lambda:False)
    calls=[]
    def retrieve(query,owner,documents,limit):
        calls.append((owner,{d.id for d in documents}))
        return [{'score':1,'document_id':d.id} for d in documents]
    monkeypatch.setattr(providers,'_retrieve',retrieve)
    documents=[SimpleNamespace(id='a',owner='administrator'),SimpleNamespace(id='b',owner='legacy-owner')]
    found=providers.search('Invoice total','colleague',documents,5)
    assert set((owner,tuple(sorted(ids))) for owner,ids in calls)=={('administrator',('a',)),('legacy-owner',('b',))}
    assert {m['document_id'] for m in found}=={'a','b'}
