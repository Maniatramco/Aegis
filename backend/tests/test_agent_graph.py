"""Real LangGraph/storage/API with scripted model calls; intelligence is tested
separately against the actual local Ollama model in the container smoke suite.
"""
import json
import pytest
from app import core, main, worker, agent_model, agent_graph
from app.agent_tools import Tools
from app.agent_checkpoints import ExternalCheckpointSaver
from test_dataset_models import system, dataset, template, upload, post
from test_agent_workspace import plan, send_files, call
from test_agent_chat import reply
from test_chat_stream import events


def sequence(monkeypatch, *outputs):
    values = iter(outputs); seen = []
    def complete(messages, tools):
        seen.append(messages)
        return next(values)
    monkeypatch.setattr(agent_model, 'complete', complete)
    monkeypatch.setattr(agent_model, 'classify', lambda messages:{'source':'auto','fields':[]})
    monkeypatch.setenv('AEGIS_AGENT_ENGINE', 'langgraph')
    return seen


def tool(name, **arguments):
    return {'text': '', 'calls': [{'id': core.uid(), 'name': name, 'arguments': arguments}]}


def test_saved_results_drive_conditional_summary_and_review_without_rerun(system, monkeypatch):
    s=system; d=dataset(s); doc=upload(s,d)['documents'][0]; t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once()
    before=s.api.get('/api/jobs').json()
    seen=sequence(monkeypatch,tool('find_extractions'),tool('read_extraction_results',extraction_id=ex['id']),
        {'text': 'The saved extracted owner is Alice. Extraction ID: '+ex['id'], 'calls':[]})
    p=plan(s,d,text='If this was already processed, summarize the saved fields.',document_ids=[doc['id']])
    assert p['runtime']=='langgraph' and p['calls']==[] and p['model_calls']==4
    answer=events(reply(s,p))[-1]['message']
    assert answer['status']=='completed' and answer['review_actions'][0]['extraction_id']==ex['id']
    result=json.loads(next(m['content'] for m in seen[-1] if m.get('tool_name')=='read_extraction_results'))
    assert result['records'][0]['fields']==s.api.get('/api/extractions/'+ex['id']).json()['result'] and result['version']==1
    assert s.api.get('/api/jobs').json()==before
    record=main.get_record(p['conversation_id'],s.owner,'conversation')
    assert 'saved fields' not in record.name and core.store.json(record.ref)['checkpoint_ref'].startswith('agent-state/')
    saver=ExternalCheckpointSaver(record.id)
    checkpoint=saver.get_tuple({'configurable':{'thread_id':record.id}})
    assert checkpoint.checkpoint['channel_values']['phase']=='answered'
    # A newly constructed saver reads external state, not process memory.
    assert list(ExternalCheckpointSaver(record.id).list({'configurable':{'thread_id':record.id}},limit=2))


def test_upload_extract_proposal_uses_confirmed_chain_and_fresh_followup_reads(system,monkeypatch):
    s=system; d=dataset(s); t=template(s)
    sequence(monkeypatch,tool('prepare_workflow',operation='extract'))
    p=plan(s,d,text='Find the owner in the attached file and save the structured result.',attached_filenames=['general.txt'],template_id=t['id'])
    assert [c['tool'] for c in p['calls']]==['upload','extract']
    assert s.api.get('/api/jobs').json()==[]
    accepted=send_files(s,p); assert accepted.status_code==200,accepted.text
    assert worker.run_once()
    result=call(s,p,1);assert result.status_code==200,result.text
    assert worker.run_once()
    ex=result.json()['calls'][1]['result']['extraction_id']
    seen=sequence(monkeypatch,tool('get_workflow_status'),tool('read_extraction_results',extraction_id=ex),{'text':'Alice was extracted.','calls':[]})
    follow=plan(s,d,text='What did that produce?',conversation_id=p['conversation_id'])
    assert follow['conversation_id']==p['conversation_id']
    assert not any('Find the owner in the attached file' in m.get('content','') for batch in seen for m in batch)
    observed=json.loads(next(m['content'] for m in seen[-1] if m.get('tool_name')=='read_extraction_results'))
    assert observed['records'][0]['fields']==s.api.get('/api/extractions/'+ex).json()['result']
    assert follow['calls']==[]


