"""Explicit user routes skip inference and preserve workflow authorization."""
import pytest,json
from pydantic import ValidationError
from app import agent_model,agent_workspace,worker
from test_dataset_models import system,dataset,template,upload
from test_agent_workspace import plan,call,send_files
from test_agent_chat import reply
from test_chat_stream import events

@pytest.mark.parametrize('operation',['upload','extract','reextract'])
@pytest.mark.parametrize('stream',[False,True])
def test_explicit_agent_bypasses_all_inference_and_requires_confirmation(system,monkeypatch,operation,stream):
    s=system;d=dataset(s)
    def forbidden(*args,**kwargs):pytest.fail('Explicit agent selection must not use classification or answer inference.')
    monkeypatch.setattr(agent_model,'classify',forbidden);monkeypatch.setattr(agent_model,'complete',forbidden)
    # Explicit directives work even with the retained legacy fallback enabled.
    p=plan(s,d,text='@'+operation.title(),stream_answers=stream)
    if stream:p=events(reply(s,p))[-1]['plan']
    assert p['agent']==('reextract' if operation=='reextract' else 'onboard_extract') and p['model_calls']==0
    assert [c['tool'] for c in p['calls']]==[operation]
    assert p['phase']=='awaiting_confirmation'
    message=s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']
    assert message['request_route']['routing_mode']=='explicit'
    assert message['request_route']['attempts']==[]
    assert not any(step['label']=='Understanding request' for step in message['answer_workflow']['steps'])
    assert s.api.get('/api/jobs').json()==[]
    rejected=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload',data={'dataset_id':d['id'],'confirmed':'false'},files={'files':('sample.txt',b'Sample text','text/plain')}) if operation=='upload' else s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0',json={'confirmed':False})
    assert rejected.status_code==409
    assert s.api.get('/api/jobs').json()==[]

def test_explicit_extract_keeps_real_dataset_document_and_prompt_scope(system,monkeypatch):
    s=system;d=dataset(s);t=template(s);doc=upload(s,d)['documents'][0]
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda *args:pytest.fail('No classifier'))
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:pytest.fail('No answer model'))
    p=plan(s,d,text='@Extract',document_ids=[doc['id']],template_id=t['id'])
    before=s.api.get('/api/jobs').json()
    assert p['calls'][0]['tool']=='extract' and s.api.get('/api/jobs').json()==before
    result=call(s,p,0).json();id=result['calls'][0]['result']['extraction_id']
    # Completing a confirmed extraction may compose its result summary; this
    # is not routing and must use only already saved fields, without tools.
    def summarize(messages,tools,**kwargs):
        assert tools==[] and 'MOCK TEST VALUE' in json.dumps(messages)
        return {'text':'Extraction completed. Owner: MOCK TEST VALUE.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',summarize)
    assert worker.run_once()
    saved=s.api.get('/api/extractions/'+id).json()
    assert saved['status']=='ready' and saved['result']['owner']=='MOCK TEST VALUE'
    assert saved['document_ids']==[doc['id']] and saved['template_id']==t['id']
    other=dataset(s,'Other');foreign=upload(s,other)['documents'][0]
    assert s.api.post('/api/agent-v2/plans',json={'text':'@Extract','agent_operation':'extract','dataset_id':d['id'],'planner_model_id':d['default_chat_model_id'],'document_ids':[foreign['id']]}).status_code==400

def test_explicit_upload_indexes_only_confirmed_attachments(system,monkeypatch):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda *args:pytest.fail('No classifier'))
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:pytest.fail('No answer model'))
    p=plan(s,d,text='@Upload',attached_filenames=['general.txt'])
    assert s.api.get('/api/documents').json()==[]
    uploaded=send_files(s,p);assert uploaded.status_code==200,uploaded.text
    assert worker.run_once()
    assert [doc['status'] for doc in s.api.get('/api/documents').json()]==['ready']
    assert s.api.get('/api/extractions').json()==[]
    finished=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert finished['calls'][0]['status']=='completed' and finished['calls'][0]['vector_publication']

def test_only_leading_current_user_directives_select_an_agent():
    for text in ('Email upload@example.com','Summarize @Upload','"@Extract"'):
        assert agent_workspace.PlanInput(text=text,planner_model_id='model').agent_operation is None
    assert agent_workspace.PlanInput(text='  @EXTRACT file.pdf',planner_model_id='model').agent_operation=='extract'
    assert agent_workspace.PlanInput(text='  @onBOARD',planner_model_id='model').agent_operation=='onboard'
    assert agent_workspace.PlanInput(text='  @reEXTRACT saved documents',planner_model_id='model').agent_operation=='reextract'
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@Upload',planner_model_id='model',agent_operation='extract')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='Run it',planner_model_id='model',agent_operation='delete')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@Uploader',planner_model_id='model')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@Onboarded',planner_model_id='model')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@Onboard',planner_model_id='model',agent_operation='upload')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@Reextractor',planner_model_id='model')
    with pytest.raises(ValidationError):agent_workspace.PlanInput(text='@ReExtract',planner_model_id='model',agent_operation='extract')


@pytest.mark.parametrize('stream',[False,True])
@pytest.mark.parametrize('selected',[False,True])
def test_explicit_onboard_opens_setup_without_inference_or_processing(system,monkeypatch,stream,selected):
    from app import main
    s=system;d=dataset(s)
    def forbidden(*args,**kwargs):pytest.fail('Opening direct onboarding must not invoke a model or request external processing consent.')
    monkeypatch.setattr(agent_model,'classify',forbidden);monkeypatch.setattr(agent_model,'complete',forbidden)
    monkeypatch.setattr(main,'external_check',forbidden)
    p=plan(s,d,text='@onboard',dataset_id=d['id'] if selected else '',stream_answers=stream)
    if stream:p=events(reply(s,p))[-1]['plan']
    assert p['agent']=='onboard_extract' and p['model_calls']==0
    assert p['onboarding']=={'name':'','description':''} and p['calls']==[]
    assert p['phase']=='awaiting_confirmation'
    chat=s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']
    assert chat['request_route']['routing_mode']=='explicit'
    assert chat['request_route']['requested_operation']=='onboard'
    assert chat['request_route']['decision']['operation']=='onboard_dataset'
    assert chat['request_route']['attempts']==[]
    assert s.api.get('/api/agent-v2/onboarding').json()==[]
    assert len(s.api.get('/api/datasets').json())==1
    assert s.api.get('/api/jobs').json()==[]


def test_direct_onboard_confirms_existing_full_processing_workflow(system,monkeypatch):
    from test_agent_onboarding import processing_body,stage,finish
    from test_dataset_models import post
    s=system;d=dataset(s)
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('No classifier for @Onboard'))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:pytest.fail('No planning model for @Onboard'))
    p=plan(s,d,text='@Onboard')
    body,files=processing_body(d);body['plan_id']=p['id']
    workflow=finish(s,stage(s,post(s,'/api/agent-v2/onboarding',body),files))
    saved=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert saved['onboarding_workflow_id']==workflow['id']
    assert workflow['status']=='completed' and workflow['vector_publication']['verified_vectors']>0
    assert len(workflow['vector_publication']['parquet_files'])==2
    assert all(s.api.get('/api/extractions/'+id).json()['result'] for id in workflow['extraction_ids'])
