from fastapi.testclient import TestClient
from app import main, worker, dataset_models as routing
from test_dataset_models import system, dataset, upload, post


def test_document_listing_resolves_each_dataset_once(system,monkeypatch):
    d=dataset(system)
    upload(system,d)
    upload(system,d)
    original=routing.embedding_snapshot
    calls=[]
    def counted(record):
        calls.append(record.id)
        return original(record)
    monkeypatch.setattr(routing,'embedding_snapshot',counted)
    result=system.api.get('/api/documents')
    assert result.status_code==200
    assert len(result.json())==2
    assert calls==[d['id']]
    system.api.get('/api/documents')
    assert calls==[d['id'],d['id']]


def test_dataset_template_import_scope_validation_and_extraction_stages(system):
    d=dataset(system)
    other=dataset(system,'Other dataset')
    document=upload(system,d)['documents'][0]
    schema={'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}
    template=post(system,'/api/templates',{'name':'Imported JSON','schema':schema,'dataset_id':d['id']})
    assert template['dataset_id']==d['id']
    assert system.api.get('/api/templates').json()[0]['dataset_id']==d['id']
    assert system.api.post('/api/templates',json={'name':'Bad','schema':{'type':'string'},'dataset_id':d['id']}).status_code==400
    assert system.api.post('/api/templates',json={'name':'Unauthorized','schema':schema,'dataset_id':'missing'}).status_code==404
    other_doc=upload(system,other)['documents'][0]
    assert system.api.post('/api/extractions',json={'dataset_id':other['id'],'document_ids':[other_doc['id']],'template_id':template['id']}).status_code==400
    run=post(system,'/api/extractions',{'dataset_id':d['id'],'document_ids':[document['id']],'template_id':template['id']})
    assert list(run['job']['workflow']['stages'])==['prepare','generate','validate','ready']
    assert worker.run_once()
    result=system.api.get('/api/extractions/'+run['id']).json()
    assert result['status']=='ready' and result['template_id']==template['id']
    job=next(j for j in system.api.get('/api/jobs').json() if j['id']==run['job']['id'])
    assert all(stage['status']=='completed' for stage in job['workflow']['stages'].values())
