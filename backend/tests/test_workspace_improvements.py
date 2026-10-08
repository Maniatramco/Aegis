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


def test_template_json_download_versions_and_owner_scope(system):
    schema={'type':'object','properties':{'total':{'type':['number','null'],'description':'Amount','minimum':0}},'required':['total'],'additionalProperties':False}
    d=dataset(system)
    t=post(system,'/api/templates',{'name':'Invoice / totals','schema':schema,'dataset_id':d['id']})
    updated=schema|{'description':'New instructions'}
    response=system.api.put('/api/templates/'+t['id'],json={'name':'Invoice totals','schema':updated,'dataset_id':d['id']})
    assert response.status_code==200
    current=system.api.get('/api/templates/'+t['id']+'/export')
    assert current.status_code==200 and current.json()=={'name':'Invoice totals','schema':updated}
    assert current.headers['content-type'].startswith('application/json')
    assert 'attachment;' in current.headers['content-disposition'] and 'Invoice%20totals-v2.json' in current.headers['content-disposition']
    old=system.api.get('/api/templates/'+t['id']+'/export?version=1')
    assert old.json()=={'name':'Invoice / totals','schema':schema}
    assert 'Invoice%20-%20totals-v1.json' in old.headers['content-disposition']
    assert system.api.get('/api/templates/'+t['id']+'/export?version=0').status_code==404
    assert system.api.get('/api/templates/'+t['id']+'/export?version=3').status_code==404
    system.owner='bob'
    assert system.api.get('/api/templates/'+t['id']+'/export').status_code==404