def test_short_summary_reads_completed_work_after_stale_proposal(system,monkeypatch):
    s=system;d=dataset(s);t=template(s)
    sequence(monkeypatch,tool('prepare_workflow',operation='extract'))
    p=plan(s,d,text='Extract the attached file.',attached_filenames=['general.txt'],template_id=t['id'])
    assert 'not run yet' in p['explanation']
    assert send_files(s,p).status_code==200
    assert worker.run_once()
    accepted=call(s,p,1);assert accepted.status_code==200
    assert worker.run_once()
    ex=accepted.json()['calls'][1]['result']['extraction_id']
    saved=s.api.get('/api/extractions/'+ex).json()
    assert saved['status']=='ready',saved.get('error')
    from app import dataset_models as routing
    routing.create('extraction',s.owner,'Unrelated earlier result',
        {'document_ids':saved['document_ids'],'result':{'owner':'Other saved owner'}},parent=d['id'])
    before=s.api.get('/api/jobs').json()
    contexts=[]
    def classify(messages):
        contexts.append(json.loads(messages[0]['content'].split(': ',1)[1]))
        return {'source':'results','fields':[],'answer_kind':'summary','filters':[],'result_scope':'latest_workflow'}
    monkeypatch.setattr(agent_model,'classify',classify)
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:pytest.fail('Saved summary must use actual results.'))
    follow=plan(s,d,text='can you summarize',conversation_id=p['conversation_id'])
    assert saved['result']['owner'] in follow['explanation'] and 'completed, version 1' in follow['explanation']
    assert 'Other saved owner' not in follow['explanation']
    assert ex in follow['explanation'] and 'not run yet' not in follow['explanation']
    assert follow['calls']==[] and s.api.get('/api/jobs').json()==before
    assert 'previous_user_request' not in contexts[0] and contexts[0]['chat_history_supplied'] is False
    assert all(c['status']=='completed' for c in contexts[0]['latest_workflow']['calls'])
    answer=events(reply(s,follow))[-1]['message']
    assert answer['review_actions'][0]['extraction_id']==ex
    assert answer['answer_workflow']['status']=='completed'
    labels=[step['label'] for step in answer['answer_workflow']['steps']]
    assert 'Checking saved extractions' in labels and 'Reading saved fields' in labels
    assert 'Generating response' not in labels  # No model generation ran for this saved summary.
    again=plan(s,d,text='summarize again',conversation_id=p['conversation_id'])
    assert saved['result']['owner'] in again['explanation'] and ex in again['explanation']
    assert contexts[-1]['latest_workflow']['id']==p['id']
    assert again['calls']==[] and s.api.get('/api/jobs').json()==before


def test_summary_of_unconfirmed_workflow_does_not_claim_completion_or_run(system,monkeypatch):
    s=system;d=dataset(s);t=template(s)
    sequence(monkeypatch,tool('prepare_workflow',operation='extract'))
    p=plan(s,d,text='Extract this attachment.',attached_filenames=['general.txt'],template_id=t['id'])
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'results','answer_kind':'summary','result_scope':'latest_workflow'})
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:pytest.fail('Status is verified without inference.'))
    follow=plan(s,d,text='Summarize that.',conversation_id=p['conversation_id'])
    assert 'no saved extraction result' in follow['explanation'] and 'extract: pending' in follow['explanation']
    assert follow['calls']==[] and s.api.get('/api/jobs').json()==[]


def test_dataset_and_owner_isolation_for_results_and_conversations(system,monkeypatch):
    s=system; d=dataset(s); other=dataset(s,'Other'); doc=upload(s,other)['documents'][0]; t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':other['id'],'document_ids':[doc['id']],'template_id':t['id']});assert worker.run_once()
    seen=sequence(monkeypatch,tool('read_extraction_results',extraction_id=ex['id']),{'text':'That result is outside this dataset.','calls':[]})
    p=plan(s,d,text='Read this result')
    observation=json.loads(next(m['content'] for m in seen[-1] if m.get('role')=='tool'))
    assert observation['status_code']==404 and 'Alice' not in json.dumps(observation)
    model=next(m for m in other['models'] if 'chat' in m['capabilities'])
    assert s.api.post('/api/agent-v2/plans',json={'text':'Continue','planner_model_id':model['id'],'dataset_id':other['id'],'conversation_id':p['conversation_id']}).status_code==409
    s.owner='bob'
    assert s.api.get('/api/agent-v2/plans/'+p['id']).status_code==404


