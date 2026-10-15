"""The planner is mocked here; tools execute the real API-to-worker path."""
import copy
import json
import io
import zipfile
import time
import pytest
from ags_app import core, main, providers, worker, agent_workspace as agent
from test_dataset_models import system, dataset, template, upload, post

def proposal(tools=('upload', 'extract'), **values):
    return {'explanation': 'I will connect the requested document tools.', 'answer_mode':'documents', 'dataset_name': '', 'document_names': [], 'template_name': '', 'calls': [{'tool': tool, 'title': tool.title()} for tool in tools], **values}

def planner(monkeypatch, value):
    monkeypatch.setattr(providers, 'plan', lambda *args: copy.deepcopy(value))


def test_capability_question_returns_reply_without_document_actions(system, monkeypatch):
    s = system
    d = dataset(s)
    reply = providers.AGENT_CAPABILITIES
    monkeypatch.setattr(providers,'plan',lambda *args:pytest.fail('Capabilities must come from the supported app features.'))
    p = plan(s, d, text='hi what and all u can do')
    assert p['explanation'] == reply
    assert p['calls'] == []
    assert call(s, p, 0).status_code == 404
    assert s.api.get('/api/jobs').json() == []
    assert s.api.get('/api/documents').json() == []

def plan(s, d, **values):
    model = next(m for m in d['models'] if 'chat' in m['capabilities'])
    return post(s, '/api/agent-v2/plans', {'text': 'Please ingest this file and find the requested fields.', 'planner_model_id': model['id'], 'dataset_id': d['id'], **values})

def call(s, p, index, **values):
    return s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/{index}', json={'confirmed': True, **values})

def send_files(s, p, files=None):
    return s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload', data={'dataset_id': p['dataset_id'], 'confirmed': 'true'}, files=files or [('files', ('general.txt', b'Invoice total 42. Alice is the owner.', 'text/plain'))])

def test_chain_waits_for_indexing_consumes_upload_refs_and_is_idempotent(system, monkeypatch):
    s = system; d = dataset(s); t = template(s); planner(monkeypatch, proposal())
    old = upload(s, d)['documents'][0]
    p = plan(s, d, document_ids=[old['id']], template_id=t['id'])
    assert call(s, p, 1).status_code == 409
    accepted = send_files(s, p); assert accepted.status_code == 200, accepted.text
    refs = accepted.json()['calls'][0]['uploaded_document_ids']; assert refs != [old['id']]
    assert call(s, p, 1).status_code == 409
    assert send_files(s, p).json()['calls'][0]['uploaded_document_ids'] == refs
    assert worker.run_once()
    result = call(s, p, 1, document_ids=[old['id']]); assert result.status_code == 200, result.text
    ex = result.json()['calls'][1]['result']['extraction_id']
    assert main.extraction(ex, s.owner)['document_ids'] == refs
    assert call(s, p, 1).json()['calls'][1]['result']['extraction_id'] == ex
    assert worker.run_once()
    done = s.api.get('/api/agent-v2/plans/' + p['id']).json()
    assert all(c['status'] == 'completed' for c in done['calls'])
    assert done['calls'][1]['result']['data'] is not None
    assert 'event: workflow' in s.api.get('/api/agent-v2/plans/' + p['id'] + '/events').text

def test_reextract_creates_new_result_preserves_previous_review(system, monkeypatch):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]; t = template(s)
    old = post(s, '/api/extractions', {'dataset_id': d['id'], 'document_ids': [doc['id']], 'template_id': t['id']})
    assert worker.run_once()
    record = main.get_record(old['id'], s.owner, 'extraction'); data = core.store.json(record.ref); data['review_status'] = 'reviewed'; core.store.put_json(record.ref, data)
    before = core.store.get(record.ref)
    planner(monkeypatch, proposal(('reextract',)))
    p = plan(s, d, document_ids=[doc['id']], template_id=t['id'])
    response = call(s, p, 0); assert response.status_code == 200, response.text
    assert response.json()['calls'][0]['result']['extraction_id'] != old['id']
    assert worker.run_once(); assert core.store.get(record.ref) == before

