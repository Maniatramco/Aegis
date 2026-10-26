"""Administrators can rename and describe an onboarded dataset without touching its models or access."""
from types import SimpleNamespace
from test_user_management import accounts, login
from test_dataset_models import system, dataset
from test_dataset_access import assign


def test_admin_edits_dataset_details_and_others_cannot(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client),name='Contracts')
    before=client.get('/api/datasets/'+d['id']+'/models').json()
    edited=client.patch('/api/datasets/'+d['id'],json={'name':'  Supplier contracts ','description':'Signed agreements'})
    assert edited.status_code==200,edited.text
    assert edited.json()['name']=='Supplier contracts' and edited.json()['description']=='Signed agreements'
    assert next(row for row in client.get('/api/datasets').json() if row['id']==d['id'])['name']=='Supplier contracts'
    after=client.get('/api/datasets/'+d['id']+'/models').json()
    assert {k:v for k,v in after.items() if k!='version'}=={k:v for k,v in before.items() if k!='version'} and after['version']==before['version']+1
    assert client.patch('/api/datasets/'+d['id'],json={'name':'   '}).status_code==422
    assert client.patch('/api/datasets/'+d['id'],json={'name':'x'*201}).status_code==422

    assign(client,[d]);login(client,'Colleague')
    assert client.patch('/api/datasets/'+d['id'],json={'name':'Mine now'}).status_code==403
    assert client.get('/api/datasets/'+d['id']).json()['name']=='Supplier contracts'