def test_invalid_or_unknown_tools_are_observations_never_actions(system,monkeypatch):
    s=system;d=dataset(s)
    seen=sequence(monkeypatch,tool('delete_everything'),tool('prepare_workflow',operation='erase'),{'text':'No files were changed.','calls':[]})
    p=plan(s,d,text='Help with this')
    errors=[json.loads(m['content']) for m in seen[-1] if m.get('role')=='tool']
    assert len(errors)==2 and all(e['executed'] is False for e in errors)
    assert p['calls']==[] and s.api.get('/api/jobs').json()==[]


def test_prompt_receipt_is_grounded_and_stays_in_external_conversation(system,monkeypatch):
    s=system;d=dataset(s)
    t=post(s,'/api/templates',{'name':'sample_resume.json','source_filename':'sample_resume.json','dataset_id':d['id'],'schema':{'type':'object','properties':{},'additionalProperties':False}})
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda *args:pytest.fail('A saved prompt receipt requires no model.'))
    p=plan(s,d,text='update this',template_id=t['id'],submitted_prompt_id=t['id'])
    saved=s.api.get('/api/conversations/'+p['conversation_id']).json()
    assert 'sample_resume.json' in saved['messages'][-1]['text']
    assert p['model_calls']==0
    assert p['calls']==[]


def test_actual_document_search_is_scoped_and_citations_persist(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];other=dataset(s,'Other');upload(s,other)
    seen=sequence(monkeypatch,tool('search_documents',query='Who is the owner?'),{'text':'Alice is the owner. [1]','calls':[]})
    p=plan(s,d,text='Who is named here?',document_ids=[doc['id']])
    answer=events(reply(s,p))[-1]['message']
    assert len(answer['citations'])==1 and answer['citations'][0]['document_id']==doc['id']
    assert json.loads(seen[-1][-1]['content'])['scoped_document_count']==1


def test_tool_step_limit_preserves_state_and_does_not_mutate(system,monkeypatch):
    s=system;d=dataset(s)
    sequence(monkeypatch,*[tool('list_documents') for _ in range(8)])
    p=plan(s,d,text='Inspect everything')
    assert p['phase']=='limited' and p['calls']==[]
    assert 'tool-step limit' in p['explanation'] and s.api.get('/api/jobs').json()==[]


def test_all_merged_profiles_are_paged_and_document_filter_cannot_leak(system):
    from app import dataset_models as routing
    from app.agent_workspace import PlanInput
    s=system;d=dataset(s);docs=[upload(s,d)['documents'][0] for _ in range(3)]
    ids=[doc['id'] for doc in docs]
    ex=routing.create('extraction',s.owner,'Merged profiles',{'document_ids':ids,'result':{'records':[
        {'source_filename':str(i)+'.pdf','fields':{'name':name,'large':'x'*8000}} for i,name in enumerate(['Arjun','Meera','Nikhil'])
    ]}},parent=d['id'])
    with core.Session.begin() as db:db.get(core.Record,ex.id).status='ready'
    model=next(m['id'] for m in d['models'] if 'chat' in m['capabilities'])
    body=PlanInput(text='summarize',planner_model_id=model,dataset_id=d['id'])
    tools=Tools(s.owner,body,'test-conversation',main)
    assert 'too large' in tools.read_extraction_results(ex.id)['error']
    first=tools.read_extraction_results(ex.id,fields=['name']);second=tools.read_extraction_results(ex.id,offset=first['next_offset'],fields=['name'])
    assert [r['fields']['name'] for r in first['records']+second['records']]==['Arjun','Meera','Nikhil']
    assert second['next_offset'] is None and first['total_records']==3
    assert len(tools.review_actions)==1
    body.document_ids=[ids[0]]
    assert tools.find_extractions()['total']==0
    from fastapi import HTTPException
    with pytest.raises(HTTPException):tools.read_extraction_results(ex.id)


