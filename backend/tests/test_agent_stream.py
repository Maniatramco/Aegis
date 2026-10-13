"""Streaming transport tests; model intelligence is checked in the live browser."""
import json
import httpx
import pytest
from app import core, main, providers, agent_graph, agent_model, agent_stream
from test_dataset_models import system, dataset
from test_agent_workspace import plan
from test_agent_chat import reply
from test_chat_stream import events


@pytest.mark.parametrize('answer',['A quote: "hello".\nNext line.', 'Emoji 😀 and café.', 'literal \\u and slash /', ''])
def test_json_answer_decodes_every_boundary_without_exposing_control_data(answer):
    raw=json.dumps({'tool_calls':[],'answer':answer},ensure_ascii=True)
    last=''
    for end in range(len(raw)+1):
        prefix=agent_stream.answer_prefix(raw[:end])
        assert answer.startswith(prefix) and prefix.startswith(last)
        last=prefix
    assert last==answer


def test_tool_arguments_and_nested_answer_never_appear_as_chat():
    raw=json.dumps({'tool_calls':[{'name':'prepare_workflow','arguments':{'answer':'SECRET TOOL DATA'}}],'answer':''})
    assert all(agent_stream.answer_prefix(raw[:end])=='' for end in range(len(raw)+1))
    assert agent_stream.answer_prefix('{"answer":"Hello","tool_calls":')==''
    assert agent_stream.answer_prefix('{"answer":"Hello","tool_calls":[]}')=='Hello'


def setup_graph(monkeypatch):
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'general','fields':[]})


def test_deferred_plan_does_no_inference_get_keeps_input_and_reply_streams(system,monkeypatch):
    s=system;d=dataset(s);setup_graph(monkeypatch);seen=[]
    def complete(messages,tools,on_token=None):
        assert on_token
        on_token('Hello ');seen.append('first token');on_token('world.')
        return {'text':'Hello world.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='Say hello',stream_answers=True)
    assert p['phase']=='queued' and not seen and 'deferred_input' not in p
    restored=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert restored['phase']=='queued' and 'deferred_input' not in restored
    record=main.get_record(p['id'],s.owner,'agent_plan')
    assert core.store.json(record.ref)['deferred_input']['text']=='Say hello'
    frames=events(reply(s,p));assert [f['text'] for f in frames if 'text' in f]==['Hello ','world.']
    assert frames[-1]['message']['text']=='Hello world.'
    assert frames[-1]['message']['status']=='completed'
    assert frames[-1]['plan']['calls']==[]
    progress=[f['workflow'] for f in frames if 'workflow' in f]
    assert progress and progress[-1]['status']=='completed'
    assert progress[0]['steps'][0]['label']=='Checking agent configuration' and progress[0]['steps'][0]['status']=='running'
    assert [s['label'] for s in progress[-1]['steps']]==['Checking agent configuration','Checking workspace','Reading current workspace state','Understanding request','Generating response','Saving response']
    assert all(s['status']=='completed' and s['duration_ms']>=0 for s in progress[-1]['steps'])
    assert any(w['steps'][-1]['label']=='Generating response' and w['steps'][-1]['status']=='running' for w in progress)
    assert frames[-1]['message']['answer_workflow']==progress[-1]
    conversation=s.api.get('/api/conversations/'+frames[-1]['conversation_id']).json()
    assert conversation['messages'][-1]['answer_workflow']==progress[-1]
    assert reply(s,p).status_code==409
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']['text']=='Hello world.'


def test_deferred_failure_saves_partial_and_does_not_emit_done(system,monkeypatch):
    s=system;d=dataset(s);setup_graph(monkeypatch)
    def complete(messages,tools,on_token=None):
        on_token('Partial answer');raise providers.ProviderError('Synthetic disconnect')
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='Say hello',stream_answers=True)
    response=reply(s,p);frames=events(response)
    assert 'event: done' not in response.text and frames[-1]['message']['status']=='failed'
    saved=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert saved['chat']['text']=='Partial answer' and saved['chat']['status']=='failed'
    assert saved['answer_workflow']['status']=='failed'
    assert saved['answer_workflow']['steps'][-1]['label']=='Generating response'
    assert saved['answer_workflow']['steps'][-1]['status']=='failed'
    assert s.api.get('/api/jobs').json()==[]


def test_deferred_reply_rechecks_disabled_model_before_any_inference(system,monkeypatch):
    s=system;d=dataset(s);setup_graph(monkeypatch)
    p=plan(s,d,text='Say hello',stream_answers=True)
    model=next(m for m in d['models'] if m['id']==d['default_chat_model_id'])
    body={k:model[k] for k in ('name','connection_profile_id','provider_model','capabilities')}|{'enabled':False}
    assert s.api.put('/api/models/'+model['id'],json=body).status_code==200
    monkeypatch.setattr(agent_model,'classify',lambda *args:pytest.fail('Disabled model must not receive a request'))
    response=reply(s,p);frames=events(response)
    assert response.status_code==200 and 'event: done' not in response.text
    assert frames[0]['workflow']['steps'][0]['label']=='Checking agent configuration'
    assert frames[-1]['message']['status']=='failed'
    assert frames[-1]['message']['answer_workflow']['steps'][0]['status']=='failed'
    assert s.api.get('/api/jobs').json()==[] and reply(s,p).status_code==409


