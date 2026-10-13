"""Latency paths retain persistence, scope checks and workflow routing."""
import json
import pytest
from ags_app import core, agent_graph, agent_model, ollama_provider
from ags_app.agent_tools import Tools
from ags_app.agent_workspace import PlanInput
from test_dataset_models import system, dataset
from test_agent_workspace import plan
from test_agent_chat import reply
from test_chat_stream import events


@pytest.mark.parametrize('text',['hi','HELLO!','hey','Good morning.'])
def test_plain_greeting_streams_and_persists_without_model_or_workspace_scan(system,monkeypatch,text):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    def forbidden(*args,**kwargs):pytest.fail('A plain greeting needs no model or catalog scan')
    monkeypatch.setattr(agent_model,'classify',forbidden)
    monkeypatch.setattr(agent_model,'complete',forbidden)
    monkeypatch.setattr(Tools,'snapshot',forbidden)
    monkeypatch.setattr(Tools,'definitions',forbidden)
    import ags_app.agent_workspace as workspace
    monkeypatch.setattr(workspace,'catalog',forbidden)
    p=plan(s,d,text=text,stream_answers=True)
    frames=events(reply(s,p));final=frames[-1]
    assert final['message']['text']=='Hi! How can I help you today?'
    assert any(f.get('text')==final['message']['text'] for f in frames[:-1])
    assert final['plan']['model_calls']==0 and final['plan']['calls']==[]
    saved=s.api.get('/api/conversations/'+final['conversation_id']).json()
    assert saved['messages'][-2]['text']==text and saved['messages'][-1]['status']=='completed'
    assert s.api.get('/api/jobs').json()==[]


@pytest.mark.parametrize('values',[
    {'text':'Hi, extract these files'}, {'text':'hi','attached_filenames':['invoice.txt']},
    {'text':'hi','submitted_prompt_id':'saved-prompt'}, {'text':'hi','earlier_request':'extract'},
    {'text':'hi','completed_tools':['upload']}, {'text':'hi what can you do?'},
])
def test_requests_and_workflow_context_do_not_become_greetings(values):
    assert agent_graph.greeting_answer(PlanInput(planner_model_id='test',**values))==''


def test_general_answer_uses_compact_instruction_without_tool_catalog(system,monkeypatch):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'general','fields':[]})
    monkeypatch.setattr(Tools,'definitions',lambda *args:pytest.fail('No contracts needed for general answers'))
    def complete(messages,tools):
        assert tools==[] and messages[0]['content']==agent_graph.GENERAL_INSTRUCTION
        assert len(messages[0]['content'])<500
        return {'text':'A pod runs containers.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='What is a Kubernetes pod?')
    assert p['explanation']=='A pod runs containers.' and p['calls']==[]


@pytest.mark.parametrize('stream',[False,True])
def test_qwen_without_tools_keeps_json_guard_against_legacy_reasoning(monkeypatch,stream):
    cfg=core.DEFAULTS|{'model_provider':'ollama','model':'qwen3:4b','max_output_tokens':512,'context_limit':8192}
    monkeypatch.setattr(core,'settings',lambda:cfg)
    original=[{'role':'system','content':'Answer briefly.'},{'role':'user','content':'What is a pod?'}]
    seen=[]
    def response(*args):
        payload=args[1]
        assert 'format' in payload and 'tools' not in payload and payload['think'] is False
        assert payload['messages'][-1]['content']=='<think>\n</think>\n\n'
        if stream:args[2]('A pod runs containers.')
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'tool_calls':[],'answer':'A pod runs containers.'})}}
    monkeypatch.setattr(ollama_provider,'request',response)
    from ags_app import agent_stream
    monkeypatch.setattr(agent_stream,'qwen_request',lambda payload,timeout,on_token:response('',payload,on_token))
    result=agent_model.complete(original,[],on_token=seen.append if stream else None)
    assert result=={'text':'A pod runs containers.','calls':[]}
    assert len(original)==2 and original[-1]['content']=='What is a pod?'
    if stream:assert seen==['A pod runs containers.']