def test_missing_details_and_ambiguous_names_do_not_guess(system, monkeypatch):
    s = system; d = dataset(s); upload(s, d); upload(s, d)
    planner(monkeypatch, proposal(('extract',), document_names=['invoice.txt']))
    p = plan(s, d)
    assert p['document_ids'] == [] and p['clarification']
    assert call(s, p, 0).status_code == 422
    assert not any(j['kind'] == 'extract' for j in s.api.get('/api/jobs').json())

def test_failed_index_stops_following_extraction(system, monkeypatch):
    s = system; d = dataset(s); t = template(s); planner(monkeypatch, proposal())
    p = plan(s, d, template_id=t['id'])
    assert send_files(s, p, [('files', ('bad.docx', b'Not a DOCX file', 'application/octet-stream'))]).status_code == 200
    assert worker.run_once()
    failed = s.api.get('/api/agent-v2/plans/' + p['id']).json()
    assert failed['calls'][0]['status'] == 'failed' and failed['calls'][0]['error']
    assert 'invalid or damaged' in failed['calls'][0]['error']
    assert call(s, p, 1).status_code == 409

def test_batch_prevalidation_creates_no_partial_documents(system, monkeypatch):
    s = system; d = dataset(s); planner(monkeypatch, proposal(('upload',))); p = plan(s, d)
    files = [('files', ('okay.txt', b'Hello', 'text/plain')), ('files', ('bad.exe', b'Disallowed', 'application/octet-stream'))]
    assert send_files(s, p, files).status_code == 422
    assert s.api.get('/api/documents').json() == []

def test_plan_and_tools_are_owned_and_cross_dataset_rejected(system, monkeypatch):
    s = system; d = dataset(s); other = dataset(s, 'Other'); doc = upload(s, other)['documents'][0]; t = template(s)
    planner(monkeypatch, proposal(('extract',))); p = plan(s, d, template_id=t['id'])
    assert call(s, p, 0, document_ids=[doc['id']]).status_code == 400
    s.owner = 'bob'
    for path in ('/api/agent-v2/plans/' + p['id'], '/api/agent-v2/plans/' + p['id'] + '/events'):
        assert s.api.get(path).status_code == 404
    assert call(s, p, 0).status_code == 404

def test_unknown_tools_and_out_of_scope_requests_cannot_mutate(system, monkeypatch):
    s = system; d = dataset(s); planner(monkeypatch, proposal(('delete_everything',)))
    model = next(m for m in d['models'] if 'chat' in m['capabilities'])
    assert s.api.post('/api/agent-v2/plans', json={'text': 'Delete everything', 'planner_model_id': model['id'], 'dataset_id': d['id']}).status_code == 502
    planner(monkeypatch, proposal((), explanation='This version supports upload, extraction, and re-extraction.'))
    assert plan(s, d)['calls'] == []
    assert s.api.get('/api/jobs').json() == []

def test_external_planning_is_allowed_but_only_proposes_processing(system, monkeypatch):
    s = system; d = dataset(s); seen = []
    original=agent.chat_snapshot
    def snapshot(*args):
        value=original(*args);value['settings']={**value['settings'],'model_provider':'openai'};return value
    monkeypatch.setattr(agent,'chat_snapshot',snapshot)
    monkeypatch.setattr(providers, 'plan', lambda *args: seen.append(args) or proposal(('upload',)))
    model = next(m for m in d['models'] if 'chat' in m['capabilities'])
    r = s.api.post('/api/agent-v2/plans', json={'text': 'Upload a document', 'planner_model_id': model['id'], 'dataset_id': d['id']})
    assert r.status_code == 200 and len(seen)==1
    assert r.json()['calls'][0]['status']=='pending'
    assert s.api.get('/api/jobs').json()==[]

