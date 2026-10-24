"""New reruns use current dataset routes; accepted jobs keep their pinned routes."""
import pytest
from ags_app import core, main, worker, providers, dataset_models as routing
from test_dataset_models import system, dataset, upload, template, model, mapping, post
from test_dataset_ocr_selection import vision, choose
from test_ocr import scan
from ags_app.ags_models.connection import ModelConnection


@pytest.mark.parametrize('action',['reextract','resume'])
def test_result_rerun_replaces_old_explicit_selection_with_current_default(system,monkeypatch,action):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    old=next(m for m in d['models'] if m['id']==d['default_extraction_model_id'])
    newer=model(s,old['connection_profile_id'],'New mapped extraction')
    mapping(s,d,mappings=d['mappings']+[{'model_id':newer['id'],'enabled':True}])
    request={'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id'],'model_id':old['id'],'idempotency_key':'original-request'}
    e=post(s,'/api/extractions',request)
    assert worker.run_once()
    original=core.store.json(main.get_record(e['id'],s.owner,'extraction').ref)
    if action=='resume':
        with core.Session.begin() as session:session.get(core.Record,e['id']).status='failed'
    mapping(s,d,default_extraction_model_id=newer['id'])
    result=post(s,f'/api/extractions/{e["id"]}/{action}',{'version':1,**({'template_id':t['id']} if action=='resume' else {})})
    saved=core.store.json(main.get_record(e['id'],s.owner,'extraction').ref)
    pinned=core.store.json('jobs/'+result['job']['id']+'.json')['execution']
    assert saved['model_id']==pinned['model_id']==newer['id']
    assert result['model_selection']['model_id']==newer['id']
    assert core.store.json(f'extraction/{e["id"]}/v1.json')==original
    # The accepted rerun keeps its new selection even if the default changes again.
    mapping(s,d,default_extraction_model_id=old['id'])
    replay=post(s,'/api/extractions',request)
    assert replay['id']==e['id'] and replay['job']['id']==result['job']['id']
    assert replay['model_selection']['model_id']==newer['id']
    called=[]
    def extract(*args):
        called.append(core.settings()['model']);return {'data':{'owner':'Alice'},'evidence':[]}
    monkeypatch.setattr(providers,'extract',extract)
    assert worker.run_once()
    assert called==['New mapped extraction']


def test_changed_cloud_ocr_rebuilds_scan_before_review_rerun(system,monkeypatch):
    s=system;d=dataset(s);mini=vision(s);full=vision(s,'gpt-4o');choose(s,d,mini)
    called=[]
    def send(self,path,payload,headers=None):
        called.append(payload['model'])
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"text":"Alice is the owner. Synthetic total USD 42.50","unreadable":false}'}}]}
    monkeypatch.setattr(ModelConnection,'post',send)
    monkeypatch.setattr(providers,'extract',lambda *a:{'data':{'owner':'Alice'},'evidence':[]})
    raw=scan()
    response=s.api.post('/api/documents/upload',files={'files':('scan.pdf',raw,'application/pdf')},data={'dataset_id':d['id'],'allow_external':'true'})
    assert response.status_code==200,response.text
    doc=response.json()['documents'][0];assert worker.run_once()
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':template(s)['id']})
    assert worker.run_once()
    before=core.store.json(main.get_record(e['id'],s.owner,'extraction').ref)
    choose(s,d,full)
    assert s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    rerun=post(s,f'/api/extractions/{e["id"]}/rerun',{'source_version':1,'template_id':e['template_id'],'display_name':'Current cloud rerun','idempotency_key':'current-cloud','allow_external':True})
    assert rerun['calls'][0]['tool']=='upload'
    jid=rerun['calls'][0]['job_ids'][0]
    assert core.store.json('jobs/'+jid+'.json')['execution']['ocr_execution']['model_id']==full['id']
    assert worker.run_once();assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+rerun['id']).json()
    updated=done['calls'][-1]['result']['extractions'][0]['extraction_id']
    assert updated!=e['id'] and s.api.get('/api/extractions/'+updated).json()['status']=='ready'
    assert called==['gpt-4o-mini','gpt-4o']
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']
    assert core.store.get('documents/'+doc['id']+'/original')==raw
    assert core.store.json(main.get_record(e['id'],s.owner,'extraction').ref)==before


def test_changed_ocr_does_not_invalidate_native_text_index(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];choose(s,d,vision(s))
    assert not s.api.get('/api/documents/'+doc['id']).json()['requires_reindex']


@pytest.mark.parametrize('kind',['index','extract'])
def test_retry_rejects_outdated_cloud_routes_without_state_changes(system,kind):
    s=system;d=dataset(s);pending=upload(s,d,run=False)
    if kind=='index':
        j=pending['jobs'][0];choose(s,d,vision(s))
    else:
        assert worker.run_once()
        e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[pending['documents'][0]['id']],'template_id':template(s)['id']})
        j=e['job'];old=next(m for m in d['models'] if m['id']==d['default_extraction_model_id'])
        newer=model(s,old['connection_profile_id'],'New default')
        mapping(s,d,mappings=d['mappings']+[{'model_id':newer['id'],'enabled':True}],default_extraction_model_id=newer['id'])
    post(s,'/api/jobs/'+j['id']+'/cancel')
    before=core.store.json('jobs/'+j['id']+'.json')
    rejected=s.api.post('/api/jobs/'+j['id']+'/retry')
    assert rejected.status_code==409 and 'model' in rejected.json()['detail']
    assert core.store.json('jobs/'+j['id']+'.json')==before
    assert next(job for job in s.api.get('/api/jobs').json() if job['id']==j['id'])['status']=='cancelled'