def test_deferred_workflow_remains_pending_until_confirmation(system,monkeypatch):
    s=system;d=dataset(s);setup_graph(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda messages:{'source':'action','operation':'upload','fields':[]})
    def complete(messages,tools,on_token=None):
        return {'text':'','calls':[{'id':'call-upload','name':'prepare_workflow','arguments':{'operation':'upload'}}]}
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='Upload the attached file',attached_filenames=['invoice.txt'],stream_answers=True)
    result=events(reply(s,p))[-1]
    assert result['plan']['calls'][0]['tool']=='upload'
    assert result['plan']['calls'][0]['status']=='pending'
    assert s.api.get('/api/jobs').json()==[] and s.api.get('/api/documents').json()==[]


class Response:
    status_code=200
    def __init__(self,lines):self.lines=lines
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_lines(self):yield from self.lines


def transport(monkeypatch,lines):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kwargs):
            assert kwargs['json']['stream'] is True
            return Response(lines)
    monkeypatch.setattr(agent_stream.httpx,'Client',Client)
    monkeypatch.setattr(agent_stream.ollama_provider,'base_url',lambda:'http://localhost:11434')


def test_qwen_transport_emits_before_model_finishes_and_checks_terminal(monkeypatch):
    pieces=[]
    def lines():
        yield json.dumps({'message':{'content':'{"tool_calls":[],"answer":"Hello '},'done':False})
        assert [p for p in pieces if p]==['Hello ']
        yield json.dumps({'message':{'content':'world."}'},'done':False})
        assert [p for p in pieces if p]==['Hello ','world.']
        yield json.dumps({'done':True,'done_reason':'stop'})
    transport(monkeypatch,lines())
    result=agent_stream.qwen_request({'model':'qwen3:4b'},10,pieces.append)
    assert json.loads(result['message']['content'])['answer']=='Hello world.'


def test_qwen_incomplete_stream_keeps_emitted_text_and_fails(monkeypatch):
    transport(monkeypatch,[json.dumps({'message':{'content':'{"tool_calls":[],"answer":"Partial'}})])
    pieces=[]
    with pytest.raises(providers.ProviderError,match='incomplete'):
        agent_stream.qwen_request({},10,pieces.append)
    assert [p for p in pieces if p]==['Partial']


def test_native_local_stream_hides_reasoning_and_retains_tools(monkeypatch):
    transport(monkeypatch,[json.dumps({'message':{'content':piece},'done':False}) for piece in ['<thi','nk>private','</think>','Hello ','world.']]+[json.dumps({'message':{'tool_calls':[{'function':{'name':'list_documents','arguments':{}}}]},'done':True})])
    pieces=[];result=agent_stream.native_request('ollama',{}, {'timeout':10},pieces.append)
    assert ''.join(pieces)=='Hello world.' and result['message']['tool_calls'][0]['function']['name']=='list_documents'


def test_openai_stream_collects_fragmented_tool_arguments_without_exposing_them(monkeypatch):
    monkeypatch.setattr(agent_stream.core,'api_key',lambda:'synthetic-test-key')
    lines=[{'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call-1','function':{'name':'list_documents','arguments':'{"lim'}}]}}]},
           {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'it":1}'}}]},'finish_reason':'tool_calls'}]}]
    transport(monkeypatch,['data: '+json.dumps(e) for e in lines]+['data: [DONE]'])
    pieces=[];result=agent_stream.native_request('openai',{}, {'timeout':10,'model_provider':'openai'},pieces.append)
    call=result['choices'][0]['message']['tool_calls'][0]
    assert call['id']=='call-1' and json.loads(call['function']['arguments'])=={'limit':1}
    assert ''.join(pieces)==''


def test_stream_can_cancel_during_private_control_tokens(monkeypatch):
    transport(monkeypatch,[json.dumps({'message':{'content':'{"tool_calls":['}})])
    def cancelled(piece):raise providers.ProviderError('Stopped')
    with pytest.raises(providers.ProviderError,match='Stopped'):agent_stream.qwen_request({},10,cancelled)


def test_stream_recovers_runner_failure_before_tokens_without_duplicate_answer(monkeypatch):
    original=httpx.Client;seen=[];pieces=[]
    def handle(request):
        seen.append(json.loads(request.content))
        if len(seen)==1:return httpx.Response(500,json={'error':'llama runner process has terminated: CUDA error'})
        line=json.dumps({'message':{'content':'{"tool_calls":[],"answer":"Recovered answer"}'},'done':True,'done_reason':'stop'})
        return httpx.Response(200,content=line+'\n')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    payload={'model':'qwen3:4b','options':{'num_ctx':8192}}
    result=agent_stream.qwen_request(payload,60,pieces.append)
    assert seen==[dict(payload,stream=True)]*2
    assert ''.join(pieces)=='Recovered answer' and json.loads(result['message']['content'])['answer']=='Recovered answer'


def test_partial_stream_failure_never_replays_visible_text(monkeypatch):
    original=httpx.Client;seen=[];pieces=[]
    def handle(request):
        seen.append(request)
        lines=[{'message':{'content':'{"tool_calls":[],"answer":"Partial answer'}},
               {'error':'llama runner process has terminated: CUDA error private details'}]
        return httpx.Response(200,content='\n'.join(json.dumps(line) for line in lines)+'\n')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    with pytest.raises(providers.ProviderError) as caught:agent_stream.qwen_request({'model':'qwen3:4b'},60,pieces.append)
    assert len(seen)==1 and ''.join(pieces)=='Partial answer' and 'private' not in str(caught.value)