def test_recovery_is_only_a_scoped_confirmation_proposal(system,monkeypatch):
    from app import dataset_models as routing
    from app.agent_workspace import PlanInput
    s=system;d=dataset(s)
    workflow=routing.create('agent_plan',s.owner,'Failed workflow',{'conversation_id':'this-thread','calls':[
        {'tool':'extract','status':'failed','error':'Model timed out.'}]},parent=d['id'])
    body=PlanInput(text='retry',planner_model_id=next(m['id'] for m in d['models'] if 'chat' in m['capabilities']),dataset_id=d['id'])
    tools=Tools(s.owner,body,'this-thread',main)
    proposal=tools.prepare_recovery(workflow.id,'retry')
    assert proposal['executed'] is False and proposal['confirmation_required']
    assert core.store.json(workflow.ref)['calls'][0]['status']=='failed'
    assert tools.recovery_actions[0]['workflow_id']==workflow.id
    from fastapi import HTTPException
    with pytest.raises(HTTPException):Tools(s.owner,body,'another-thread',main).prepare_recovery(workflow.id,'retry')


def test_qwen_adapter_uses_validated_json_decisions_and_rejects_invalid_output(system,monkeypatch):
    from app import ollama_provider, providers
    from app.agent_tools import definitions
    seen=[]
    def request(path,body,timeout):
        seen.append(body)
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'answer':'','tool_calls':[{'name':'find_extractions','arguments':{}}]})}}
    monkeypatch.setattr(ollama_provider,'request',request)
    monkeypatch.setattr(ollama_provider,'generation_options',lambda messages,tokens:{'num_predict':tokens})
    cfg=core.settings()|{'model':'qwen3:4b'}
    result=agent_model.schema_decision([{'role':'system','content':'Use tools.'},{'role':'user','content':'summarize saved results'}],definitions(),cfg)
    assert result['calls'][0]['name']=='find_extractions' and seen[0]['think'] is False and 'format' in seen[0] and 'tools' not in seen[0]
    monkeypatch.setattr(ollama_provider,'request',lambda *args:{'done':True,'message':{'content':'{"answer":"wrong"}'}})
    with pytest.raises(providers.ProviderError,match='invalid tool decision'):agent_model.schema_decision([{'role':'system','content':'Use tools.'}],definitions(),cfg)


def test_semantic_result_source_reads_saved_fields_before_answering(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']});assert worker.run_once()
    seen=sequence(monkeypatch,{'text':'The saved result is ready.','calls':[]})
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'results','fields':[]})
    p=plan(s,d,text='Tell me what was already obtained.')
    observations=[m for m in seen[0] if m.get('role')=='tool']
    assert [o['tool_name'] for o in observations]==['read_extraction_results']
    message=events(reply(s,p))[-1]['message']
    assert [o['tool'] for o in message['tool_trace']][:2]==['find_extractions','read_extraction_results']
    assert json.loads(observations[-1]['content'])['records'][0]['fields']==s.api.get('/api/extractions/'+ex['id']).json()['result']
    answer=message
    assert answer['review_actions'][0]['extraction_id']==ex['id']
    assert ex['id'] in answer['text'] and 'saved extraction values' in answer['text']


def test_prompt_source_acknowledges_verified_receipt_without_model_rewriting_it(system,monkeypatch):
    s=system;d=dataset(s)
    t=post(s,'/api/templates',{'name':'sample_resume.json','source_filename':'sample_resume.json','dataset_id':d['id'],'schema':{'type':'object','properties':{},'additionalProperties':False}})
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'prompt','fields':[]})
    monkeypatch.setattr(agent_model,'complete',lambda *args:pytest.fail('Do not let a model contradict a completed save event.'))
    p=plan(s,d,text='update this',template_id=t['id'],submitted_prompt_id=t['id'])
    assert 'Saved prompt "sample_resume.json"' in p['explanation'] and 'version 1' in p['explanation'] and not p['calls']


