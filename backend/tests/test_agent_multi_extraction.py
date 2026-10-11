"""Multi-file choice, independent failures, recovery and exact merged scope."""
from sqlalchemy import select
from app import core, main, worker, providers, dataset_models as routing
from test_dataset_models import system, dataset, template, upload
from test_agent_workspace import plan, call

def setup(s):
    d=dataset(s);t=template(s)
    docs=[upload(s,d)['documents'][0]['id'] for _ in range(2)]
    return d,t,docs


def age_proposal(s,p):
    import time
    with s.session() as session:ref=session.get(core.Record,p['id']).ref
    data=core.store.json(ref);data['created_at']=time.time()-7200;core.store.put_json(ref,data)


def test_unstarted_proposal_still_expires(system):
    s=system;d,t,docs=setup(s)
    p=plan(s,d,text='extract',document_ids=docs[:1],template_id=t['id']);age_proposal(s,p)
    response=call(s,p,0)
    assert response.status_code==409 and 'expired' in response.json()['detail']


def test_confirmed_upload_can_finish_extraction_after_slow_ocr(system):
    from test_agent_workspace import send_files
    s=system;d=dataset(s);t=template(s)
    p=plan(s,d,text='extract',attached_filenames=['general.txt'],template_id=t['id'])
    assert send_files(s,p).status_code==200
    age_proposal(s,p)
    # Pending indexing still blocks extraction, regardless of the proposal age.
    assert call(s,p,1).status_code==409
    assert worker.run_once()
    response=call(s,p,1)
    assert response.status_code==200,response.text
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert all(c['status']=='completed' for c in done['calls'])

def test_multiple_documents_require_choice_and_merge_creates_one_result(system):
    s=system;d,t,docs=setup(s)
    p=plan(s,d,text='extract',document_ids=docs,template_id=t['id'])
    before=len(s.api.get('/api/jobs').json())
    assert call(s,p,0).status_code==422
    assert len(s.api.get('/api/jobs').json())==before
    r=call(s,p,0,extraction_mode='merge').json()
    entries=r['calls'][0]['result']['extractions'];assert len(entries)==1
    assert main.extraction(entries[0]['extraction_id'],s.owner)['document_ids']==docs
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['calls'][0]['status']=='completed'
    assert done['calls'][0]['result']['extractions'][0]['status']=='completed'

def test_independent_partial_failure_does_not_hide_success_or_duplicate_on_retry(system,monkeypatch):
    s=system;d,t,docs=setup(s)
    p=plan(s,d,text='extract',document_ids=docs,template_id=t['id'])
    r=call(s,p,0,extraction_mode='independent').json()
    entries=r['calls'][0]['result']['extractions'];assert [e['document_ids'] for e in entries]==[[docs[0]],[docs[1]]]
    original=providers.extract_with_evidence
    monkeypatch.setattr(providers,'extract_with_evidence',lambda *a:(_ for _ in ()).throw(providers.ProviderError('Selected content exceeds the local context budget (4,096 tokens).')))
    assert worker.run_once()
    mid=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert mid['calls'][0]['status']=='waiting'
    monkeypatch.setattr(providers,'extract_with_evidence',original)
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['calls'][0]['status']=='failed'
    assert sorted(e['status'] for e in done['calls'][0]['result']['extractions'])==['completed','failed']
    retry=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/recover',json={'action':'retry','confirmed':True})
    assert retry.status_code==200
    response=call(s,p,0,extraction_mode='independent').json()
    assert len(response['calls'][0]['job_ids'])==1
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    visible=[e for e in done['calls'][0]['result']['extractions'] if not e.get('superseded')]
    assert len(visible)==2 and all(e['status']=='completed' for e in visible)

def test_upload_and_extract_confirmation_persists_mode_and_template(system):
    s=system;d=dataset(s);t=template(s)
    p=plan(s,d,text='extract',attached_filenames=['a.txt','b.txt'],template_id=t['id'])
    path=f'/api/agent-v2/plans/{p["id"]}/calls/0/upload'
    files=[('files',('a.txt',b'Alice owns invoice 42','text/plain')),('files',('b.txt',b'Bob owns invoice 21','text/plain'))]
    form={'confirmed':'true','continue_extraction':'true','template_id':t['id'],'dataset_id':d['id']}
    assert s.api.post(path,data=form,files=files).status_code==422
    assert s.api.get('/api/documents').json()==[]
    r=s.api.post(path,data=form|{'extraction_mode':'independent'},files=files)
    assert r.status_code==200,r.text
    assert r.json()['auto_continue'] and r.json()['extraction_mode']=='independent'
    assert worker.run_once() and worker.run_once()
    # No browser polling or second confirmation is needed after indexing.
    with core.Session() as session:
        accepted=list(session.scalars(select(core.Record).where(core.Record.kind=='extraction')))
        assert len(accepted)==2
    assert call(s,p,1).status_code==200
    assert worker.run_once() and worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert all(c['status']=='completed' for c in done['calls'])

