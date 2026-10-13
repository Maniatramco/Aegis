"""Real storage/API/graph invariants for confirmed dataset onboarding."""
import uuid
import hashlib
import pytest
from fastapi import HTTPException
from app import core, main, dataset_models as routing, agent_onboarding, agent_model, dataset_access
from test_dataset_models import system, dataset, post
from app.agent_tools import Tools
from app.agent_workspace import PlanInput
from test_agent_chat import reply
from test_chat_stream import events
from app import worker
import json


def test_agent_named_document_scope_is_resolved_before_proposing_extraction(system,monkeypatch):
    from test_agent_workspace import plan
    from test_dataset_models import template
    s=system;d=dataset(s);t=template(s)
    response=s.api.post('/api/documents/upload',files=[('files',(name,b'Alice is the owner.','text/plain')) for name in ('target.txt','other.txt')],data={'dataset_id':d['id']})
    assert response.status_code==200,response.text
    doc=response.json()['documents'][0]
    while worker.run_once():pass
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'intent':'run_workflow','source':'action','operation':'extract','document_names':['target.txt']})
    monkeypatch.setattr(agent_model,'complete',lambda *a:pytest.fail('The operation and named scope are resolved.'))
    p=plan(s,d,text='Extract target.txt using the selected prompt.',template_id=t['id'])
    assert p['document_ids']==[doc['id']] and p['model_calls']==1
    assert all(job['kind']=='index' and job['status']=='completed' for job in s.api.get('/api/jobs').json())


def test_existing_dataset_agent_requires_vectors_and_retries_without_reextracting(system,monkeypatch):
    from test_agent_workspace import plan,call
    from test_dataset_models import template,upload
    s=system;d=dataset(s);t=template(s);doc=upload(s,d)['documents'][0]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'intent':'run_workflow','source':'action','operation':'extract'})
    monkeypatch.setattr(agent_model,'complete',lambda *a:pytest.fail('A resolved operation must not call a second tool-selection model.'))
    p=plan(s,d,text='Extract the selected document.',document_ids=[doc['id']],template_id=t['id'])
    assert p['agent']=='onboard_extract' and p['model_calls']==1
    submitted=call(s,p,0).json();ex=submitted['calls'][0]['result']['extraction_id']
    publish=agent_onboarding.publish_knowledge
    def unavailable(*a):raise HTTPException(503,'Synthetic vector outage')
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',unavailable)
    assert worker.run_once()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['status']=='failed' and failed['calls'][0]['publication_error']
    assert s.api.get('/api/extractions/'+ex).json()['status']=='ready'
    jobs=s.api.get('/api/jobs').json()
    assert s.api.post('/api/agent-v2/plans/'+p['id']+'/knowledge/retry',json={'confirmed':False}).status_code==400
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',publish)
    recovered=post(s,'/api/agent-v2/plans/'+p['id']+'/knowledge/retry',{'confirmed':True})
    completed=recovered['calls'][0]
    assert completed['status']=='completed' and not completed.get('publication_error')
    assert completed['result']['extraction_id']==ex
    assert completed['vector_publication']['verified_vectors']>0
    assert len(completed['vector_publication']['parquet_files'])==1
    assert s.api.get('/api/jobs').json()==jobs
    assert s.api.post('/api/agent-v2/plans/'+p['id']+'/knowledge/retry',json={'confirmed':True}).status_code==409


