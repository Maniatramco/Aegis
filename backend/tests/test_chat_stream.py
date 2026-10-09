import asyncio
import json
from app import main, providers, ollama_provider
from test_dataset_models import system, dataset, upload, conversation


def events(response):
    return [json.loads(frame.split('data: ',1)[1]) for frame in response.text.split('\n\n') if 'data: ' in frame]


def test_empty_provider_failure_is_saved_and_retryable(system, monkeypatch):
    d=dataset(system);upload(system,d);c=conversation(system,d)
    async def unavailable(*args):
        raise providers.ProviderError('Synthetic provider failure')
        yield
    monkeypatch.setattr(providers,'answer_stream_async',unavailable)
    response=system.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Question','allow_external':True})
    event=events(response)[-1]
    assert 'No answer was generated.' in event['detail']
    assert 'partial response' not in event['detail']
    assert event['message']['status']=='failed' and event['message']['error']['retryable']
    saved=system.api.get('/api/conversations/'+c['id']).json()['messages']
    assert saved[-1]==event['message'] and saved[-2]==event['user_message']


def test_partial_failure_keeps_text_and_canonical_citations(system,monkeypatch):
    d=dataset(system);upload(system,d);c=conversation(system,d)
    async def interrupted(*args):
        yield 'Alice owns the project [1].'
        raise providers.ProviderError('Synthetic interruption')
    monkeypatch.setattr(providers,'answer_stream_async',interrupted)
    response=system.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Who owns it?','allow_external':True})
    event=events(response)[-1]
    assert event['message']['text']=='Alice owns the project [1].'
    assert event['message']['citations'][0]['index']==1
    assert 'partial response has been kept' in event['detail']


def test_waiting_stream_has_heartbeat_and_persists_before_done(system,monkeypatch):
    d=dataset(system);upload(system,d);c=conversation(system,d)
    async def slow(*args):
        await asyncio.sleep(.04)
        yield 'Alice [1].'
    monkeypatch.setattr(main,'CHAT_HEARTBEAT_SECONDS',.01)
    monkeypatch.setattr(providers,'answer_stream_async',slow)
    response=system.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Who owns it?','allow_external':True})
    assert ': keep-alive\n\n' in response.text
    event=events(response)[-1]
    assert event['message']['status']=='completed'
    assert system.api.get('/api/conversations/'+c['id']).json()['messages'][-1]==event['message']


def test_local_chat_history_excludes_failed_messages_and_internal_metadata(monkeypatch):
    def response(path,payload,timeout):
        user=payload['messages'][1]['content']
        assert 'Internal model config' not in user and 'failed answer' not in user
        assert 'Earlier question' in user and 'Completed response' in user
        assert 'Respond naturally and briefly to greetings' in payload['messages'][0]['content']
        return {'done':True,'message':{'content':'Hello! What would you like to know about your documents?'}}
    monkeypatch.setattr(ollama_provider,'request',response)
    history=[{'role':'user','text':'Earlier question','model_selection':{'name':'Internal model config'}},
             {'role':'assistant','text':'failed answer','status':'failed'},
             {'role':'assistant','text':'Completed response','status':'completed'}]
    assert ollama_provider.chat('qwen3:4b','hi',[{'document_name':'synthetic','text':'Evidence'}],history,30).startswith('Hello!')
