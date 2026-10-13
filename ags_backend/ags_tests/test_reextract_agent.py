"""Re-extract real API/worker/artifact/publication and recovery boundaries."""
import json,time
import pytest
from fastapi import HTTPException
from ags_app import core,worker,main,agent_model,agent_workspace,agent_goals,agent_onboarding,knowledge,parquet_results,reextract_agent
from test_dataset_models import system,dataset,template,upload,post
from test_agent_workspace import plan,call

def setup(s,monkeypatch,documents=1,direct=False,stream=False):
    d=dataset(s);t=template(s);docs=[upload(s,d)['documents'][0] for _ in range(documents)]
    original=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[x['id'] for x in docs],'template_id':t['id']})
    assert worker.run_once()
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('Explicit @ReExtract must skip classification.') if direct else {'intent':'run_workflow','source':'action','operation':'reextract'})
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:pytest.fail('Re-extract must not rediscover tools or run an answer model.'))
    p=plan(s,d,text='@ReExtract' if direct else 'Re-extract the selected saved documents.',document_ids=[x['id'] for x in docs],template_id=t['id'],stream_answers=stream)
    if stream:
        from test_agent_chat import reply
        from test_chat_stream import events
        p=events(reply(s,p))[-1]['plan']
    return d,t,docs,original,p

@pytest.mark.parametrize('direct,stream',[(False,False),(True,False),(True,True)])
def test_direct_agent_creates_one_confirmed_rerun_and_publishes_verified_artifacts(system,monkeypatch,direct,stream):
    s=system;d,t,docs,original,p=setup(s,monkeypatch,direct=direct,stream=stream)
    assert p['agent']=='reextract' and p['model_calls']==(0 if direct else 1) and [c['tool'] for c in p['calls']]==['reextract']
    assert p['document_ids']==[x['id'] for x in docs] and p['template_id']==t['id']
    before=s.api.get('/api/jobs').json()
    assert s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0',json={'confirmed':False}).status_code==409
    assert s.api.get('/api/jobs').json()==before
    submitted=call(s,p,0).json();updated=submitted['calls'][0]['result']['extraction_id']
    assert updated!=original['id']
    assert call(s,p,0).json()['calls'][0]['result']['extraction_id']==updated
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    c=done['calls'][0];assert c['status']=='completed' and done['goal']['status']=='completed'
    artifact=c['vector_publication']['verified_artifacts'][0]
    saved=core.store.json(main.get_record(updated,s.owner,'extraction').ref)
    assert artifact['reference']==saved['output_reference'] and artifact['sha256']==saved['output_sha256']
    assert parquet_results.load(saved)['result']==saved['result']
    assert s.api.get('/api/extractions/'+original['id']).json()['status']=='ready'
    assert done['goal']['answer']['request_route']['model_calls']==0
    assert done['goal']['answer']['review_actions'][0]['extraction_id']==updated
    thread=core.store.json(main.get_record(done['conversation_id'],s.owner,'conversation').ref)
    count=sum(m.get('goal_id')==p['id']+':0' for m in thread['messages'])
    agent_workspace.advance_workflows()
    again=core.store.json(main.get_record(done['conversation_id'],s.owner,'conversation').ref)
    assert count==1 and sum(m.get('goal_id')==p['id']+':0' for m in again['messages'])==1

def test_vector_outage_retries_saved_parquet_without_new_jobs(system,monkeypatch):
    s=system;d,t,docs,original,p=setup(s,monkeypatch)
    updated=call(s,p,0).json()['calls'][0]['result']['extraction_id']
    publish=agent_onboarding.publish_knowledge
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',lambda *a:(_ for _ in ()).throw(HTTPException(503,'Synthetic OCI vector outage')))
    assert worker.run_once()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['publication_error'] and failed['goal']['status']!='completed'
    assert s.api.get('/api/extractions/'+updated).json()['status']=='ready'
    jobs=s.api.get('/api/jobs').json()
    assert s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/recover',json={'confirmed':True,'action':'retry'}).status_code==409
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',publish)
    waiting=post(s,f'/api/agent-v2/plans/{p["id"]}/knowledge/retry',{'confirmed':True})
    assert waiting['calls'][0]['publication_pending'] and waiting['calls'][0]['status']=='waiting'
    agent_workspace.advance_workflows()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['calls'][0]['status']=='completed' and done['goal']['status']=='completed'
    assert done['calls'][0]['result']['extraction_id']==updated and s.api.get('/api/jobs').json()==jobs

