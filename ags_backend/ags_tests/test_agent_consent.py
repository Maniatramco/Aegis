"""Approval preflight must be read-only and must not weaken execution guards."""
from ags_app import main, dataset_models as routing
from test_dataset_models import system, dataset
from test_agent_workspace import plan, send_files


def test_local_preflight_needs_no_approval_or_side_effects(system):
    d=dataset(system)
    response=system.api.post('/api/agent-v2/consent',json={'dataset_id':d['id'],'planner_model_id':d['default_chat_model_id'],'roles':['chat','embedding','extraction']})
    assert response.status_code==200,response.text
    assert response.json()=={'dataset_id':d['id'],'required':False,'destinations':[]}
    assert system.api.get('/api/documents').json()==[]
    assert system.api.get('/api/jobs').json()==[]


def test_cloud_upload_popup_scope_and_execution_still_require_consent(system,monkeypatch):
    s=system;d=dataset(s);p=plan(s,d,text='@Upload',attached_filenames=['general.txt'])
    original=routing.execution_snapshot
    def snapshot(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[1]=='embedding':result['settings']={**result['settings'],'storage_provider':'oci','api_key':'do-not-leak'}
        return result
    monkeypatch.setattr(routing,'execution_snapshot',snapshot)
    response=s.api.post('/api/agent-v2/consent',json={'dataset_id':d['id'],'roles':['embedding']})
    assert response.status_code==200,response.text
    notice=response.json();assert notice['required']
    assert [item['title'] for item in notice['destinations']]==['OCI Object Storage']
    assert 'do-not-leak' not in response.text
    assert s.api.get('/api/jobs').json()==[]
    assert send_files(s,p).status_code==409
    assert s.api.get('/api/documents').json()==[]
    assert s.api.get('/api/jobs').json()==[]
    accepted=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload',data={'dataset_id':d['id'],'confirmed':'true','allow_external':'true'},files={'files':('general.txt',b'Fictional consent QA invoice 42','text/plain')})
    assert accepted.status_code==200,accepted.text
    assert len(s.api.get('/api/documents').json())==1
    assert len(s.api.get('/api/jobs').json())==1
    again=s.api.post('/api/agent-v2/consent',json={'dataset_id':d['id'],'roles':['embedding']}).json()
    assert again['destinations']==notice['destinations']


def test_preflight_enforces_dataset_access_and_mapping(system):
    s=system;d=dataset(s)
    assert s.api.post('/api/agent-v2/consent',json={'dataset_id':d['id'],'planner_model_id':d['embedding_model_id'],'roles':['chat']}).status_code==409
    s.owner='bob'
    assert s.api.post('/api/agent-v2/consent',json={'dataset_id':d['id'],'roles':['embedding']}).status_code==404


def test_onboarding_preflight_checks_selected_profiles(system,monkeypatch):
    s=system;d=dataset(s);original=routing.profile_snapshot
    settings=main.core.settings() if hasattr(main,'core') else main.settings()
    from ags_app import core
    monkeypatch.setattr(core,'settings',lambda:{**settings,'storage_provider':'oci'})
    def snapshot(*args,**kwargs):
        result=original(*args,**kwargs)
        result['settings']={**result['settings'],'storage_provider':'oci','search_provider':'oracle'}
        return result
    monkeypatch.setattr(routing,'profile_snapshot',snapshot)
    response=s.api.post('/api/agent-v2/consent',json={'roles':['embedding','extraction'],'model_ids':{'embedding':d['embedding_model_id'],'extraction':d['default_extraction_model_id']}})
    assert response.status_code==200,response.text
    assert {item['title'] for item in response.json()['destinations']}=={'OCI Object Storage','OCI knowledge store'}
    assert s.api.get('/api/agent-v2/onboarding').json()==[]
    assert s.api.get('/api/jobs').json()==[]
