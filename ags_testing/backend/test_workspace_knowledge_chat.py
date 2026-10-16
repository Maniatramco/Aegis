"""Dataset Chat cannot share processing Agent requests, history or jobs."""
import json
import pytest
from sqlalchemy import select
from ags_app import core,knowledge,agent_model,providers,worker
from ags_app.ags_agent.dataset_chat_knowledge import WorkspaceKnowledge,assemble
from test_dataset_models import system,dataset,upload,model,mapping,post
from test_chat_agent import install_chat_models

def setup(s,monkeypatch):
    a=dataset(s,'Invoice workspace');one=upload(s,a)['documents'][0]
    b=dataset(s,'Policy workspace');two=upload(s,b)['documents'][0]
    knowledge.sync(s.owner,a['id']);knowledge.sync(s.owner,b['id'])
    install_chat_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('Dataset Chat must not invoke the processing Agent router.'))
    return a,one,b,two

def body(a,b,**values):
    return {'text':'Summarize workspace knowledge.','dataset_ids':[a['id'],b['id']],
        'model_id':next(item['id'] for item in a['models'] if 'chat' in item['capabilities'])}|values

def test_combined_summary_follows_hybrid_rerank_generation_validation(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch);seen=[]
    def answer(messages,tools,**kw):
        assert tools==[]
        evidence=json.loads(next(m['content'] for m in messages if 'Published vector evidence:\n' in m.get('content','')).split('Published vector evidence:\n',1)[1]);seen.append(evidence)
        assert set(evidence['scope']['dataset_ids'])=={a['id'],b['id']}
        assert 'retrieval' not in evidence and 'semantic_candidates' not in evidence
        assert all(name in str(evidence['records']) for name in ('Invoice workspace','Policy workspace'))
        return {'text':'The workspace includes invoice and policy knowledge. [1]','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    result=post(s,'/api/dataset-chat/messages',body(a,b,summary=True));message=result['message']
    assert seen and message['answer_workflow']['status']=='completed'
    assert message['source_summary']=={'checked_count':4,'dataset_count':2,'documents':2,'saved_results':0,'dataset_descriptions':2,'guidance':0,'cited_count':1}
    assert message['tool_trace'][0]['result']['retrieval']['mode']=='hybrid'
    assert message['tool_trace'][0]['result']['retrieval']['reranker_enabled']
    for citation in message['citations']:assert s.api.get(citation['source_url']).status_code==200

def test_file_scope_and_read_only_schema_cannot_widen_access(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    records=assemble(WorkspaceKnowledge(s.owner,[a['id'],b['id']],[one['id']]).search('Alice owner',['document_chunk'],require_rerank=True))
    assert records and {id for record in records for id in record['document_ids']}=={one['id']}
    for values in ({'dataset_ids':[]},{'document_ids':[]},{'agent_operation':'upload'},{'attached_filenames':['x.txt']},{'template_id':'x'}):
        assert s.api.post('/api/dataset-chat/messages',json=body(a,b,**values)).status_code==422
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,dataset_ids=[a['id']],document_ids=[two['id']])).status_code==404
    s.owner='another-user'
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b)).status_code==404

def test_exact_thread_scope_and_agent_history_isolation(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    result=post(s,'/api/dataset-chat/messages',body(a,b));id=result['conversation_id']
    assert any(item['id']==id for item in s.api.get('/api/dataset-chat/conversations').json())
    assert all(item['id']!=id for item in s.api.get('/api/conversations').json())
    assert s.api.get('/api/conversations/'+id).status_code==404
    assert post(s,'/api/dataset-chat/messages',body(a,b,dataset_ids=[b['id'],a['id']],conversation_id=id))['conversation_id']==id
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,dataset_ids=[a['id']],conversation_id=id)).status_code==409
    legacy=post(s,'/api/conversations',{'dataset_id':a['id']})
    assert s.api.get('/api/dataset-chat/conversations/'+legacy['id']).status_code==404
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,conversation_id=legacy['id'])).status_code==404