def test_get_never_publishes_and_expired_publication_lease_recovers(system,monkeypatch):
    s=system;d,t,docs,original,p=setup(s,monkeypatch)
    call(s,p,0)
    advance=agent_workspace.advance_workflows
    monkeypatch.setattr(agent_workspace,'advance_workflows',lambda **kw:None)
    assert worker.run_once()
    monkeypatch.setattr(agent_workspace,'advance_workflows',advance)
    record=main.get_record(p['id'],s.owner,'agent_plan')
    pending=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert pending['calls'][0]['status']=='waiting' and pending['calls'][0]['publication_pending']
    data=core.store.json(record.ref);data['calls'][0].update(publication_lease_until=time.time()+30,publication_token='old',publication_status='running')
    agent_workspace.save_plan(record,data)
    publisher=agent_onboarding.publish_knowledge
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',lambda *a:pytest.fail('An active publication lease cannot be duplicated.'))
    reextract_agent.publish_pending(record,main)
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'][0]['status']=='waiting'
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',publisher)
    data=core.store.json(record.ref);data['calls'][0]['publication_lease_until']=time.time()-1
    agent_workspace.save_plan(record,data);advance()
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['goal']['status']=='completed'

def test_corrupt_parquet_prevents_completion(system,monkeypatch):
    s=system;d,t,docs,original,p=setup(s,monkeypatch)
    updated=call(s,p,0).json()['calls'][0]['result']['extraction_id']
    advance=agent_workspace.advance_workflows;monkeypatch.setattr(agent_workspace,'advance_workflows',lambda **kw:None)
    assert worker.run_once();monkeypatch.setattr(agent_workspace,'advance_workflows',advance)
    saved=core.store.json(main.get_record(updated,s.owner,'extraction').ref)
    core.store.put(saved['output_reference'],b'corrupt test artifact')
    advance()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['publication_error'] and failed['goal']['status']!='completed'

def test_independent_rerun_preserves_each_result_and_never_repeats_successful_job(system,monkeypatch):
    s=system;d,t,docs,original,p=setup(s,monkeypatch,2)
    submitted=call(s,p,0,extraction_mode='independent').json()
    assert len(submitted['calls'][0]['job_ids'])==2
    assert worker.run_once();assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['goal']['status']=='completed'
    assert len(done['calls'][0]['vector_publication']['verified_artifacts'])==2

@pytest.mark.parametrize('stream',[False,True])
def test_reextract_attached_files_confirms_upload_then_rerun_and_publication(system,monkeypatch,stream):
    s=system;d,t,docs,original,p=setup(s,monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('Direct Re-extract must not classify attachments.'))
    p=plan(s,d,text='@ReExtract with the existing prompt',document_ids=[docs[0]['id']],template_id=t['id'],attached_filenames=['new.txt'],stream_answers=stream)
    if stream:
        from test_agent_chat import reply
        from test_chat_stream import events
        p=events(reply(s,p))[-1]['plan']
    assert p['agent']=='reextract' and p['model_calls']==0
    assert [c['tool'] for c in p['calls']]==['upload','reextract']
    assert p['phase']=='awaiting_confirmation' and p['document_ids']==[]
    before=s.api.get('/api/jobs').json()
    payload={'dataset_id':d['id'],'template_id':t['id'],'continue_extraction':'true','confirmed':'false'}
    files={'files':('new.txt',b'New confirmed source for extraction.','text/plain')}
    endpoint=f'/api/agent-v2/plans/{p["id"]}/calls/0/upload'
    assert s.api.post(endpoint,data=payload,files=files).status_code==409
    assert s.api.get('/api/jobs').json()==before
    payload['confirmed']='true';accepted=s.api.post(endpoint,data=payload,files=files)
    assert accepted.status_code==200,accepted.text
    updated=accepted.json()['calls'][1]['result']['extraction_id']
    references=accepted.json()['calls'][0]['uploaded_document_ids']
    assert docs[0]['id'] not in references
    assert worker.run_once();assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['goal']['status']=='completed'
    assert all(c['status']=='completed' and c['vector_publication']['verified_vectors']>0 for c in done['calls'])
    saved=s.api.get('/api/extractions/'+updated).json()
    assert saved['document_ids']==references and saved['template_id']==t['id']
    artifact=core.store.json(main.get_record(updated,s.owner,'extraction').ref)
    assert parquet_results.load(artifact)['result']==artifact['result']
    assert done['calls'][1]['vector_publication']['verified_artifacts'][0]['sha256']==artifact['output_sha256']
    assert s.api.get('/api/extractions/'+original['id']).json()['status']=='ready'
    jobs=s.api.get('/api/jobs').json()
    assert s.api.post(endpoint,data=payload,files=files).json()['calls'][1]['result']['extraction_id']==updated
    assert s.api.get('/api/jobs').json()==jobs


