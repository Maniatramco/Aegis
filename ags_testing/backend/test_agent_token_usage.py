import json
import httpx
import pytest
from ags_app import token_usage, agent_model, agent_stream, core, providers
from test_dataset_models import system, dataset
from test_agent_workspace import plan
from test_agent_chat import reply
from test_agent_stream import setup_graph
from test_chat_stream import events


def test_provider_totals_include_multiple_calls_without_reasoning_double_count():
    with token_usage.collect() as calls:
        token_usage.record({'usage': {'prompt_tokens': 100, 'completion_tokens': 40,
                                    'completion_tokens_details': {'reasoning_tokens': 30}}}, 'openai')
        token_usage.record({'prompt_eval_count': 50, 'eval_count': 10}, 'ollama')
        assert token_usage.summary(calls)['input_tokens'] == 150
        assert token_usage.summary(calls)['output_tokens'] == 50
        with token_usage.collect() as other:
            token_usage.record({'usage': {'input_tokens': 3, 'output_tokens': 2}}, 'openai')
            assert token_usage.summary(other)['input_tokens'] == 3
        assert len(calls) == 2
    token_usage.record({'usage': {'prompt_tokens': 999, 'completion_tokens': 999}}, 'openai')
    assert len(calls) == 2


def test_missing_or_invalid_usage_is_unknown_not_zero():
    with token_usage.collect() as calls:
        token_usage.record({}, 'openai')
        token_usage.record({'usage': {'prompt_tokens': True, 'completion_tokens': -1}}, 'openai')
        summary = token_usage.summary(calls)
        assert summary['input_tokens'] is None and summary['output_tokens'] is None
        assert not summary['complete'] and summary['reported_calls'] == 0
        token_usage.record({'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}, 'openai')
        assert token_usage.summary(calls)['input_tokens'] == 10
        assert not token_usage.summary(calls)['complete']
    assert token_usage.summary([])['input_tokens'] == 0


def test_stream_usage_only_frame_after_final_choice_is_retained(monkeypatch):
    frames = [
        {'choices': [{'delta': {'content': 'Ready'}, 'finish_reason': None}]},
        {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
        {'choices': [], 'usage': {'prompt_tokens': 17, 'completion_tokens': 3}},
    ]
    original = httpx.Client
    def handle(request):
        assert json.loads(request.content)['stream_options'] == {'include_usage': True}
        return httpx.Response(200, text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n')
    monkeypatch.setattr(agent_stream.httpx, 'Client', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(core, 'api_key', lambda: 'synthetic-key')
    pieces=[]
    result=agent_stream.native_request('openai', {}, {'model_provider':'openai','timeout':10}, pieces.append)
    assert result['usage'] == frames[-1]['usage']
    assert ''.join(pieces) == 'Ready'


def test_generation_adapter_records_actual_usage(monkeypatch):
    cfg=dict(core.settings(),model_provider='openai',model='synthetic',context_limit=16384,max_output_tokens=128)
    monkeypatch.setattr(core,'settings',lambda:cfg)
    monkeypatch.setattr(providers,'openai_request',lambda *_:{'choices':[{'finish_reason':'stop','message':{'content':'Ready'}}],
        'usage':{'prompt_tokens':23,'completion_tokens':4}})
    with token_usage.collect() as calls:
        assert agent_model.complete([{'role':'user','content':'Status?'}],[])['text']=='Ready'
    assert token_usage.summary(calls)['input_tokens']==23
    assert token_usage.summary(calls)['output_tokens']==4


def test_failed_provider_request_is_unknown_not_a_free_zero_call(monkeypatch):
    cfg=dict(core.settings(),model_provider='openai',model='synthetic',context_limit=16384,max_output_tokens=128)
    monkeypatch.setattr(core,'settings',lambda:cfg)
    def fail(*_):raise providers.ProviderError('Synthetic timeout')
    monkeypatch.setattr(providers,'openai_request',fail)
    with token_usage.collect() as calls:
        with pytest.raises(providers.ProviderError):
            agent_model.complete([{'role':'user','content':'Status?'}],[])
    usage=token_usage.summary(calls)
    assert usage['model_calls']==1 and not usage['complete'] and usage['input_tokens'] is None


def test_concurrent_answers_do_not_share_usage():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier=Barrier(2)
    def run(amount):
        with token_usage.collect() as calls:
            barrier.wait()
            token_usage.record({'usage':{'prompt_tokens':amount,'completion_tokens':1}},'openai')
            barrier.wait()
            return token_usage.summary(calls)['input_tokens']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run,[10,100]))==[10,100]


def test_usage_is_saved_and_returned_on_completed_stream(system,monkeypatch):
    s=system;d=dataset(s);setup_graph(monkeypatch)
    def complete(messages,tools,on_token=None):
        token_usage.record({'usage':{'prompt_tokens':31,'completion_tokens':7}},'openai')
        if on_token:on_token('Ready.')
        return {'text':'Ready.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='Give a short greeting',stream_answers=True)
    frames=events(reply(s,p))
    usage=frames[-1]['message']['token_usage']
    assert usage['input_tokens']==31 and usage['output_tokens']==7 and usage['complete']
    saved=s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']
    assert saved['token_usage']==usage
