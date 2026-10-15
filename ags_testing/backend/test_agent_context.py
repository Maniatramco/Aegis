"""Wire-budget and no-chat-history regressions; real model/UI evidence is separate."""
import copy
import json
import pytest
from ags_app import agent_context, agent_model, core, providers, ollama_provider, dataset_models as routing
from test_dataset_models import system, dataset, upload
from test_agent_workspace import plan


def msg(role, content, **kw):
    return dict(role=role, content=content, **kw)


def test_history_is_excluded_even_with_spare_capacity_and_archive_is_untouched():
    messages=[msg('system','Trusted instruction'),
        msg('user','PRIVATE EARLIER REQUEST',_context={'kind':'history','unit':'old'}),
        msg('assistant','STALE EARLIER CLAIM',_context={'kind':'history','unit':'old'}),
        msg('user','Current question')]
    original=copy.deepcopy(messages);audits=[]
    with agent_context.observe(audits.append):
        wire=agent_context.fit(messages,{'context_limit':32768},1024,lambda m:m,'answer')
    assert wire==[messages[0],messages[-1]] and messages==original
    assert audits[0]['history_turns_dropped']==1 and audits[0]['dispatch_allowed']


def test_optional_examples_are_removed_as_whole_pairs_not_current_question_or_evidence():
    messages=[msg('system','Trusted instruction'),
        msg('user','x'*6000,_context={'kind':'example','unit':'one'}),
        msg('assistant','Example answer',_context={'kind':'example','unit':'one'}),
        msg('user','Current question'),msg('tool','Required evidence',tool_call_id='actual')]
    audits=[]
    with agent_context.observe(audits.append):
        wire=agent_context.fit(messages,{'context_limit':2000},256,lambda m:m,'routing')
    assert wire==[messages[0],messages[-2],messages[-1]]
    assert audits[0]['example_pairs_dropped']==1
    assert audits[0]['estimated_total_tokens']<=2000


def pair(name, args, value, id):
    return [msg('assistant','',tool_calls=[{'id':id,'type':'function','function':{'name':name,'arguments':args}}]),
        msg('tool',json.dumps(value),tool_call_id=id,tool_name=name)]


def test_only_exact_successful_single_reads_are_deduplicated_without_orphans():
    messages=pair('list_documents',{'offset':0},{'documents':['stale']},'old')
    messages+=pair('list_documents',{'offset':20},{'documents':['page2']},'page')
    messages+=pair('list_documents',{'offset':0},{'documents':['fresh']},'new')
    messages+=pair('list_documents',{'offset':0},{'error':'retry'},'error')
    messages+=pair('prepare_workflow',{}, {'executed':False},'mutation1')
    messages+=pair('prepare_workflow',{}, {'executed':False},'mutation2')
    original=copy.deepcopy(messages)
    wire=agent_context.fit(messages,{'context_limit':32768},256,lambda m:m,'answer')
    assert 'stale' not in json.dumps(wire) and 'fresh' in json.dumps(wire)
    assert [m['tool_call_id'] for m in wire if m['role']=='tool']==['page','new','error','mutation1','mutation2']
    assert messages==original
    assert all(wire[i+1]['tool_call_id']==m['tool_calls'][0]['id'] for i,m in enumerate(wire) if m['role']=='assistant')


