"""Unclear input must stop before knowledge retrieval or workflow proposals."""
import pytest
from ags_app import core,main,agent_model,providers,chat_agent
from ags_app.agent_intent import input_problem,route_problem
from test_dataset_models import system,dataset,upload
from test_agent_workspace import plan

def forbidden(*args,**kwargs):pytest.fail('An unclear request must not infer, retrieve or execute.')

@pytest.mark.parametrize('text',['@\\','@@','@Uplaod','@Uploader','/','/Uplaod','/Onboarded','?','...'])
def test_invalid_inputs_rejected_before_plan_creation(system,monkeypatch,text):
    s=system;d=dataset(s);monkeypatch.setattr(agent_model,'classify',forbidden)
    response=s.api.post('/api/agent-v2/plans',json={'text':text,'dataset_id':d['id'],'planner_model_id':d['default_chat_model_id']})
    assert response.status_code==422,response.text
    assert s.api.get('/api/jobs').json()==[] and s.api.get('/api/documents').json()==[]

@pytest.mark.parametrize('text',['do it','continue','show me','that one'])
def test_ambiguous_short_requests_clarify_without_model_or_vectors(system,monkeypatch,text):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',forbidden);monkeypatch.setattr(chat_agent,'PublishedKnowledge',forbidden)
    p=plan(s,d,text=text)
    assert 'What would you like' in p['explanation'] and p['calls']==[] and p['model_calls']==0
    message=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert message['request_route']['routing_mode']=='clarification' and not message['citations'] and not message['tool_trace']

@pytest.mark.parametrize('decision',[
    {'agent':'clarify','question':'What task or information do you need?'},
    {'agent':'chat','query':'status','request_evidence':'Explain Parquet.'},
    {'agent':'chat','query':'documents','request_evidence':'A selected dataset from context'},
    {'agent':'chat','query':'status'},
    {'agent':'chat','query':'models','request_evidence':42},
])
def test_semantically_unsupported_route_never_reads_catalog(system,monkeypatch,decision):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    calls=[]
    def choose(messages,tools,**kw):
        calls.append(tools);return {'calls':[{'name':'route_aegis','arguments':decision}]}
    monkeypatch.setattr(agent_model,'complete',choose);monkeypatch.setattr(chat_agent,'PublishedKnowledge',forbidden)
    p=plan(s,d,text='Explain Parquet.')
    assert p['calls']==[] and len(calls)==1
    message=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert message['request_route']['decision']['intent']=='clarify'
    assert not message['citations'] and not message['tool_trace'] and s.api.get('/api/jobs').json()==[]

def test_ordinary_document_spelling_errors_still_get_exact_filenames(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d);request='Can you list me douccments name available for this dataset?'
    from ags_app import knowledge
    knowledge.sync(s.owner,d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    from test_chat_agent import install_chat_models
    install_chat_models(monkeypatch)
    answer = agent_model.complete
    calls=[]
    def choose(messages,tools,**kw):
        if not tools:
            return answer(messages,tools,**kw)
        calls.append(tools);return {'calls':[{'name':'route_aegis','arguments':{'agent':'chat','query':'documents','request_evidence':request}}]}
    monkeypatch.setattr(agent_model,'complete',choose)
    p=plan(s,d,text=request)
    assert 'invoice.txt' in p['explanation'] and 'Extraction status:' not in p['explanation']
    assert len(calls)==1 and not p['calls']

def test_request_evidence_validation_is_not_keyword_routing():
    assert input_problem('Email upload@example.com') is None
    assert input_problem('Describe @Extract') is None
    assert route_problem('What is the processing statuus?',{'agent':'chat','query':'status','request_evidence':'processing statuus'}) is None
    assert route_problem('Quels documents sont disponibles?',{'agent':'chat','query':'documents','request_evidence':'documents'}) is None
    assert route_problem('How can I run extraction?',{'agent':'onboard_extract','operation':'extract','request_evidence':'run extraction'})
