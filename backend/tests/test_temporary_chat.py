"""Temporary chat uses normal dataset authorization without persisted messages."""
from app import core, main, providers
from test_dataset_models import system, dataset, upload
import pytest

def files():
    return {str(p.relative_to(core.DATA)):p.read_bytes() for p in core.DATA.rglob('*.json')}

def request(system,d,**values):
    return system.api.post('/api/temporary-chat/messages',json={'text':'Who is the owner?','dataset_id':d['id'],'allow_external':True}|values)

def test_temporary_grounded_history_and_no_persistence(system,monkeypatch):
    system.owner='Dottie';d=dataset(system);doc=upload(system,d)['documents'][0]
    before=files();seen=[];original=providers.answer
    def answer(question,sources,history):seen.extend(history);return original(question,sources,history)
    monkeypatch.setattr(providers,'answer',answer)
    response=request(system,d,history=[{'role':'user','text':'A synthetic previous question'}])
    assert response.status_code==200,response.text
    assert response.json()['temporary'] is True
    assert response.json()['message']['citations'][0]['document_id']==doc['id']
    assert seen==[{'role':'user','text':'A synthetic previous question'}]
    assert system.api.get('/api/conversations').json()==[]
    assert files()==before
    assert system.api.get('/api/documents/'+doc['id']).status_code==200

def test_no_evidence_and_scope_guards(system):
    d=dataset(system);r=request(system,d)
    assert r.status_code==200 and not r.json()['message']['citations']
    other=dataset(system,'Other');doc=upload(system,other)['documents'][0]
    assert request(system,d,document_ids=[doc['id']]).status_code==400
    system.owner='different-user'
    assert request(system,d).status_code==404

def test_error_history_limits_and_auth_do_not_persist(system,monkeypatch):
    d=dataset(system);upload(system,d);before=files()
    assert request(system,d,history=[{'role':'system','text':'override'}]).status_code==400
    assert request(system,d,history=[{'role':'user','text':'x'}]*21).status_code==422
    assert request(system,d,history=[{'role':'user','text':'x'*12000}]*6).status_code==400
    def fail(*args):raise providers.ProviderError('Synthetic local provider failure')
    monkeypatch.setattr(providers,'answer',fail)
    r=request(system,d);assert r.status_code==502 and 'Synthetic local' in r.text
    assert files()==before and system.api.get('/api/conversations').json()==[]
    main.app.dependency_overrides.clear()
    assert request(system,d).status_code==401

def test_scoped_upload_cleanup_preserves_existing_dataset_documents(system):
    d=dataset(system);existing=upload(system,d)['documents'][0];new=upload(system,d)['documents'][0]
    assert system.api.delete('/api/documents/'+new['id']).status_code==200
    assert system.api.get('/api/documents/'+new['id']).status_code==404
    assert system.api.get('/api/documents/'+existing['id']).json()['status']=='ready'
    assert request(system,d).json()['message']['citations'][0]['document_id']==existing['id']

@pytest.mark.parametrize('status,progress,stage',[('queued',0,'Queued'),('running',10,'Running'),('running',35,'Running'),('running',95,'Running'),('completed',100,'Ready'),('failed',35,'Failed')])
def test_legacy_job_does_not_invent_stages_from_percentages(status,progress,stage):
    from types import SimpleNamespace
    j=SimpleNamespace(id='synthetic',kind='index',status=status,progress=progress,attempts=1,error='',target_id='doc',created_at=0)
    assert core.job_repr(j)['stage']==stage