@pytest.mark.parametrize('stream',[False,True])
def test_qwen_wire_excludes_history_includes_contract_once_and_reserves_response(system,monkeypatch,stream):
    seen=[];audits=[]
    contract={'type':'function','function':{'name':'list_documents','parameters':{'type':'object','properties':{}}}}
    def request(*args):
        payload=args[1];seen.append(payload)
        return {'done':True,'done_reason':'stop','message':{'content':'{"tool_calls":[],"answer":"Fresh answer"}'}}
    monkeypatch.setattr(ollama_provider,'request',request)
    from ags_app import agent_stream
    monkeypatch.setattr(agent_stream,'qwen_request',lambda payload,timeout,on_token:request('/api/chat',payload,timeout))
    cfg=dict(core.settings(),model='qwen3:4b',context_limit=8192,max_output_tokens=1024,timeout=30)
    with core.execution_context({'settings':cfg}),agent_context.observe(audits.append):
        agent_model.schema_decision([msg('system','Instruction'),msg('user','HISTORY'*20000,_context={'kind':'history','unit':'old'}),
            msg('user','Current question')],[contract],cfg,on_token=(lambda _:None) if stream else None)
    packed=json.dumps(seen[0]['messages'],ensure_ascii=False)
    assert 'HISTORY' not in packed and '_context' not in packed and packed.count('list_documents')==1
    assert audits[0]['estimated_total_tokens']<=8192
    assert audits[0]['reserved_output_tokens']==seen[0]['options']['num_predict']==1024
    assert seen[0]['options']['num_ctx']==8192


def test_required_question_overflow_rejected_before_provider_and_audited(system,monkeypatch):
    monkeypatch.setattr(ollama_provider,'request',lambda *args:pytest.fail('Oversize request reached inference'))
    audits=[];cfg=dict(core.settings(),model='qwen3:4b',context_limit=8192,max_output_tokens=1024)
    with agent_context.observe(audits.append),pytest.raises(providers.ProviderError,match='required question or evidence'):
        agent_model.schema_decision([msg('system','Instructions'),msg('user','Q'*18000)],[],cfg)
    assert not audits[0]['dispatch_allowed'] and audits[0]['estimated_total_tokens']>8192


@pytest.mark.parametrize('protocol',['openai','ollama'])
def test_native_wire_budget_includes_tools_and_never_leaks_internal_tags(system,monkeypatch,protocol):
    seen=[];audits=[]
    contract={'type':'function','function':{'name':'list_documents','parameters':{'type':'object','properties':{}}}}
    def request(path,payload,*args):
        seen.append(payload)
        return {'done':True,'message':{'content':'Fresh answer'},
            'choices':[{'finish_reason':'stop','message':{'content':'Fresh answer'}}]}
    monkeypatch.setattr(ollama_provider,'request',request);monkeypatch.setattr(providers,'openai_request',request)
    cfg=dict(core.settings(),model_provider=protocol,model='native-test',context_limit=8192,max_output_tokens=1024)
    with core.execution_context({'settings':cfg}),agent_context.observe(audits.append):
        result=agent_model.complete([msg('system','Instructions'),
            msg('assistant','HISTORY'*5000,_context={'kind':'history','unit':'old'}),
            msg('user','Current question',_context_refs={'document_ids':['internal']})],[contract])
    assert result['text']=='Fresh answer' and seen[0]['tools']==[contract]
    assert 'HISTORY' not in json.dumps(seen) and '_context' not in json.dumps(seen)
    assert audits[0]['estimated_total_tokens']<=8192 and audits[0]['reserved_output_tokens']==1024


def test_classifier_prunes_examples_for_long_current_question_without_truncating(system,monkeypatch):
    audits=[];seen=[];question='List the document filenames. '+('Synthetic current-request details. '*230)
    frame={'intent':'answer','source':'metadata','initial_reads':['list_documents'],'metadata_answer':'none'}
    def request(path,payload,timeout):
        seen.append(payload)
        return {'done':True,'message':{'content':json.dumps({'tool_calls':[{'name':'select_source','arguments':frame}],'answer':''})}}
    monkeypatch.setattr(ollama_provider,'request',request)
    cfg=dict(core.settings(),model_provider='ollama',model='qwen3:4b',context_limit=8192,max_output_tokens=1024)
    with core.execution_context({'settings':cfg}),agent_context.observe(audits.append):
        assert agent_model.classify([msg('user',question)])['source']=='metadata'
    assert question in seen[0]['messages'][-2]['content']
    assert audits[0]['example_pairs_dropped']>0 and audits[0]['estimated_total_tokens']<=8192