@pytest.mark.parametrize('source',['action','auto'])
def test_prompt_only_upload_stops_on_completed_save_receipt(system,monkeypatch,source):
    s=system;d=dataset(s)
    t=post(s,'/api/templates',{'name':'prompt-only.json','source_filename':'prompt-only.json','dataset_id':d['id'],
        'schema':{'type':'object','properties':{},'additionalProperties':False}})
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':source,'operation':'upload','fields':[]})
    decisions=[]
    def complete(*args):
        decisions.append(True)
        assert len(decisions)==1,'A completed prompt save must not loop back into the model.'
        return tool('prepare_workflow',operation='upload',template_id=t['id'])
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='can you upload it',template_id=t['id'],submitted_prompt_id=t['id'])
    assert p['phase']=='answered' and p['calls']==[] and p['model_calls']<=2
    assert 'Saved prompt "prompt-only.json"' in p['explanation'] and 'version 1' in p['explanation']
    assert len(decisions)==0 and p['model_calls']==0
    assert not s.api.get('/api/jobs').json() and not s.api.get('/api/documents').json()


def test_saved_prompt_does_not_hide_attached_document_extraction(system,monkeypatch):
    s=system;d=dataset(s)
    t=post(s,'/api/templates',{'name':'prompt-with-document.json','source_filename':'prompt-with-document.json','dataset_id':d['id'],
        'schema':{'type':'object','properties':{},'additionalProperties':False}})
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'action','operation':'extract','fields':[]})
    p=plan(s,d,text='Extract the attached file.',template_id=t['id'],submitted_prompt_id=t['id'],attached_filenames=['general.txt'])
    assert p['phase']=='awaiting_confirmation' and [c['tool'] for c in p['calls']]==['upload','extract']
    assert not s.api.get('/api/jobs').json()


def test_general_workflow_binds_to_confirmed_dataset_and_retains_followup_scope(system,monkeypatch):
    s=system;d=dataset(s)
    sequence(monkeypatch,tool('prepare_workflow',operation='upload'))
    p=plan(s,d,text='Upload this file',dataset_id='',attached_filenames=['general.txt'])
    assert not p['dataset_id']
    p['dataset_id']=d['id'];response=send_files(s,p);assert response.status_code==200,response.text
    conversation=main.get_record(p['conversation_id'],s.owner,'conversation')
    assert core.store.json(conversation.ref)['dataset_id']==d['id'] and conversation.parent_id==d['id']
    assert main.get_record(p['id'],s.owner,'agent_plan').parent_id==d['id']
    assert worker.run_once()
    sequence(monkeypatch,tool('get_workflow_status'),{'text':'Upload completed.','calls':[]})
    follow=plan(s,d,text='Did the upload finish?',conversation_id=p['conversation_id'])
    assert follow['conversation_id']==p['conversation_id']


def test_semantic_workflow_intent_prepares_attached_chain_without_a_second_model_guess(system,monkeypatch):
    s=system;d=dataset(s);t=template(s)
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'action','intent':'run_workflow','operation':'extract','fields':[]})
    monkeypatch.setattr(agent_model,'complete',lambda *args:pytest.fail('Explicit attached-file workflow is already resolved.'))
    p=plan(s,d,text='Obtain structured fields from these attachments.',attached_filenames=['general.txt'],template_id=t['id'])
    assert [c['tool'] for c in p['calls']]==['upload','extract'] and p['model_calls']==1
    assert p['phase']=='awaiting_confirmation' and not s.api.get('/api/jobs').json()


def test_classification_keeps_intent_separate_from_document_source(system,monkeypatch):
    monkeypatch.setattr(agent_model,'schema_decision',lambda *args,**kw:{'calls':[{'name':'select_source','arguments':{
        'intent':'run_workflow','source':'documents','supplementary_sources':[],'operation':'extract','fields':[],'document_names':[],'answer_kind':'other','filters':[],'result_scope':'selected_scope'}}]})
    with core.execution_context({'settings':core.settings()|{'model_provider':'ollama','model':'qwen3:4b'}}):
        frame=agent_model.classify([{'role':'user','content':'Process this attached file into saved fields.'}])
    assert frame['source']=='action' and frame['operation']=='extract'


