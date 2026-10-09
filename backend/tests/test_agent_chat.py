import json
import asyncio
import httpx
import pytest
from app import providers,core,main
from test_dataset_models import system,dataset,upload,post,model
from test_agent_workspace import planner,proposal,plan
from test_chat_stream import events
from app.agent_workspace import readonly_question,knowledge_lookup

@pytest.mark.parametrize('text',[
    'can you pls find out is thr any information related to kubernates',
    'Is there any information about Kubernetes?',
    'Search for Kubernetes documents',
    'Find information about invoice totals',
    'What does my knowledge base say about deployments?',
])
def test_knowledge_lookup_retrieves_selected_scope_without_general_planning(system,monkeypatch,text):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    other=dataset(s,'Other');upload(s,other)
    monkeypatch.setattr(providers,'plan',lambda *a:pytest.fail('Explicit knowledge lookup must not become general chat'))
    seen=[]
    def search(q,owner,docs,top_k):
        seen.append([item.id for item in docs]);return []
    monkeypatch.setattr(providers,'search',search)
    p=plan(s,d,text=text,document_ids=[doc['id']])
    assert p['answer_mode']=='documents' and p['calls']==[]
    answer=events(reply(s,p))[-1]['message']
    assert seen==[[doc['id']]]
    assert answer['status']=='completed' and answer['citations']==[]
    assert "couldn't find evidence" in answer['text']
    assert not any(j['kind']=='extract' for j in s.api.get('/api/jobs').json())

def test_knowledge_lookup_requires_dataset_instead_of_claiming_no_uploads(system,monkeypatch):
    s=system;d=dataset(s)
    monkeypatch.setattr(providers,'plan',lambda *a:pytest.fail('Lookup routing must be deterministic'))
    p=plan(s,d,text='Find information about Kubernetes',dataset_id='')
    assert p['answer_mode']=='documents'
    assert reply(s,p).status_code==422