def test_expired_plan_does_not_start_a_tool(system, monkeypatch):
    s = system; d = dataset(s); planner(monkeypatch, proposal(('upload',))); p = plan(s, d)
    record = main.get_record(p['id'], s.owner, 'agent_plan'); value = core.store.json(record.ref); value['created_at'] = time.time() - 3700; core.store.put_json(record.ref, value)
    assert send_files(s, p).status_code == 409
    assert s.api.get('/api/documents').json() == []

def test_every_tool_requires_confirmation(system, monkeypatch):
    s = system; d = dataset(s); planner(monkeypatch, proposal(('upload',))); p = plan(s, d)
    r = s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload', data={'dataset_id': d['id']}, files={'files': ('x.txt', b'Hello', 'text/plain')})
    assert r.status_code == 409 and s.api.get('/api/documents').json() == []
    doc = upload(s, d)['documents'][0]; t = template(s)
    for tool in ('extract', 'reextract'):
        planner(monkeypatch, proposal((tool,))); p = plan(s, d, document_ids=[doc['id']], template_id=t['id'])
        assert call(s, p, 0, confirmed=False).status_code == 409
    assert not any(j['kind'] == 'extract' for j in s.api.get('/api/jobs').json())

def test_planner_sees_attached_names_and_scoped_catalog_but_no_document_content(system, monkeypatch):
    s = system; d = dataset(s); other = dataset(s, 'Other'); upload(s, other); seen = []
    def capture(instruction, text, schema):
        seen.append((instruction, json.loads(text))); return proposal(('upload', 'extract'))
    monkeypatch.setattr(providers, 'plan', capture)
    p = plan(s, d, attached_filenames=['general.txt'])
    assert [c['tool'] for c in p['calls']] == ['upload', 'extract']
    assert seen[0][1]['attached_filenames'] == ['general.txt']
    assert seen[0][1]['catalog']['documents'] == []
    assert 'BOTH upload and extract' in seen[0][0]
    assert 'Alice is the owner' not in json.dumps(seen)

def test_missing_upload_confirm_is_recoverable_but_uncertain_submission_is_not_retried(system, monkeypatch):
    s = system; d = dataset(s); planner(monkeypatch, proposal(('upload',))); p = plan(s, d)
    count = []
    async def uncertain(*args, **kwargs): count.append(1); raise RuntimeError('network failure')
    monkeypatch.setattr(main, 'upload', uncertain)
    assert send_files(s, p).status_code == 502
    assert send_files(s, p).status_code == 409
    assert len(count) == 1

def test_native_planner_uses_orchestration_instruction_and_validates_output(system, monkeypatch):
    seen = []
    def invoke(*args): seen.append(args); return proposal()
    monkeypatch.setattr(providers, 'ollama_call', invoke)
    with core.execution_context({'settings': core.settings() | {'model_provider': 'ollama', 'model': 'qwen3:4b'}}):
        result = providers.plan(agent.PLANNER_INSTRUCTION, 'Upload then extract.', agent.planner_schema())
    assert [c['tool'] for c in result['calls']] == ['upload', 'extract']
    assert seen[0][0] == 'extract' and seen[0][-1] == agent.PLANNER_INSTRUCTION
    monkeypatch.setattr(providers, 'ollama_call', lambda *args: proposal(('delete',)))
    with core.execution_context({'settings': core.settings() | {'model_provider': 'ollama'}}):
        with pytest.raises(providers.ProviderError): providers.plan(agent.PLANNER_INSTRUCTION, 'Delete.', agent.planner_schema())

def test_invalid_docx_returns_a_readable_format_error():
    with pytest.raises(ValueError, match='invalid or damaged'):
        worker.parse_document('damaged.docx', b'Not a ZIP file')
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as archive: archive.writestr('example.txt','A ZIP is not a DOCX.')
    with pytest.raises(ValueError, match='not a valid DOCX'):
        worker.parse_document('archive.docx',raw.getvalue())

def test_valid_docx_still_parses_after_error_classification():
    from docx import Document
    document=Document();document.add_paragraph('General document text.');raw=io.BytesIO();document.save(raw)
    assert worker.parse_document('general.docx',raw.getvalue())[0]['text']=='General document text.'