def test_compact_semantic_classification_restores_defaults_and_validates_reads(system,monkeypatch):
    seen=[]
    def decision(messages,contracts,cfg,**kwargs):
        seen.append(contracts[0]['function']['parameters'])
        return {'calls':[{'name':'select_source','arguments':{
            'intent':'answer','source':'metadata','initial_reads':['list_documents']}}]}
    monkeypatch.setattr(agent_model,'schema_decision',decision)
    with core.execution_context({'settings':core.settings()|{'model_provider':'ollama','model':'qwen3:4b'}}):
        frame=agent_model.classify([{'role':'user','content':'List filenames.'}])
    assert frame['initial_reads']==['list_documents']
    assert frame['operation']=='none' and frame['filters']==[]
    assert frame['result_scope']=='selected_scope' and frame['document_names']==[]
    assert seen[0]['oneOf'][0]['required']==['intent','source','initial_reads','metadata_answer']
    assert seen[0]['oneOf'][1]['required']==['intent','source']
    monkeypatch.setattr(agent_model,'schema_decision',lambda *a,**kw:{'calls':[
        {'name':'select_source','arguments':{'intent':'answer','source':'metadata','initial_reads':['prepare_workflow']}}]})
    with core.execution_context({'settings':core.settings()|{'model_provider':'ollama','model':'qwen3:4b'}}):
        with pytest.raises(main.providers.ProviderError):agent_model.classify([{'role':'user','content':'List filenames.'}])


def test_local_classifier_receives_workflow_context_with_current_request(system,monkeypatch):
    seen=[]
    def decision(messages,*args,**kwargs):
        seen.extend(messages)
        return {'calls':[{'name':'select_source','arguments':{'intent':'answer','source':'results','supplementary_sources':[],'operation':'none',
            'fields':[],'document_names':[],'answer_kind':'summary','filters':[],'result_scope':'latest_workflow'}}]}
    monkeypatch.setattr(agent_model,'schema_decision',decision)
    with core.execution_context({'settings':core.settings()|{'model_provider':'ollama','model':'qwen3:4b'}}):
        frame=agent_model.classify([{'role':'system','content':'Verified latest workflow: extract completed'},
            {'role':'user','content':'can you summarize'}])
    assert frame['source']=='results' and frame['result_scope']=='latest_workflow'
    assert len([m for m in seen if m['role']=='system'])==1
    assert 'extract completed' not in seen[0]['content']
    assert sum('extract completed' in m['content'] for m in seen)==1
    assert 'extract completed' in seen[-1]['content'] and seen[-1]['content'].endswith('CURRENT request: can you summarize')


def test_mixed_question_observes_original_and_saved_status_without_workflow(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once()
    before=s.api.get('/api/jobs').json()
    seen=sequence(monkeypatch,{'text':'The original names Alice. The extraction is ready. [1]','calls':[]})
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'mixed','fields':[]})
    p=plan(s,d,text='What owner is written in the original and has extraction completed?',document_ids=[doc['id']])
    observations={m.get('tool_name'):json.loads(m['content']) for m in seen[0] if m['role']=='tool'}
    assert observations['search_documents']['matches']
    assert observations['find_extractions']['extractions'][0]['status']=='ready'
    assert observations['read_extraction_results']['records']
    assert not p['calls'] and s.api.get('/api/jobs').json()==before


def test_named_result_scope_does_not_read_other_files(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    other=post(s,'/api/documents/upload',files={'files':('other.txt',b'Bob is the owner.')},data={'dataset_id':d['id']})['documents'][0]
    assert worker.run_once()
    for id in (doc['id'],other['id']):
        post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[id],'template_id':t['id']});assert worker.run_once()
    seen=sequence(monkeypatch,{'text':'Saved owner Alice.','calls':[]})
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'results','fields':[],'document_names':['invoice.txt']})
    p=plan(s,d,text='Show saved extraction for invoice.txt.')
    message=events(reply(s,p))[-1]['message']
    observations=[o['result'] for o in message['tool_trace'] if o['tool']=='find_extractions']
    assert observations[0]['requested_document_ids']==[doc['id']] and len(observations[0]['extractions'])==1
    assert not p['calls']