def processing_body(d, mode='independent'):
    files = [('one.txt', b'Alice is the owner. Invoice total 42.'), ('two.txt', b'Bob is the owner. Invoice total 24.')]
    return setup_body(d) | {'processing': {
        'documents': [{'name': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files],
        'prompt_name': 'owner-prompt.json', 'schema': {'type': 'object', 'properties': {'owner': {'type':'string'}}, 'required': ['owner'], 'additionalProperties': False},
        'instructions': 'Read the owner from the source.', 'extraction_mode': mode}}, files


def stage(s, w, files):
    response = s.api.post(f'/api/agent-v2/onboarding/{w["id"]}/files', files=[('files', (name, raw, 'text/plain')) for name, raw in files])
    assert response.status_code == 200, response.text
    return response.json()


def finish(s, w):
    for _ in range(30):
        w = advance(s, w)
        assert w['status'] != 'failed', w.get('error')
        if w['status'] == 'completed': return w
        if w['status'] == 'waiting':
            while worker.run_once(): pass
    raise AssertionError(w)


@pytest.mark.parametrize('mode', ['independent', 'merge'])
def test_full_onboarding_runs_actual_upload_index_and_extraction_pipeline(system, mode):
    s=system; body, files=processing_body(dataset(s), mode); w=post(s, '/api/agent-v2/onboarding', body)
    w=stage(s, w, files); assert s.api.get('/api/jobs').json()==[]
    for _ in range(5): w=advance(s,w)
    assert len(w['document_ids'])==2 and w['template_id']
    pending=advance(s,w); assert pending['status']=='waiting' and pending['steps'][5]['status']=='running'
    # A restored workflow is sufficient; no file reattachment is needed.
    restored=s.api.get(f'/api/agent-v2/onboarding/{w["id"]}').json()
    assert restored['files_saved']; w=finish(s,restored)
    assert len(w['extraction_ids'])==(2 if mode=='independent' else 1)
    assert all(step['status']=='completed' for step in w['steps'])
    assert w['vector_publication']['verified_vectors']>0
    assert len(w['vector_publication']['parquet_files'])==len(w['extraction_ids'])
    assert all(s.api.get('/api/extractions/'+id).json()['result'] is not None for id in w['extraction_ids'])
    assert len(s.api.get('/api/documents').json())==2
    assert s.api.get('/api/templates').json()[0]['version']==1
    assert advance(s,w)==w


def test_full_onboarding_rejects_schema_and_changed_files_before_any_dataset_write(system):
    s=system; body,files=processing_body(dataset(s))
    bad=body | {'processing': body['processing'] | {'schema': {'type':'object'}}}
    assert s.api.post('/api/agent-v2/onboarding',json=bad).status_code==400
    assert len(s.api.get('/api/datasets').json())==1
    w=post(s,'/api/agent-v2/onboarding',body)
    response=s.api.post(f'/api/agent-v2/onboarding/{w["id"]}/files',files=[('files',(name,raw+b'changed','text/plain')) for name,raw in files])
    assert response.status_code==409
    assert not s.api.get(f'/api/agent-v2/onboarding/{w["id"]}').json().get('files_saved')
    assert s.api.get('/api/jobs').json()==[]


@pytest.mark.parametrize('point', ['upload', 'extraction'])
def test_full_retry_after_accepted_submission_never_duplicates_files_prompts_or_results(system, monkeypatch, point):
    s=system; body,files=processing_body(dataset(s)); w=stage(s,post(s,'/api/agent-v2/onboarding',body),files)
    if point=='upload':
        original=main.upload
        async def interrupted(**kwargs):
            await original(**kwargs); raise HTTPException(503,'Upload receipt interrupted')
        monkeypatch.setattr(main,'upload',interrupted)
        for _ in range(5): w=advance(s,w)
    else:
        for _ in range(5): w=advance(s,w)
        while worker.run_once(): pass
        w=advance(s,w)
        original=main.create_extraction
        def interrupted(*args):
            original(*args); raise HTTPException(503,'Extraction receipt interrupted')
        monkeypatch.setattr(main,'create_extraction',interrupted); w=advance(s,w)
    assert w['status']=='failed'
    monkeypatch.setattr(main,'upload' if point=='upload' else 'create_extraction',original)
    w=finish(s,w)
    assert len(s.api.get('/api/datasets').json())==2
    assert len(s.api.get('/api/documents').json())==2
    assert len(s.api.get('/api/extractions').json())==2
    assert s.api.get('/api/templates').json()[0]['version']==1


@pytest.mark.parametrize('status', ['failed', 'cancelled'])
def test_failed_worker_requires_explicit_retry_and_resumes_retained_result(system, status):
    s=system; body,files=processing_body(dataset(s),'merge'); w=stage(s,post(s,'/api/agent-v2/onboarding',body),files)
    for _ in range(5): w=advance(s,w)
    while worker.run_once(): pass
    w=advance(s,w); w=advance(s,w); id=w['extraction_ids'][0]
    with core.Session.begin() as session:
        target=session.get(core.Record,id); target.status=status;target.error='Synthetic provider outage'
        from sqlalchemy import select
        for job in session.scalars(select(core.Job).where(core.Job.target_id==id)):
            job.status=status;job.error=target.error
    w=advance(s,w);assert w['status']=='failed' and 'outage' in w['error']
    w=finish(s,w)
    assert w['extraction_ids']==[id]
    assert s.api.get('/api/extractions/'+id).json()['version']==(2 if status=='failed' else 1)
    assert len(s.api.get('/api/documents').json())==2


def test_full_chat_proposal_publishes_verified_processing_receipt_and_tool_metadata(system, monkeypatch):
    s=system; d=dataset(s); monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'intent':'run_workflow','source':'action','operation':'onboard_dataset','fields':[]})
    monkeypatch.setattr(agent_model,'complete',lambda messages,tools:{'text':'','calls':[{'id':core.uid(),'name':'prepare_dataset_onboarding','arguments':{'name':'Agent onboarding QA','description':''}}]})
    plan=post(s,'/api/agent-v2/plans',{'text':'Onboard a new dataset with documents, a prompt and extraction','dataset_id':d['id'],'planner_model_id':d['default_chat_model_id']})
    body,files=processing_body(d); body['plan_id']=plan['id']
    w=finish(s,stage(s,post(s,'/api/agent-v2/onboarding',body),files))
    saved=s.api.get('/api/agent-v2/plans/'+plan['id']).json()
    assert saved['onboarding_workflow_id']==w['id']
    assert '2 documents' in saved['explanation'] and 'owner-prompt.json' in saved['explanation'] and '2 extraction results' in saved['explanation']
    tools=Tools(s.owner,PlanInput(text='What is the onboarding status?',dataset_id=w['dataset_id'],planner_model_id=d['default_chat_model_id']),'',main)
    facts=tools.get_dataset_onboarding_status()['onboardings'][0]
    assert facts['document_names']==['one.txt','two.txt'] and facts['extraction_ids']==w['extraction_ids'] and facts['prompt_name']=='owner-prompt.json'
    receipt=tools.snapshot()['recent_dataset_onboarding'][0]
    assert receipt['completed_result_count']==2 and 'steps' not in receipt and 'extraction_ids' not in receipt


