"""Jobs monitoring shows who started each job without revealing other users' names to non-administrators."""
from types import SimpleNamespace
from test_user_management import accounts, login
from test_dataset_models import system, dataset, upload
from test_dataset_access import assign


def test_jobs_report_starter_dataset_and_timing_with_names_only_for_administrators(accounts):
    client=accounts;login(client);d=dataset(SimpleNamespace(api=client))
    upload(SimpleNamespace(api=client),d)
    assign(client,[d]);login(client,'Colleague')
    upload(SimpleNamespace(api=client),d)

    mine,theirs=sorted(client.get('/api/jobs').json(),key=lambda job:not job['started_by']['self'])
    assert mine['started_by']=={'id':'colleague','label':'You','self':True}
    assert theirs['started_by']=={'id':None,'label':'Another user','self':False}
    assert {mine['dataset_id'],theirs['dataset_id']}=={d['id']}
    assert all(job['updated_at']>=job['created_at'] and job['started_via'] for job in (mine,theirs))

    login(client)
    labels={job['started_by']['label'] for job in client.get('/api/jobs').json()}
    assert labels=={'You','Colleague'}
    assert client.get('/api/jobs?ids=unknown').json()==[]