def test_restart_rebuilds_all_originals_then_extracts_again_preserving_results(system, monkeypatch):
    s=system;d=dataset(s);t=template(s);planner(monkeypatch,proposal())
    p=plan(s,d,template_id=t['id'])
    assert send_files(s,p).status_code==200
    assert worker.run_once()
    accepted=call(s,p,1);assert accepted.status_code==200,accepted.text
    original=accepted.json()['calls'][1]['result']['extraction_id']
    assert worker.run_once()
    saved=core.store.get(main.get_record(original,s.owner,'extraction').ref)
    # A completed first result and a later failed call must both restart.
    record=main.get_record(p['id'],s.owner,'agent_plan');data=core.store.json(record.ref)
    data['calls'].append({'tool':'extract','title':'Second extraction','status':'failed','error':'Model unavailable'})
    core.store.put_json(record.ref,data)
    response=s.api.post('/api/agent-v2/plans/'+p['id']+'/restart',json={'confirmed':True})
    assert response.status_code==200,response.text
    restarted=response.json();first=restarted['calls'][0]
    assert first['status']=='waiting' and all(c['status']=='pending' for c in restarted['calls'][1:])
    assert first['uploaded_document_ids']==data['calls'][0]['uploaded_document_ids']
    assert first['job_ids']!=data['calls'][0]['job_ids']
    assert first['jobs'][0]['workflow']['stages']['extract']['status']=='queued'
    assert first['jobs'][0]['workflow']['stages']['index']['status']=='blocked'
    assert s.api.post('/api/agent-v2/plans/'+p['id']+'/restart',json={'confirmed':True}).status_code==409
    assert worker.run_once()
    for _ in range(4):
        s.api.get('/api/agent-v2/plans/'+p['id'])
        worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert all(c['status']=='completed' for c in done['calls']),done
    assert done['calls'][1]['result']['extraction_id']!=original
    assert core.store.get(main.get_record(original,s.owner,'extraction').ref)==saved
    assert len(s.api.get('/api/documents').json())==1
    assert done['restart_attempt']==1 and len(done['previous_attempts'])==1


def test_restart_extract_only_rebuilds_stale_knowledge_before_extraction(system, monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s);planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d,document_ids=[doc['id']],template_id=t['id'])
    record=main.get_record(p['id'],s.owner,'agent_plan');data=core.store.json(record.ref)
    data['calls'][0].update(error='Reindex required',status='pending');core.store.put_json(record.ref,data)
    assert s.api.post('/api/agent-v2/plans/'+p['id']+'/restart',json={}).status_code==409
    response=s.api.post('/api/agent-v2/plans/'+p['id']+'/restart',json={'confirmed':True})
    assert response.status_code==200,response.text
    assert [c['tool'] for c in response.json()['calls']]==['upload','extract']
    assert worker.run_once();assert worker.run_once()
    assert all(c['status']=='completed' for c in s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'])


def test_restart_rejects_uncertain_or_active_work_and_foreign_scope(system, monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s);planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d,document_ids=[doc['id']],template_id=t['id'])
    record=main.get_record(p['id'],s.owner,'agent_plan');data=core.store.json(record.ref)
    data['calls'][0].update(error='Submission status is uncertain',status='failed',submission_uncertain=True);core.store.put_json(record.ref,data)
    endpoint='/api/agent-v2/plans/'+p['id']+'/restart'
    assert s.api.post(endpoint,json={'confirmed':True}).status_code==409
    data['calls'][0].pop('submission_uncertain');data['calls'][0]['error']='Model failed';core.store.put_json(record.ref,data)
    s.owner='mallory'
    assert s.api.post(endpoint,json={'confirmed':True}).status_code in (403,404)
    s.owner='alice'
    post(s,'/api/documents/'+doc['id']+'/reindex',{})
    assert s.api.post(endpoint,json={'confirmed':True}).status_code==409