def test_failed_upload_can_continue_ready_and_ended_request_cannot_execute(system):
    s=system;d=dataset(s);t=template(s)
    p=plan(s,d,text='extract',attached_filenames=['a.txt','b.docx'],template_id=t['id'])
    r=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload',data={'confirmed':'true','dataset_id':d['id']},files=[('files',('a.txt',b'Valid invoice 42','text/plain')),('files',('b.docx',b'Broken','application/octet-stream'))])
    assert r.status_code==200
    assert worker.run_once() and worker.run_once()
    recover=f'/api/agent-v2/plans/{p["id"]}/calls/0/recover'
    assert s.api.post(recover,json={'action':'continue_ready','confirmed':False}).status_code==409
    done=s.api.post(recover,json={'action':'continue_ready','confirmed':True}).json()
    assert len(done['calls'][0]['uploaded_document_ids'])==1 and len(done['calls'][0]['skipped_document_ids'])==1
    assert call(s,p,1).status_code==200
    assert worker.run_once()

def test_cancel_blocks_pending_submission(system):
    s=system;d,t,docs=setup(s);p=plan(s,d,text='extract',document_ids=docs,template_id=t['id'])
    assert s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/recover',json={'action':'cancel','confirmed':True}).status_code==200
    assert call(s,p,0,extraction_mode='merge').status_code==409

def test_retry_pins_updated_context_without_changing_failed_job(system,monkeypatch):
    s=system;d,t,docs=setup(s)
    model=routing.owned(d['default_extraction_model_id'],s.owner,'model')
    profile=routing.owned(routing.model_data(model)['connection_profile_id'],s.owner,'config_profile')
    config=core.local_store.json(profile.ref);config['settings']['context_limit']=4096
    core.local_store.put_json(profile.ref,config)
    p=plan(s,d,text='extract',document_ids=docs[:1],template_id=t['id'])
    accepted=call(s,p,0).json();old_job=accepted['calls'][0]['job_ids'][0]
    monkeypatch.setattr(providers,'extract_with_evidence',lambda *a:(_ for _ in ()).throw(providers.ProviderError('Selected content exceeds the local context budget (4,096 tokens).')))
    assert worker.run_once()
    config['settings']['context_limit']=8192;core.local_store.put_json(profile.ref,config)
    assert s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/recover',json={'action':'retry','confirmed':True}).status_code==200
    new=call(s,p,0).json();new_job=new['calls'][0]['job_ids'][0]
    assert new_job!=old_job
    assert core.store.json('jobs/'+old_job+'.json')['execution']['settings']['context_limit']==4096
    assert core.store.json('jobs/'+new_job+'.json')['execution']['settings']['context_limit']==8192

def test_recovery_is_owned_and_cannot_expand_an_uploaded_scope(system,monkeypatch):
    s=system;d,t,docs=setup(s)
    p=plan(s,d,text='extract',document_ids=docs[:1],template_id=t['id'])
    call(s,p,0)
    monkeypatch.setattr(providers,'extract_with_evidence',lambda *a:(_ for _ in ()).throw(providers.ProviderError('Failed test generation')))
    assert worker.run_once()
    path=f'/api/agent-v2/plans/{p["id"]}/calls/0/recover'
    s.owner='other';assert s.api.post(path,json={'action':'retry','confirmed':True}).status_code==404
    s.owner='alice';assert s.api.post(path,json={'action':'retry','confirmed':True}).status_code==200
    before=len(s.api.get('/api/jobs').json())
    assert call(s,p,0,document_ids=docs,extraction_mode='merge').status_code==422
    assert len(s.api.get('/api/jobs').json())==before

def test_uncertain_submission_requires_history_inspection_not_blind_retry(system,monkeypatch):
    s=system;d,t,docs=setup(s);p=plan(s,d,text='extract',document_ids=docs,template_id=t['id'])
    monkeypatch.setattr(main,'create_extraction',lambda *a:(_ for _ in ()).throw(RuntimeError('uncertain acceptance')))
    assert call(s,p,0,extraction_mode='independent').status_code==502
    path=f'/api/agent-v2/plans/{p["id"]}/calls/0/recover'
    response=s.api.post(path,json={'action':'retry','confirmed':True})
    assert response.status_code==409 and 'duplicate work' in response.text
    assert s.api.post(path,json={'action':'cancel','confirmed':True}).status_code==200
