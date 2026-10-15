"""Dataset trash removes access, preserves originals/results and supports real recovery."""
from types import SimpleNamespace
import time
import pytest
from fastapi import HTTPException
from ags_app import core, worker, dataset_models as routing, dataset_lifecycle, dataset_access as access
from test_dataset_models import system, dataset, upload, conversation, post
from test_user_management import accounts, login


def remove(client, row, **changes):
    return client.request('DELETE', '/api/datasets/' + row['id'], json={
        'confirmation': row['name'], 'expected_version': row['version'], **changes})


def test_delete_hides_related_content_and_restore_preserves_originals_and_review(accounts):
    client=accounts;login(client);s=SimpleNamespace(api=client)
    d=dataset(s);keep=dataset(s,'Keep',mapped=False)
    doc=upload(s,d)['documents'][0]
    prompt=post(s,'/api/templates',{'name':'Scoped','dataset_id':d['id'],
        'schema':{'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}})
    extraction=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']], 'template_id':prompt['id'],'allow_external':True})
    assert worker.run_once()
    result=client.patch('/api/extractions/'+extraction['id'],json={'version':1,'result':{'owner':'Alice'}})
    assert result.status_code==200,result.text
    reviewed=result
    c=conversation(s,d,[doc['id']])
    before=client.get('/api/datasets/'+d['id']).json()
    original=core.store.get('documents/'+doc['id']+'/original')
    models=client.get('/api/models').json()
    assert remove(client,d).json()['recoverable']
    assert [r['id'] for r in client.get('/api/datasets').json()]==[keep['id']]
    assert [r['id'] for r in client.get('/api/agent-v2/catalog').json()['datasets']]==[keep['id']]
    for path in ['/api/datasets/'+d['id'],'/api/documents/'+doc['id']+'/download',
                 '/api/templates/'+prompt['id']+'/export','/api/extractions/'+extraction['id'],'/api/conversations/'+c['id']]:
        assert client.get(path).status_code==404,path
    assert client.get('/api/documents').json()==[]
    assert client.get('/api/extractions').json()==[]
    assert client.get('/api/overview').json()['documents']==0
    assert client.get('/api/models').json()==models
    assert [r['id'] for r in client.get('/api/dataset-trash').json()]==[d['id']]
    assert core.store.get('documents/'+doc['id']+'/original')==original
    assert client.post('/api/dataset-trash/'+d['id']+'/restore').status_code==200
    after=client.get('/api/datasets/'+d['id']).json()
    for key in ['mappings','default_chat_model_id','default_extraction_model_id','embedding_model_id','index_generation']:
        assert after[key]==before[key]
    assert client.get('/api/documents/'+doc['id']+'/download').content==original
    saved=client.get('/api/extractions/'+extraction['id']).json()
    assert saved['version']==reviewed.json()['version'] and saved['review_status']=='reviewed'
    assert client.get('/api/conversations/'+c['id']).status_code==200
    assert client.get('/api/dataset-trash').json()==[]


def test_only_admin_can_delete_list_trash_or_restore_and_assignments_survive(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client))
    assert client.put('/api/users/colleague/datasets',json={'dataset_ids':[d['id']]}).status_code==200
    login(client,'Colleague')
    assert remove(client,d).status_code==403
    assert client.get('/api/dataset-trash').status_code==403
    assert client.post('/api/dataset-trash/'+d['id']+'/restore').status_code==403
    login(client);assert remove(client,d).status_code==200
    login(client,'Colleague')
    assert client.get('/api/datasets').json()==[]
    assert client.get('/api/datasets/'+d['id']).status_code==404
    assert client.get('/api/models').json()==[]
    login(client);assert client.post('/api/dataset-trash/'+d['id']+'/restore').status_code==200
    login(client,'Colleague')
    assert client.get('/api/datasets/'+d['id']).status_code==200


def test_wrong_name_stale_version_and_invalid_restore_do_not_change_dataset(system):
    d=dataset(system)
    assert remove(system.api,d,confirmation='wrong name').status_code==400
    assert remove(system.api,d,expected_version=d['version']+1).status_code==409
    assert system.api.post('/api/dataset-trash/'+d['id']+'/restore').status_code==404
    assert system.api.get('/api/dataset-trash').json()==[]
    assert system.api.get('/api/datasets/'+d['id']).status_code==200


def test_queued_jobs_block_deletion_and_completed_jobs_allow_it(system):
    d=dataset(system);item=upload(system,d,run=False)
    assert remove(system.api,d).status_code==409
    assert worker.run_once()
    assert remove(system.api,d).status_code==200
    assert remove(system.api,d).status_code==404


@pytest.mark.parametrize('kind',['index','extract'])
def test_late_worker_job_cannot_process_deleted_dataset(system,monkeypatch,kind):
    d=dataset(system);item=upload(system,d);doc=item['documents'][0]
    target=doc['id']
    if kind=='extract':
        prompt=post(system,'/api/templates',{'name':'Late job','schema':{'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}})
        target=post(system,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id'],'allow_external':True})['id']
        assert worker.run_once()
    snapshot=routing.execution_snapshot(routing.owned(d['id'],system.owner,'knowledge_base'),'embedding' if kind=='index' else 'extraction')
    assert remove(system.api,d).status_code==200
    from ags_app import main,providers
    monkeypatch.setattr(providers,'embed',lambda *a,**k:pytest.fail('Deleted dataset must never invoke embeddings'))
    monkeypatch.setattr(providers,'extract_with_evidence',lambda *a,**k:pytest.fail('Deleted dataset must never invoke generation'))
    job=main.enqueue(system.owner,kind,target,True,snapshot)
    assert worker.run_once()
    with core.Session() as session:assert session.get(core.Job,job.id).status=='failed'


def test_active_agent_blocks_delete_but_pending_proposal_becomes_inaccessible(system):
    d=dataset(system)
    plan=routing.create('agent_plan',system.owner,'Pending',{'dataset_id':d['id'],'calls':[], 'goal':{'status':'running'}},parent=d['id'],status='workflow')
    assert remove(system.api,d).status_code==409
    core.store.put_json(plan.ref,{'dataset_id':d['id'],'calls':[{'status':'proposed'}]})
    assert remove(system.api,d).status_code==200
    with pytest.raises(HTTPException) as error:access.get_record(plan.id,system.owner,'agent_plan')
    assert error.value.status_code==404


def test_failed_recovery_receipt_write_keeps_dataset_active(system,monkeypatch):
    d=dataset(system);write=core.store.put_json
    def fail(ref,value):
        if ref==dataset_lifecycle.receipt_ref(d['id']):raise OSError('synthetic storage failure')
        return write(ref,value)
    monkeypatch.setattr(core.store,'put_json',fail)
    with pytest.raises(OSError):remove(system.api,d)
    assert system.api.get('/api/datasets/'+d['id']).status_code==200
    assert system.api.get('/api/dataset-trash').json()==[]


def test_unscoped_legacy_onboarding_is_hidden_with_its_deleted_dataset(system):
    d=dataset(system)
    onboarding=routing.create('agent_onboarding',system.owner,'Earlier workflow',{'dataset_id':d['id'],'status':'completed'})
    assert remove(system.api,d).status_code==200
    with pytest.raises(HTTPException) as error:access.get_record(onboarding.id,system.owner,'agent_onboarding')
    assert error.value.status_code==404
    assert system.api.post('/api/dataset-trash/'+d['id']+'/restore').status_code==200
    assert access.get_record(onboarding.id,system.owner,'agent_onboarding').id==onboarding.id


@pytest.mark.parametrize('tool,age,job_ids,allowed',[
    ('upload',172800,[],True),('upload',10,[],False),
    ('extract',172800,[],False),('upload',172800,['uncertain-job'],False)])
def test_only_expired_uploads_without_jobs_stop_blocking_delete(system,tool,age,job_ids,allowed):
    d=dataset(system)
    routing.create('agent_plan',system.owner,'Interrupted upload',{'dataset_id':d['id'],
        'goal':{'status':'waiting_jobs'},'calls':[{'tool':tool,'status':'running','started_at':time.time()-age,'job_ids':job_ids}]},parent=d['id'],status='workflow')
    assert remove(system.api,d).status_code==(200 if allowed else 409)