def test_graph_long_archive_never_reaches_any_model_and_fresh_metadata_wins(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    archive=[{'role':role,'text':'OLD_CHAT_SENTINEL '+('stale unrelated text '*300),'status':'completed'}
        for _ in range(80) for role in ('user','assistant')]
    conversation=routing.create('conversation',s.owner,'Long QA chat',{'dataset_id':d['id'],'messages':archive},parent=d['id'])
    seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    def classify(messages):
        seen.extend(messages)
        catalog=json.loads(messages[0]['content'].split(': ',1)[1])
        assert catalog['chat_history_supplied'] is False and 'previous_user_request' not in catalog
        return {'intent':'answer','source':'metadata','initial_reads':['list_documents'],'metadata_answer':'none'}
    def complete(messages,contracts,**kwargs):
        seen.extend(messages)
        observation=json.loads(next(m['content'] for m in messages if m.get('tool_name')=='list_documents'))
        assert observation['documents'][0]['id']==doc['id'] and contracts==[]
        return {'text':'invoice.txt is the available document.','calls':[]}
    monkeypatch.setattr(agent_model,'classify',classify);monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='List the filenames.',conversation_id=conversation.id)
    assert 'invoice.txt' in p['explanation'] and 'OLD_CHAT_SENTINEL' not in json.dumps(seen)
    assert core.store.json(conversation.ref)['messages'][:160]==archive


def test_result_followup_reads_verified_result_ids_without_prior_chat_text(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    ex=routing.create('extraction',s.owner,'Selected result',{'document_ids':[doc['id']],'result':{'name':'Alice Example'}},parent=d['id'])
    other=routing.create('extraction',s.owner,'Unrelated result',{'document_ids':[doc['id']],'result':{'name':'Other Example'}},parent=d['id'])
    old={'role':'assistant','text':'BOGUS_OLD_CLAIM Nothing was extracted.', 'status':'completed',
        'review_actions':[{'extraction_id':ex.id}], 'citations':[{'document_name':doc['name']}],
        'tool_trace':[{'tool':'read_extraction_results','result':{'records':[]}}]}
    conversation=routing.create('conversation',s.owner,'Result QA',{'dataset_id':d['id'],'messages':[old]},parent=d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    def classify(messages):
        assert 'BOGUS_OLD_CLAIM' not in json.dumps(messages)
        assert '"last_knowledge_source": "results"' in messages[0]['content']
        return {'source':'results','fields':[],'answer_kind':'summary','result_scope':'latest_workflow','scope_reference':'previous_answer'}
    monkeypatch.setattr(agent_model,'classify',classify)
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:pytest.fail('Summary uses fresh saved fields'))
    p=plan(s,d,text='Summarize those results.',conversation_id=conversation.id)
    assert 'Alice Example' in p['explanation'] and 'Other Example' not in p['explanation']
    assert ex.id in p['explanation'] and other.id not in p['explanation']


@pytest.mark.parametrize('foreign',[False,True])
def test_previous_source_reference_is_revalidated_and_never_widens_current_filter(system,monkeypatch,foreign):
    s=system;d=dataset(s);current=upload(s,d)['documents'][0]
    other=dataset(s,'Other') if foreign else d
    referenced=routing.create('document',s.owner,'previous.txt',{},parent=other['id'])
    old={'role':'assistant','text':'STALE CLAIM','status':'completed',
        'citations':[{'document_id':referenced.id,'document_name':'previous.txt'}],
        'tool_trace':[{'tool':'search_documents','result':{'matches':[]}}]}
    conversation=routing.create('conversation',s.owner,'Scope QA',{'dataset_id':d['id'],'messages':[old]},parent=d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda _: {'source':'documents','scope_reference':'previous_answer'})
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:pytest.fail('Disallowed references reached inference'))
    response=s.api.post('/api/agent-v2/plans',json={'text':'What does that file say?',
        'dataset_id':d['id'],'planner_model_id':d['default_chat_model_id'],
        'conversation_id':conversation.id,'document_ids':[current['id']]})
    assert response.status_code==422
    assert len(core.store.json(conversation.ref)['messages'])==1