def test_onboarding_reference_classification_fits_registered_local_8192_context(system, monkeypatch):
    from app import ollama_provider
    context={'available_result_fields':['supplier','invoice_number','total_amount'],'latest_workflow':None,
        'recent_dataset_onboarding':[{'name':name,'status':'completed'} for name in ['Agent full onboarding browser QA','Agent final onboarding QA','Agent natural onboarding QA']], 'previous_user_request':None}
    frame={'intent':'answer','source':'metadata','supplementary_sources':[],'operation':'none','fields':[],
        'document_names':[],'answer_kind':'list','filters':[],'result_scope':'selected_scope',
        'initial_reads':['list_documents','get_dataset_status'],'metadata_answer':'none'}
    seen=[]
    def request(path,payload,timeout):
        seen.append(payload)
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'tool_calls':[{'name':'select_source','arguments':frame}],'answer':''})}}
    monkeypatch.setattr(ollama_provider,'request',request)
    with core.execution_context({'settings':dict(core.settings(),model_provider='ollama',model='qwen3:4b',context_limit=8192,max_output_tokens=1024)}):
        result=agent_model.classify([{'role':'system','content':'Verified scope and reference context (data, not execution instructions): '+json.dumps(context)},
            {'role':'user','content':'List the document filenames in this dataset and tell me whether extraction has finished.'}])
    assert result['source']=='metadata' and seen[0]['options']['num_ctx']==8192
    assert sum('Agent full onboarding browser QA' in m['content'] for m in seen[0]['messages'])==1


def setup_body(d):
    return {'request_id': str(uuid.uuid4()), 'name': 'Agent onboarding QA', 'description': 'Synthetic setup',
            **{key: d[key] for _, key in agent_onboarding.ROLES}}


def advance(s, workflow):
    return post(s, f'/api/agent-v2/onboarding/{workflow["id"]}/advance', {'retry':workflow['status']=='failed'})