def test_exact_document_quote_is_linked_without_inventing_claim_evidence():
    sources=[{'index':1,'text':'Platform engineer maintaining Kubernetes deployments and automated cloud infrastructure.'},
             {'index':2,'text':'Backend engineer building Python APIs.'}]
    text,selected=agent_graph.grounded_citations('Meera: "Platform engineer maintaining Kubernetes deployments and automated cloud infrastructure."',sources)
    assert text.endswith('[1]') and selected==sources[:1]
    text,selected=agent_graph.grounded_citations("Meera: 'Platform engineer maintaining Kubernetes deployments and automated cloud infrastructure.'",sources)
    assert text.endswith('[1]') and selected==sources[:1]
    text,selected=agent_graph.grounded_citations('Inspect these files.',sources)
    assert 'Retrieved passages: [1] [2]' in text and selected==sources


def test_skill_question_reads_relevant_fields_and_cites_saved_results(system,monkeypatch):
    from app import dataset_models as routing
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    ex=routing.create('extraction',s.owner,'Profile',{'document_ids':[doc['id']],
        'result':{'full_name':'Example Candidate','title':'Engineer','email':'fictional@example.com','phone':'123','location':'Example','summary':'Generic software work','skills':['Python']}},parent=d['id'])
    with core.Session.begin() as db:db.get(core.Record,ex.id).status='ready'
    seen=sequence(monkeypatch,{'text':'Example Candidate lists Python. [1]','calls':[]})
    classifier=[]
    def classify(messages):
        classifier.extend(messages)
        return {'source':'results','fields':['full_name','skills']}
    monkeypatch.setattr(agent_model,'classify',classify)
    p=plan(s,d,text='Who has Python skills?')
    assert 'skills' in classifier[0]['content']
    result=json.loads(next(m['content'] for m in seen[0] if m.get('tool_name')=='read_extraction_results'))
    assert result['records'][0]['fields']=={'full_name':'Example Candidate','skills':['Python']}
    assert result['records'][0]['citation_index']==1
    message=events(reply(s,p))[-1]['message'];citation=message['citations'][0]
    assert citation['kind']=='extraction' and citation['extraction_id']==ex.id and citation['dataset_id']==d['id']
    assert citation['version']==1 and 'Python' in citation['text']
    assert sum(m['content'].count('Who has Python skills?') for m in seen[0])==1


def test_merged_saved_result_citations_and_count_cover_all_pages(system,monkeypatch):
    from app import dataset_models as routing
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    ex=routing.create('extraction',s.owner,'Three profiles',{'document_ids':[doc['id']],'result':{'records':[
        {'source_filename':f'{i}.pdf','fields':{'name':name}} for i,name in enumerate(['Arjun','Meera','Nikhil'])]}},parent=d['id'])
    with core.Session.begin() as db:db.get(core.Record,ex.id).status='ready'
    seen=sequence(monkeypatch,{'text':'There are three saved profiles.','calls':[]})
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'results','fields':['name']})
    p=plan(s,d,text='Only three profiles?')
    scope=next(m['content'] for m in seen[0] if m['content'].startswith('Verified result scope:'))
    assert '"profile_count": 3' in scope
    answer=events(reply(s,p))[-1]['message']
    assert 'Saved result references: [1] [2] [3]' in answer['text']
    assert [c['record_index'] for c in answer['citations']]==[0,1,2]
    assert all(c['extraction_id']==ex.id for c in answer['citations'])