def test_different_embedding_spaces_keep_own_citations(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    embedding=next(item for item in b['models'] if 'embedding' in item['capabilities']);original=providers.fingerprint
    monkeypatch.setattr(providers,'fingerprint',lambda cfg=None:original(cfg)+('-second' if (cfg or core.settings()).get('embedding_model')=='mock-embedding-second' else ''))
    replacement=model(s,embedding['connection_profile_id'],'Second embedding',caps=['embedding'],provider_model='mock-embedding-second')
    mapping(s,b,mappings=b['mappings']+[{'model_id':replacement['id'],'enabled':True}],embedding_model_id=replacement['id'])
    post(s,'/api/documents/'+two['id']+'/reindex',{'allow_external':True})
    for _ in range(10):
        if not worker.run_once():break
    knowledge.sync(s.owner,b['id']);view=WorkspaceKnowledge(s.owner,[a['id'],b['id']],summary=True)
    assert len({snapshot['knowledge_collection'] for snapshot in view.snapshots})==2
    records=assemble(view.search('Summarize invoice and policy knowledge',['dataset','document_chunk'],require_rerank=True))
    assert {record['_knowledge_dataset_id'] for record in records}=={a['id'],b['id']}
    for record in records:assert s.api.get('/api/knowledge/published-sources/'+record['knowledge_id'],params={'collection':record['_knowledge_collection'],'dataset_id':record['_knowledge_dataset_id']}).status_code==200

def test_exact_count_uses_complete_catalog_after_retrieval(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    result=post(s,'/api/dataset-chat/messages',body(a,b,text='How many documents are there?'))
    assert '2' in result['message']['text']
    assert result['message']['tool_trace'][0]['result']['complete_catalog']

def test_complete_file_lists_use_catalog_and_reject_ranked_filtered_lists(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    result=post(s,'/api/dataset-chat/messages',body(a,b,text='List all files'))
    evidence=result['message']['tool_trace'][0]['result']
    assert evidence['complete_catalog'] and not evidence['semantic_candidates']
    assert len(evidence['records'])==2
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,text='List all files with overdue invoices')).status_code==422

def test_access_rechecked_after_inference_before_saving(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    def answer(*args,**kw):
        with s.session.begin() as db:db.get(core.Record,b['id']).status='deleted'
        return {'text':'The workspace has invoice knowledge. [1]','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b)).status_code==404
    assert s.api.get('/api/dataset-chat/conversations').json()==[]

def test_streamed_chat_creates_no_agent_plans_or_jobs(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch);before={item['id'] for item in s.api.get('/api/jobs').json()}
    response=s.api.post('/api/dataset-chat/reply',json=body(a,b,summary=True))
    assert response.status_code==200 and 'event: done' in response.text,response.text
    assert 'event: sources' in response.text and response.text.index('event: sources')<response.text.index('event: done')
    assert '"checked_count": 4' in response.text
    assert 'dataset_knowledge_chat' in response.text and 'citation' in response.text
    assert {item['id'] for item in s.api.get('/api/jobs').json()}==before
    with s.session() as db:assert not list(db.scalars(select(core.Record).where(core.Record.kind.in_(['agent_plan','agent_goal']))))

def test_original_agent_rejects_dataset_chat_request_fields(system,monkeypatch):
    s=system;a,one,b,two=setup(s,monkeypatch)
    response=s.api.post('/api/agent-v2/plans',json={'text':'Hello','planner_model_id':body(a,b)['model_id'],'knowledge_dataset_ids':[a['id']]})
    assert response.status_code==422

def test_checked_sources_deduplicate_passages_and_keep_saved_results_distinct():
    from ags_app.ags_agent.dataset_chat import source_summary
    records=[{'entity_id':'doc-one:chunk1','source_type':'document_chunk','document_ids':['doc-one']},
        {'entity_id':'doc-one:chunk2','source_type':'document_chunk','document_ids':['doc-one']},
        {'entity_id':'result-one:record1','source_type':'extraction','document_ids':['doc-one']},
        {'entity_id':'result-one:record2','source_type':'extraction','document_ids':['doc-one']},
        {'entity_id':'dataset-one','source_type':'dataset'}]
    assert source_summary(records,1)=={'checked_count':3,'dataset_count':1,'documents':1,'saved_results':1,'dataset_descriptions':1,'guidance':0}


def test_dashboard_direct_source_guards_and_safe_general_context():
    from ags_app.ags_agent.dataset_chat_general import requires_knowledge,reference_context
    for text in ('Hi','Hello!','Good morning','Thanks!','What is the capital of France?','What is a dataset?'):
        assert not requires_knowledge(text)
    for text in ('Hi, how many documents are there?','Hello, list all files','Hi, summarize my selected file','What can you do?',
                 'What is Aegis?','Who owns invoice.pdf?','Show model mappings','What is our revenue?'):
        assert requires_knowledge(text)
    grounded=[{'role':'user','text':'SECRET SOURCE FACT'},
              {'role':'assistant','text':'PRIVATE SOURCE ANSWER [1]','request_route':{'routing_mode':'dataset_knowledge_chat'}}]
    assert requires_knowledge('Tell me more',previous=grounded)
    assert not requires_knowledge('Hello',previous=grounded)
    assert reference_context(grounded)=={'previous_answer':'knowledge','previous_general_turns':[]}
    general=grounded+[{'role':'user','text':'What is photosynthesis?'},
        {'role':'assistant','text':'Plants turn light into chemical energy.','request_route':{'routing_mode':'dataset_general_chat'}}]
    assert not requires_knowledge('Tell me more',previous=general)
    assert 'SECRET' not in json.dumps(reference_context(general)) and 'PRIVATE' not in json.dumps(reference_context(general))


@pytest.mark.parametrize('question,reply',[
    ('Hi','Hello! How can I help?'),('Hello!','Hello!'),('Thanks!','You are welcome!'),
    ('What is the capital of France?','Paris is the capital of France.'),
    ('Explain photosynthesis simply.','Plants use sunlight to turn water and carbon dioxide into food.')])
def test_general_questions_use_one_model_call_without_embeddings_or_knowledge(system,monkeypatch,question,reply):
    from ags_app import dataset_models as routing,reranker,ollama_provider
    from ags_app.ags_agent import dataset_chat,dataset_chat_general
    s=system;a,one,b,two=setup(s,monkeypatch);calls=[]
    def decide(messages,settings):
        value=json.loads(messages[-1]['content']);assert value['current_request']==question
        assert 'greetings' in messages[0]['content'] and 'If unsure' in messages[0]['content']
        assert settings['max_output_tokens']<=384
        calls.append(value);return json.dumps({'route':'general','answer':reply})
    def forbid(*args,**kwargs):pytest.fail('Direct general chat must never use knowledge, embeddings or reranking.')
    monkeypatch.setattr(dataset_chat_general,'decision',decide)
    monkeypatch.setattr(dataset_chat,'WorkspaceKnowledge',forbid)
    monkeypatch.setattr(routing,'embedding_snapshot',forbid)
    monkeypatch.setattr(routing,'execution_snapshot',forbid)
    monkeypatch.setattr(ollama_provider,'model_digest',forbid)
    monkeypatch.setattr(providers,'search',forbid);monkeypatch.setattr(reranker,'rank',forbid)
    result=post(s,'/api/dataset-chat/messages',body(a,b,text=question,dataset_ids=[a['id']]))
    message=result['message']
    assert len(calls)==1 and message['text']==reply
    assert message['request_route']['routing_mode']=='dataset_general_chat'
    assert message['citations']==[] and message['tool_trace']==[]
    assert message['source_summary']['knowledge_used'] is False
    assert message['source_summary']['checked_count']==message['source_summary']['cited_count']==0
    assert not any('Retrieving' in step['label'] or 'Rerank' in step['label'] for step in message['answer_workflow']['steps'])


def test_mixed_greeting_and_source_count_cannot_bypass_grounding(system,monkeypatch):
    from ags_app.ags_agent import dataset_chat_general
    s=system;a,one,b,two=setup(s,monkeypatch)
    monkeypatch.setattr(dataset_chat_general,'decision',lambda *args:pytest.fail('Explicit source requests keep their grounded route.'))
    result=post(s,'/api/dataset-chat/messages',body(a,b,text='Hi, how many documents are there?'))
    assert result['message']['request_route']['routing_mode']=='dataset_knowledge_chat'
    assert result['message']['tool_trace'][0]['result']['complete_catalog']
    assert result['message']['source_summary']['checked_count']>0


@pytest.mark.parametrize('raw', ['not JSON','{"route":"general","answer":"Fake fact [1]"}',
    '{"route":"general","answer":"I searched your documents."}',
    '{"route":"general","answer":"","extra":"wrong"}',
    '{"route":"knowledge","answer":""}'])
def test_unknown_or_invalid_direct_answer_keeps_grounded_pipeline(system,monkeypatch,raw):
    from ags_app.ags_agent import dataset_chat_general
    s=system;a,one,b,two=setup(s,monkeypatch)
    monkeypatch.setattr(dataset_chat_general,'decision',lambda *args:raw)
    result=post(s,'/api/dataset-chat/messages',body(a,b,text='Who is the owner?'))
    assert result['message']['request_route']['routing_mode']=='dataset_knowledge_chat'
    assert result['message']['source_summary']['checked_count']>0
    assert result['message']['tool_trace'][0]['result']['retrieval']['mode']=='hybrid'


def test_direct_chat_still_validates_scope_model_and_post_inference_access(system,monkeypatch):
    from ags_app.ags_agent import dataset_chat_general
    s=system;a,one,b,two=setup(s,monkeypatch);calls=[]
    monkeypatch.setattr(dataset_chat_general,'decision',lambda *args:calls.append(True) or '{"route":"general","answer":"Hello!"}')
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,text='Hi',dataset_ids=[a['id']],document_ids=[two['id']])).status_code==404
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,text='Hi',model_id='missing-model')).status_code==404
    assert calls==[]
    def revoke(*args):
        with s.session.begin() as db:db.get(core.Record,b['id']).status='deleted'
        return '{"route":"general","answer":"Hello!"}'
    monkeypatch.setattr(dataset_chat_general,'decision',revoke)
    assert s.api.post('/api/dataset-chat/messages',json=body(a,b,text='Hello')).status_code==404
    assert s.api.get('/api/dataset-chat/conversations').json()==[]