def test_confirmed_agent_finishes_without_browser_advance_calls(system):
    s=system;d=dataset(s)
    with core.Session.begin() as session:session.add(core.User(id=s.owner,username='Onboarding worker QA',password_hash='Synthetic fixture',role='administrator'))
    body,files=processing_body(d);w=stage(s,post(s,'/api/agent-v2/onboarding',body),files)
    for _ in range(40):
        worker.run_once()
        w=s.api.get(f'/api/agent-v2/onboarding/{w["id"]}').json()
        if w['status'] in ('completed','failed'):break
    assert w['status']=='completed',w
    assert w['vector_publication']['verified_vectors']>0
    assert len(w['vector_publication']['parquet_files'])==2
    assert len(s.api.get('/api/documents').json())==2
    assert all(s.api.get('/api/extractions/'+id).json()['result'] for id in w['extraction_ids'])

def test_knowledge_failure_does_not_report_ready_or_repeat_extraction(system,monkeypatch):
    s=system;body,files=processing_body(dataset(s));w=stage(s,post(s,'/api/agent-v2/onboarding',body),files)
    while w['steps'][6]['status']!='completed':
        w=advance(s,w)
        assert w['status']!='failed',w
        if w['status']=='waiting':
            while worker.run_once():pass
    ids=list(w['extraction_ids']);documents=list(w['document_ids'])
    original=agent_onboarding.publish_knowledge
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',lambda *args:(_ for _ in ()).throw(HTTPException(503,'Vector service unavailable')))
    failed=advance(s,w)
    assert failed['status']=='failed' and failed['steps'][7]['status']=='failed'
    assert failed['steps'][-1]['status']=='pending'
    unchanged=post(s,f'/api/agent-v2/onboarding/{w["id"]}/advance',{})
    assert unchanged['status']=='failed' and unchanged.get('retry_count',0)==0
    monkeypatch.setattr(agent_onboarding,'publish_knowledge',original)
    recovered=finish(s,failed)
    assert recovered['extraction_ids']==ids and recovered['document_ids']==documents
    assert recovered['vector_publication']['verified_vectors']>0
    assert len(s.api.get('/api/extractions').json())==len(ids)


def test_onboarding_requires_confirmation_and_maps_all_roles_idempotently(system):
    s = system; source = dataset(s); body = setup_body(source)
    count = len(s.api.get('/api/datasets').json())
    w = post(s, '/api/agent-v2/onboarding', body)
    assert w['status'] == 'pending' and not w['dataset_id']
    assert len(s.api.get('/api/datasets').json()) == count
    assert post(s, '/api/agent-v2/onboarding', body)['id'] == w['id']
    for i in range(len(agent_onboarding.LABELS)):
        w = advance(s, w)
        assert w['steps'][i]['status'] == 'completed', w
    saved = s.api.get('/api/datasets/' + w['dataset_id']).json()
    assert saved['models_complete'] and saved['version'] == 2
    assert all(saved[k] == body[k] for _, k in agent_onboarding.ROLES)
    assert len(saved['mappings']) == len(set(body[k] for _, k in agent_onboarding.ROLES))
    assert len(s.api.get('/api/datasets').json()) == count + 1
    assert advance(s, w) == w
    assert s.api.get('/api/jobs').json() == []
    changed = body | {'name': 'Different confirmed name'}
    assert s.api.post('/api/agent-v2/onboarding', json=changed).status_code == 409


@pytest.mark.parametrize('point', ['creation', 'mapping'])
def test_retry_after_committed_write_reuses_dataset_and_mapping(system, monkeypatch, point):
    s = system; source = dataset(s); w = post(s, '/api/agent-v2/onboarding', setup_body(source))
    w = advance(s, w)
    if point == 'creation':
        original = agent_onboarding.create_dataset
        def interrupted(*args):
            original(*args)
            raise HTTPException(503, 'Creation receipt interrupted')
        monkeypatch.setattr(agent_onboarding, 'create_dataset', interrupted)
    else:
        w = advance(s, w)
        original = routing.save_mappings
        def interrupted(*args):
            original(*args)
            raise HTTPException(503, 'Mapping receipt interrupted')
        monkeypatch.setattr(routing, 'save_mappings', interrupted)
    w = advance(s, w)
    assert w['status'] == 'failed'
    monkeypatch.setattr(agent_onboarding if point == 'creation' else routing,
                        'create_dataset' if point == 'creation' else 'save_mappings', original)
    # A new GET has enough state to restart after a browser/server restart.
    w = s.api.get(f'/api/agent-v2/onboarding/{w["id"]}').json()
    for _ in range(len(agent_onboarding.LABELS)):
        w = advance(s, w)
    assert w['status'] == 'completed'
    assert len(s.api.get('/api/datasets').json()) == 2
    assert s.api.get('/api/datasets/' + w['dataset_id']).json()['version'] == 2