def test_knowledge_lookup_without_document_selection_searches_only_its_dataset(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    other=dataset(s,'Other');other_doc=upload(s,other)['documents'][0]
    monkeypatch.setattr(providers,'plan',lambda *a:pytest.fail('Lookup must use retrieval'))
    p=plan(s,d,text='Find information about invoice totals in my knowledge base')
    message=events(reply(s,p))[-1]['message']
    assert message['status']=='completed' and message['citations']
    assert {c['document_id'] for c in message['citations']}=={doc['id']}
    assert other_doc['id'] not in {c['document_id'] for c in message['citations']}

@pytest.mark.parametrize('text',[
    'Explain a Python loop', 'What is Kubernetes?', 'hi',
    'Upload and extract these documents', 'Can you extract information from my documents?',
])
def test_knowledge_lookup_keeps_general_questions_and_actions_separate(text):
    assert not knowledge_lookup(text)

def reply(s,p,**body):
    return s.api.post(f'/api/agent-v2/plans/{p["id"]}/reply',json=body)

def test_general_question_uses_no_documents_and_preserves_followups(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d)
    planner(monkeypatch,proposal((),answer_mode='general'))
    monkeypatch.setattr(providers,'search',lambda *a:pytest.fail('General chat must not retrieve documents'))
    seen=[]
    async def answer(q,sources,history):
        assert core.settings()['general_chat'] and sources==[]
        seen.append(history);yield 'A concise general answer.'
    monkeypatch.setattr(providers,'answer_stream_async',answer)
    first=plan(s,d,text='Explain a loop in Python')
    result=events(reply(s,first))[-1]
    assert result['message']['status']=='completed' and result['message']['citations']==[]
    conv=result['conversation_id']
    second=plan(s,d,text='Show an example')
    assert events(reply(s,second,conversation_id=conv))[-1]['conversation_id']==conv
    assert seen[1][0]['text']=='Explain a loop in Python'
    saved=s.api.get('/api/agent-v2/plans/'+first['id']).json()
    assert saved['chat']['id']==result['message']['id']
    assert reply(s,first).status_code==409
    assert not any(j['kind']=='extract' for j in s.api.get('/api/jobs').json())

def test_document_answer_reuses_canonical_sources_and_scoped_history(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    planner(monkeypatch,proposal((),answer_mode='documents'))
    p=plan(s,d,text='Who owns this?',document_ids=[doc['id']])
    event=events(reply(s,p))[-1]
    assert event['message']['citations'][0]['document_id']==doc['id']
    assert event['message']['citations'][0]['url'].startswith('/api/documents/')
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']==event['message']
    other=dataset(s,'Other');upload(s,other)
    p2=plan(s,other,text='Who owns this?')
    assert reply(s,p2,conversation_id=event['conversation_id']).status_code==409
    s.owner='mallory'
    assert reply(s,p).status_code==404

def test_document_chat_uses_mapped_model_instead_of_unmapped_planner(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d)
    mapped=next(m for m in d['models'] if 'chat' in m['capabilities'])
    other=model(s,mapped['connection_profile_id'],name='Planner only')
    planner(monkeypatch,proposal((),answer_mode='documents'))
    p=plan(s,d,text='Who owns it?',planner_model_id=other['id'])
    answer=events(reply(s,p))[-1]['message']
    assert answer['model_selection']['model_id']==mapped['id']
    p2=plan(s,d,text='Who owns it?',planner_model_id=other['id'])
    assert reply(s,p2,document_model_id=other['id']).status_code==409

def test_explicit_document_filter_overrides_general_guess_and_uses_selected_agent_model(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    mapped=next(m for m in d['models'] if 'chat' in m['capabilities'])
    planner(monkeypatch,proposal((),answer_mode='general'))
    p=plan(s,d,text='Summarize this',document_ids=[doc['id']],answer_scope='documents')
    assert p['answer_mode']=='documents'
    message=events(reply(s,p,document_model_id=mapped['id']))[-1]['message']
    assert message['model_selection']['model_id']==p['planner']['id']==mapped['id']
    assert {c['document_id'] for c in message['citations']}=={doc['id']}

def test_explicit_document_filter_preserves_workflow_confirmations(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d,text='Extract these documents',document_ids=[doc['id']],answer_scope='documents')
    assert p['calls'][0]['tool']=='extract'
    assert reply(s,p).status_code==409

def test_action_plan_cannot_bypass_confirmation_through_chat(system,monkeypatch):
    s=system;d=dataset(s);planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d)
    assert reply(s,p).status_code==409
    assert s.api.get('/api/jobs').json()==[]

def test_fact_question_cannot_become_an_extraction_workflow(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d)
    planner(monkeypatch,proposal(('extract',),answer_mode='documents'))
    p=plan(s,d,text='What are the reference, supplier and amount in this document?')
    assert p['calls']==[]
    assert events(reply(s,p))[-1]['message']['status']=='completed'
    assert not any(j['kind']=='extract' for j in s.api.get('/api/jobs').json())

@pytest.mark.parametrize('text,readonly',[
    ('What are the supplier and amount?',True),('Hi, how do I upload a file?',True),
    ('Can you tell me the amount?',True),('What fields can you extract?',True),
    ('Please extract the fields',False),('Can you extract this?',False),
    ('What is the amount? Also extract it with my template.',False),
])
def test_question_guard_preserves_explicit_action_requests(text,readonly):
    assert readonly_question(text)==readonly

def test_general_conversation_rejects_document_scope_and_unowned_models(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    assert s.api.post('/api/conversations',json={'mode':'general','dataset_id':d['id']}).status_code==422
    c=post(s,'/api/conversations',{'mode':'general'})
    url='/api/conversations/'+c['id']+'/messages/stream'
    assert s.api.post(url,json={'text':'hi','dataset_id':d['id']}).status_code==409
    assert s.api.post(url,json={'text':'hi','document_ids':[doc['id']]}).status_code==409
    assert s.api.post(url,json={'text':'hi','model_id':'missing'}).status_code==404

def test_repeated_question_restores_the_original_answer(system,monkeypatch):
    s=system;d=dataset(s);planner(monkeypatch,proposal((),answer_mode='general'))
    p=plan(s,d,text='Same question');a=events(reply(s,p))[-1]
    p2=plan(s,d,text='Same question');b=events(reply(s,p2,conversation_id=a['conversation_id']))[-1]
    assert a['message']['id']!=b['message']['id']
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']['id']==a['message']['id']

def test_general_failure_is_saved_without_fabricated_answer(system,monkeypatch):
    s=system;d=dataset(s);planner(monkeypatch,proposal((),answer_mode='general'))
    async def unavailable(*args):
        raise providers.ProviderError('Offline')
        yield
    monkeypatch.setattr(providers,'answer_stream_async',unavailable)
    p=plan(s,d);event=events(reply(s,p))[-1]
    assert event['message']['status']=='failed' and not event['message']['text']
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['chat']['error']['retryable']

def test_followup_planning_context_is_owned_and_dataset_scoped(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d);planner(monkeypatch,proposal((),answer_mode='documents'))
    p=plan(s,d,text='Who is the owner?');a=events(reply(s,p))[-1]
    seen=[]
    monkeypatch.setattr(providers,'plan',lambda instruction,text,schema:seen.append(json.loads(text)) or proposal((),answer_mode='documents'))
    plan(s,d,text='What about the amount?',conversation_id=a['conversation_id'])
    assert seen[0]['prior_questions']==['Who is the owner?']
    other=dataset(s,'Other')
    model=next(m for m in other['models'] if 'chat' in m['capabilities'])
    body={'text':'follow-up','planner_model_id':model['id'],'dataset_id':other['id'],'conversation_id':a['conversation_id']}
    assert s.api.post('/api/agent-v2/plans',json=body).status_code==409
    s.owner='mallory'
    assert s.api.get('/api/conversations/'+a['conversation_id']).status_code==404

@pytest.mark.parametrize('frames,expected,error',[
    ([{'message':{'content':'Draft reasoning without an opening tag'}},{'message':{'content':'</think>Final '}},{'message':{'content':'answer'},'done':True}], 'Final answer',False),
    ([{'message':{'content':'<thi'}},{'message':{'content':'nk>internal'}},{'message':{'content':'</think>\nUseful '}},{'message':{'content':'answer'},'done':True}], 'Useful answer',False),
    ([{'message':{'content':'partial'}}], '',True),
    ([{'message':{'content':''},'done':True}], '',True),
    ([{'message':{'content':'partial'},'done':True,'done_reason':'length'}], 'partial',True),
])
def test_local_general_stream_requires_completion_and_hides_thinking(monkeypatch,frames,expected,error):
    from app import ollama_provider as local
    real_client=httpx.AsyncClient
    def handler(request):
        data=json.loads(request.content)
        assert data['stream'] and data['think'] is False
        assert request.url.host=='127.0.0.1'
        return httpx.Response(200,content='\n'.join(json.dumps(frame) for frame in frames))
    monkeypatch.setattr(local,'generation_options',lambda *args:{})
    monkeypatch.setattr(local.httpx,'AsyncClient',lambda **kwargs:real_client(**kwargs,transport=httpx.MockTransport(handler)))
    chunks=[]
    async def run():
        async for piece in local.general_chat_stream('qwen3:4b','Answer clearly','question',30):chunks.append(piece)
    if error:
        with pytest.raises(local.OllamaError):asyncio.run(run())
    else:asyncio.run(run())
    assert ''.join(chunks)==expected