@pytest.mark.parametrize('attachments',[[],['new.txt']])
@pytest.mark.parametrize('text',['@ReExtract','re-extract'])
def test_reextract_missing_dataset_and_prompt_opens_input_workflow(system,monkeypatch,attachments,text):
    s=system;d=dataset(s)
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('No inference for explicit Re-extract.'))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:pytest.fail('No answer inference for workflow inputs.'))
    p=plan(s,d,text=text,dataset_id='',attached_filenames=attachments)
    assert p['agent']=='reextract' and p['phase']=='awaiting_confirmation'
    assert [c['tool'] for c in p['calls']]==(['upload','reextract'] if attachments else ['reextract'])
    assert p['dataset_id']=='' and p['template_id']=='' and p['document_ids']==[]
    assert s.api.get('/api/jobs').json()==[]
    assert s.api.get('/api/documents').json()==[]

def test_independent_retry_only_resubmits_failed_document(system,monkeypatch):
    s=system;d,t,docs,original,p=setup(s,monkeypatch,2)
    submitted=call(s,p,0,extraction_mode='independent').json();jobs=submitted['calls'][0]['job_ids']
    assert worker.run_once()
    process=worker.process
    def fail_second(jid,token):
        if jid==jobs[1]:raise ValueError('Synthetic second document failure')
        return process(jid,token)
    monkeypatch.setattr(worker,'process',fail_second);assert worker.run_once()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['status']=='failed' and failed['goal']['status']!='completed'
    first=failed['calls'][0]['result']['extractions'][0]['extraction_id']
    post(s,f'/api/agent-v2/plans/{p["id"]}/calls/0/recover',{'confirmed':True,'action':'retry'})
    retry=call(s,p,0,extraction_mode='independent').json()
    assert len(retry['calls'][0]['job_ids'])==1
    assert retry['calls'][0]['result']['extractions'][0]['extraction_id']==first
    monkeypatch.setattr(worker,'process',process);assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['goal']['status']=='completed' and len(done['goal']['extraction_ids'])==2

def test_native_vector_count_alone_cannot_verify_an_altered_payload(system,monkeypatch):
    from types import SimpleNamespace
    from ags_app import providers
    from test_chat_agent import prepared
    s=system;d,doc,t,ex=prepared(s)
    snapshot,receipt=knowledge.sync(s.owner,d['id'])
    manifest=core.local_store.json(knowledge._manifest_ref(snapshot));snapshot['settings']['search_provider']='oracle'
    def scroll(*args,**kw):
        ids=kw['scroll_filter'].must[0].has_id
        points=[SimpleNamespace(id=id,payload=dict(manifest['points'][id])) for id in ids]
        points[0].payload['text']='Wrong native vector contents'
        return points,None
    native=SimpleNamespace(count=lambda *a,**kw:SimpleNamespace(count=len(kw['count_filter'].must[0].has_id)),scroll=scroll)
    monkeypatch.setattr(knowledge,'sync',lambda *a:(snapshot,receipt));monkeypatch.setattr(providers,'client',lambda:native)
    with pytest.raises(HTTPException,match='contents do not match'):
        agent_onboarding.publish_knowledge({'dataset_id':d['id'],'template_id':t['id'],'document_ids':[doc['id']],'extraction_ids':[ex['id']]},s.owner)

def test_stale_index_publication_retry_continues_the_already_confirmed_rerun(system,monkeypatch):
    from test_agent_workspace import stale_index
    s=system;d,t,docs,original,p=setup(s,monkeypatch);stale_index(docs[0])
    submitted=call(s,p,0).json()
    assert [c['tool'] for c in submitted['calls']]==['upload','reextract']
    publisher=agent_onboarding.publish_knowledge
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',lambda *a:(_ for _ in ()).throw(HTTPException(503,'Synthetic publication outage')))
    assert worker.run_once()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['publication_error'] and failed['calls'][1]['status']=='pending'
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',publisher)
    post(s,f'/api/agent-v2/plans/{p["id"]}/knowledge/retry',{'confirmed':True})
    agent_workspace.advance_workflows()
    resumed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert resumed['calls'][1]['status']=='waiting'
    assert worker.run_once()
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['goal']['status']=='completed'

def test_reconciliation_and_publication_skip_readonly_question_archives(system,monkeypatch):
    from ags_app import dataset_models as routing
    s=system;d=dataset(s)
    record=routing.create('agent_plan',s.owner,'Long archived question',{'calls':[],'request':'irrelevant history '*20000},parent=d['id'],status='query')
    read=core.store.json
    def without_archive(ref):
        if ref==record.ref:pytest.fail('Processing and publication must not download archived questions.')
        return read(ref)
    monkeypatch.setattr(core.store,'json',without_archive)
    agent_workspace.advance_workflows();knowledge.sync(s.owner,d['id'])