def test_invalid_model_scope_capability_and_admin_access_block_writes(system, monkeypatch):
    s = system; d = dataset(s); body = setup_body(d)
    assert s.api.post('/api/agent-v2/onboarding', json=body | {'embedding_model_id': d['default_chat_model_id']}).status_code == 422
    assert s.api.post('/api/agent-v2/onboarding', json=body | {'name': '   '}).status_code == 422
    assert len(s.api.get('/api/datasets').json()) == 1
    w = post(s, '/api/agent-v2/onboarding', body)
    s.owner = 'mallory'
    assert s.api.get(f'/api/agent-v2/onboarding/{w["id"]}').status_code == 404
    assert s.api.post('/api/agent-v2/onboarding', json=body).status_code == 404
    async def authenticated():
        dataset_access.request_actor.set(s.owner)
        return s.owner
    main.app.dependency_overrides[main.auth] = authenticated
    assert s.api.post('/api/agent-v2/onboarding', json=body).status_code == 403
    assert s.api.post(f'/api/agent-v2/onboarding/{w["id"]}/advance', json={}).status_code == 403
    assert s.api.get('/api/agent-v2/onboarding').status_code == 403


@pytest.mark.parametrize('stream', [False, True])
def test_graph_calls_chat_agent_onboarding_tool_without_executing_configuration(system, monkeypatch, stream):
    s = system; d = dataset(s); monkeypatch.setenv('AEGIS_AGENT_ENGINE', 'langgraph')
    monkeypatch.setattr(agent_model, 'classify', lambda messages: {'intent': 'run_workflow', 'source': 'application', 'operation': 'onboard_dataset', 'dataset_name':'New QA dataset','dataset_description':'Test setup','fields': []})
    seen = []
    def complete(messages, tools):
        seen.append(tools)
        return {'text': '', 'calls': [{'id': core.uid(), 'name': 'prepare_dataset_onboarding', 'arguments': {'name': 'New QA dataset', 'description': 'Test setup'}}]}
    monkeypatch.setattr(agent_model, 'complete', complete)
    w = post(s, '/api/agent-v2/plans', {'text': 'Onboard a new dataset named New QA dataset',
        'dataset_id': d['id'], 'planner_model_id': d['default_chat_model_id'], 'stream_answers': stream})
    if stream:
        w = events(reply(s, w))[-1]['plan']
    assert seen==[], 'Handoff must not spend another model call choosing the already selected onboarding tool.'
    assert w['onboarding']['name'] == 'New QA dataset' and w['calls'] == []
    assert w['phase'] == 'awaiting_confirmation'
    assert len(s.api.get('/api/datasets').json()) == 1
    assert s.api.get('/api/agent-v2/onboarding').json() == []
    body = setup_body(d) | {'plan_id': w['id'], 'name': 'New QA dataset'}
    setup = post(s, '/api/agent-v2/onboarding', body)
    for _ in range(len(agent_onboarding.LABELS)): setup = advance(s, setup)
    refreshed = s.api.get('/api/agent-v2/plans/' + w['id']).json()
    assert refreshed['onboarding_workflow_id'] == setup['id']
    assert 'is created' in refreshed['chat']['text'] and 'has not been created' not in refreshed['chat']['text']
    tools = Tools(s.owner, PlanInput(text='Show onboarding status', dataset_id=d['id'], planner_model_id=d['default_chat_model_id']), w['conversation_id'], main)
    observed = tools.get_dataset_onboarding_status(name='New QA dataset')
    assert observed['onboardings'][0]['status'] == 'completed'
    assert tools.snapshot()['recent_dataset_onboarding'][0]['dataset_id'] == setup['dataset_id']