@pytest.mark.parametrize('kind',['count','filter','summary'])
def test_counts_and_skill_matches_are_computed_from_saved_values(system,monkeypatch,kind):
    from app import dataset_models as routing
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    ex=routing.create('extraction',s.owner,'Profiles',{'document_ids':[doc['id']],'result':{'records':[
        {'source_filename':'sara.pdf','fields':{'name':'Sara','skills':['React','TypeScript']}},
        {'source_filename':'dev.pdf','fields':{'name':'Dev','skills':['Python','Playwright']}},
        {'source_filename':'arjun.pdf','fields':{'name':'Arjun','skills':['Python','FastAPI']}}]}},parent=d['id'])
    with core.Session.begin() as db:db.get(core.Record,ex.id).status='ready'
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'complete',lambda *args:pytest.fail('The tool computes counts/matches; a model must not guess them.'))
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'results','answer_kind':kind,'fields':['name','skills'],
        'filters':[{'field':'skills','operator':'contains','value':'React'}] if kind=='filter' else []})
    before=s.api.get('/api/jobs').json()
    p=plan(s,d,text='Who lists React?' if kind=='filter' else 'How many profiles?')
    assert p['phase']=='answered' and not p['calls'] and p['model_calls']==1
    answer=events(reply(s,p))[-1]['message']
    if kind=='count':assert 'There are 3 saved profiles' in answer['text'] and len(answer['citations'])==3
    elif kind=='summary':
        assert all(name in answer['text'] for name in ('Sara','Dev','Arjun'))
        assert len(answer['citations'])==3 and ex.id in answer['text']
        assert 'saved extraction values' in answer['text'] and 'verified documents' not in answer['text']
    else:
        assert 'Sara' in answer['text'] and 'Dev' not in answer['text'] and 'Arjun' not in answer['text']
        assert len(answer['citations'])==1 and answer['citations'][0]['record_index']==0
        assert 'do not establish an expertise level' in answer['text']
    assert s.api.get('/api/jobs').json()==before


def test_filter_list_membership_and_missing_values_are_not_guessed():
    from app.agent_tools import matches_result_filter,definitions
    condition={'field':'skills','operator':'contains','value':'Java'}
    assert not matches_result_filter({'skills':['JavaScript']},condition)
    assert matches_result_filter({'skills':['JAVA']},condition)
    assert not matches_result_filter({},condition)
    assert not matches_result_filter({'years':True},{'field':'years','operator':'gte','value':1})
    from jsonschema import Draft202012Validator
    for contract in definitions():Draft202012Validator.check_schema(contract['function']['parameters'])


def test_followup_classification_does_not_replay_previous_user_filters(system,monkeypatch):
    s=system;d=dataset(s);sequence(monkeypatch,{'text':'Earlier result.','calls':[]})
    first=plan(s,d,text='Who lists React?')
    seen=[]
    def classify(messages):
        seen.extend(m['content'] for m in messages if m['role']=='user')
        return {'source':'results','answer_kind':'count','fields':[],'filters':[]}
    monkeypatch.setattr(agent_model,'classify',classify)
    monkeypatch.setattr(agent_model,'complete',lambda *args:pytest.fail('Count is authoritative.'))
    second=plan(s,d,text='Only three profiles?',conversation_id=first['conversation_id'])
    assert seen==['Only three profiles?']
    assert 'There are 0 saved profiles' in second['explanation']

def test_document_consent_failure_stops_without_repeated_model_or_tool_calls(system,monkeypatch):
    from fastapi import HTTPException
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'documents','fields':[]})
    monkeypatch.setattr(agent_model,'complete',lambda *args:pytest.fail('Consent cannot be repaired by model retries.'))
    def guard(consent,embedding=False,cfg=None):
        if embedding:raise HTTPException(409,'This action sends document text or your query to the configured external provider. Confirm external data transmission first.')
    monkeypatch.setattr(main,'external_check',guard)
    p=plan(s,d,text='Describe the original document.',document_ids=[doc['id']],allow_external=False)
    assert p['phase']=='answered' and p['model_calls']==1
    answer=events(reply(s,p))[-1]['message']
    assert 'Privacy & cloud consent' in answer['text'] and 'tool-step limit' not in answer['text']
    assert len(answer['tool_trace'])==1 and answer['tool_trace'][0]['result']['status_code']==409

def test_dataset_name_is_not_accepted_as_an_unmentioned_filename(system,monkeypatch):
    s=system;d=dataset(s,'Resume Extraction');doc=upload(s,d)['documents'][0]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'documents','fields':[],'document_names':['Resume Extraction']})
    monkeypatch.setattr(agent_model,'complete',lambda *args:{'text':'The original says Invoice total 42. [1]','calls':[]})
    p=plan(s,d,text='Describe the original document.',allow_external=True)
    answer=events(reply(s,p))[-1]['message']
    assert 'No file with that exact name' not in answer['text']
    assert answer['citations'][0]['document_id']==doc['id']
    assert answer['request_route']['decision']['document_names']==[]