def test_general_chat_stream_has_honest_zero_sources_and_no_jobs(system,monkeypatch):
    from ags_app.ags_agent import dataset_chat_general
    s=system;a,one,b,two=setup(s,monkeypatch)
    monkeypatch.setattr(dataset_chat_general,'decision',lambda *args:'{"route":"general","answer":"Hello!"}')
    before={item['id'] for item in s.api.get('/api/jobs').json()}
    response=s.api.post('/api/dataset-chat/reply',json=body(a,b,text='Hi'))
    assert 'event: done' in response.text and 'event: sources' in response.text
    assert '"knowledge_used": false' in response.text and '"checked_count": 0' in response.text
    assert 'Retrieving indexed dataset knowledge' not in response.text
    assert {item['id'] for item in s.api.get('/api/jobs').json()}==before


def test_direct_ollama_uses_one_bounded_structured_call(system,monkeypatch):
    from ags_app import ollama_provider
    from ags_app.ags_agent import dataset_chat_general,dataset_chat
    from ags_app.ags_agent.chat_agent import chat_limits
    s=system;a=dataset(s,'Single model');request=dataset_chat.ChatInput(**body(a,a,text='Hello',dataset_ids=[a['id']]))
    snap=dataset_chat.chat_model_snapshot(request,s.owner)
    snap['settings'].update(model_provider='ollama',model='qwen3:4b')
    payloads=[]
    def generate(path,payload,timeout):
        payloads.append(payload)
        assert path=='/api/chat' and payload['think'] is False and payload['format']==dataset_chat_general.SCHEMA
        assert 'tools' not in payload
        return {'done':True,'done_reason':'stop','message':{'content':'{"route":"general","answer":"Hello!"}'}}
    monkeypatch.setattr(ollama_provider,'request',generate)
    assert dataset_chat_general.general_reply('Hello',snap,chat_limits(snap['settings']))=='Hello!'
    assert len(payloads)==1