def stale_index(doc):
    path='documents/'+doc['id']+'/index.json'
    index=core.store.json(path);index['fingerprint']='old-embedding-pipeline';core.store.put_json(path,index)


def test_confirmed_extraction_reindexes_only_stale_documents_keeps_complete_scope(system,monkeypatch):
    s=system;d=dataset(s);stale=upload(s,d)['documents'][0];ready=upload(s,d)['documents'][0];t=template(s)
    original=core.store.get(main.get_record(stale['id'],s.owner,'document').ref)
    before=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[ready['id']],'template_id':t['id']})
    assert worker.run_once();saved=core.store.get(main.get_record(before['id'],s.owner,'extraction').ref)
    stale_index(stale);planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d,document_ids=[stale['id'],ready['id']],template_id=t['id'])
    endpoint=f'/api/agent-v2/plans/{p["id"]}/calls/0'
    assert s.api.post(endpoint,json={'extraction_mode':'independent'}).status_code==409
    response=call(s,p,0,extraction_mode='independent',display_name='Selected profiles')
    assert response.status_code==200,response.text
    accepted=response.json();first=accepted['calls'][0]
    assert first['title']=='Reindex selected documents' and first['status']=='waiting'
    assert [j['target_id'] for j in first['jobs']]==[stale['id']]
    assert first['uploaded_document_ids']==[stale['id'],ready['id']]
    assert accepted['calls'][1]['status']=='pending'
    assert s.api.post(endpoint,json={'confirmed':True}).json()['calls'][0]['job_ids']==first['job_ids']
    assert worker.run_once()
    resumed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert resumed['calls'][0]['status']=='completed'
    assert {tuple(e['document_ids']) for e in resumed['calls'][1]['result']['extractions']}=={(stale['id'],),(ready['id'],)}
    assert worker.run_once();assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert all(c['status']=='completed' for c in done['calls'])
    assert core.store.get(main.get_record(stale['id'],s.owner,'document').ref)==original
    assert core.store.get(main.get_record(before['id'],s.owner,'extraction').ref)==saved
    assert s.api.get('/api/documents/'+stale['id']).json()['requires_reindex'] is False


def test_reindex_prerequisite_failure_stops_extraction_and_allows_full_restart(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s);stale_index(doc)
    planner(monkeypatch,proposal(('extract',)));p=plan(s,d,document_ids=[doc['id']],template_id=t['id'])
    response=call(s,p,0);assert response.status_code==200,response.text
    original_embed=providers.embed
    def fail(*args,**kwargs):raise providers.ProviderError('Embedding service unavailable')
    monkeypatch.setattr(providers,'embed',fail);assert worker.run_once()
    failed=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert failed['calls'][0]['status']=='failed' and failed['calls'][1]['status']=='pending'
    assert s.api.get('/api/extractions').json()==[]
    monkeypatch.setattr(providers,'embed',original_embed)
    restart=s.api.post('/api/agent-v2/plans/'+p['id']+'/restart',json={'confirmed':True})
    assert restart.status_code==200,restart.text
    assert worker.run_once();assert worker.run_once()
    assert all(c['status']=='completed' for c in s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'])


def test_stale_indexes_validate_template_and_external_consent_before_queueing(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s);stale_index(doc)
    planner(monkeypatch,proposal(('extract',)));p=plan(s,d,document_ids=[doc['id']],template_id=t['id'])
    jobs=len(s.api.get('/api/jobs').json())
    other=dataset(s,'Other');record=main.get_record(t['id'],s.owner,'template')
    with core.Session.begin() as session:session.get(core.Record,record.id).parent_id=other['id']
    assert call(s,p,0).status_code==400
    with core.Session.begin() as session:session.get(core.Record,record.id).parent_id=''
    def consent(*args,**kwargs):raise main.HTTPException(400,'External data consent required')
    monkeypatch.setattr(main,'external_check',consent)
    assert call(s,p,0).status_code==400
    assert len(s.api.get('/api/jobs').json())==jobs
    assert s.api.get('/api/extractions').json()==[]
