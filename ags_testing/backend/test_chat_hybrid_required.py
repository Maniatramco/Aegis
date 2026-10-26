"""Focused offline checks for the mandatory Unified Chat pipeline."""
import json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from ags_app import core,knowledge,agent_model,chat_policy,reranker,providers,dataset_models as routing
from ags_app.chat_agent import ChatAgent
from ags_app.chat_knowledge import PublishedKnowledge,assemble
from test_dataset_models import system,dataset,upload,template
from test_agent_workspace import plan


def install_models(monkeypatch):
    events=[]
    monkeypatch.setenv('AEGIS_RERANKER','local')
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    def rank(query,items,limit):
        events.append(('rerank',[r['dataset_id'] for r in items]))
        return items[:limit]
    def answer(messages,tools,**kwargs):
        assert tools==[]
        events.append(('answer',None))
        request=next(m['content'] for m in messages if m['role']=='user' and 'Published vector evidence:' in m['content'])
        evidence=json.loads(request.split('Published vector evidence:\n',1)[1])
        records=evidence['records']
        facts=evidence.get('verified_catalog_facts') or 'Aegis can explain its features and help with document processing.'
        if '[' not in facts:facts+=' ['+str(records[0]['citation_index'])+']'
        return {'text':facts,'calls':[]}
    monkeypatch.setattr(reranker,'rank',rank)
    monkeypatch.setattr(agent_model,'complete',answer)
    return events


@pytest.mark.parametrize('frame,question',[
    ({'source':'application'},'What can you do?'),
    ({'source':'general'},'Hello, what can you help with?'),
    ({'source':'metadata','initial_reads':['list_documents'],'metadata_answer':'document_count','answer_kind':'count'},'How many documents are in this dataset?'),
    ({'source':'results','fields':['owner'],'answer_kind':'summary'},'Summarize the saved owner.'),
    ({'source':'prompt'},'Explain the selected prompt.'),
    ({'source':'documents'},'What does invoice.txt say?'),
    ({'source':'knowledge','knowledge_types':['document_chunk']},'Find the invoice total semantically.')])
def test_every_question_retrieves_and_reranks_before_model(system,monkeypatch,frame,question):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    routing.create('extraction',s.owner,'Saved owner',{'document_ids':[doc['id']],'result':{'owner':'Alice'}},parent=d['id'])
    knowledge.sync(s.owner,d['id']);events=install_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',operation='none',**frame))
    response=plan(s,d,text=question,document_ids=[doc['id']],template_id=t['id'] if frame['source']=='prompt' else '')
    assert response['agent']=='chat' and not response['calls']
    assert [e[0] for e in events]==['rerank','answer']
    thread=core.store.json(routing.owned(response['conversation_id'],s.owner,'conversation').ref)
    reply=thread['messages'][-1];trace=reply['tool_trace'][0]['result']
    assert trace['retrieval']['mode']=='hybrid' and trace['retrieval']['reranker_enabled']
    assert trace['scope']['dataset_id']==d['id']
    assert trace['answer_check']=='passed'
    if frame.get('answer_kind')=='count':assert '1 document' in response['explanation']


def test_hybrid_root_and_dataset_filters_precede_reranking(system,monkeypatch):
    s=system;d=dataset(s);chosen=upload(s,d)['documents'][0];other=upload(s,d)['documents'][0]
    foreign=dataset(s,'Foreign');foreign_doc=upload(s,foreign)['documents'][0]
    knowledge.sync(s.owner,d['id']);knowledge.sync(s.owner,foreign['id'])
    seen=[];monkeypatch.setenv('AEGIS_RERANKER','local')
    def rank(query,items,limit):
        seen.extend(items)
        assert all(r['dataset_id']==d['id'] and r['document_ids']==[chosen['id']] for r in items)
        return items[:limit]
    monkeypatch.setattr(reranker,'rank',rank)
    view=PublishedKnowledge(s.owner,d['id'],[chosen['id']])
    rows=assemble(view.search('invoice',{'document_chunk'},root_ids={chosen['id']},require_rerank=True))
    assert seen and rows
    assert other['id'] not in json.dumps(rows) and foreign_doc['id'] not in json.dumps(rows)


def test_missing_citations_repair_once_and_preserve_scope(system,monkeypatch):
    s=system;d=dataset(s);knowledge.sync(s.owner,d['id']);install_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='application'))
    attempts=[]
    def answer(messages,tools,**kw):
        attempts.append(messages)
        return {'text':'Aegis can help with datasets.' if len(attempts)==1 else 'Aegis can help with datasets [citation_index: 1].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    response=plan(s,d,text='What can you do?')
    reply=core.store.json(routing.owned(response['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    result=reply['tool_trace'][0]['result']
    assert len(attempts)==2 and '[1]' in response['explanation']
    assert result['answer_validation']['attempts'][0]['reason']=='missing_citations'
    assert result['answer_check']=='passed' and result['answer_validation']['repaired']


def test_failed_repair_does_not_attach_sources_to_error(system,monkeypatch):
    s=system;d=dataset(s);knowledge.sync(s.owner,d['id']);install_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='application'))
    calls=[]
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:(calls.append(1) or {'text':'','calls':[]}))
    response=plan(s,d,text='What can you do?')
    reply=core.store.json(routing.owned(response['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert len(calls)==2 and 'empty answer' in response['explanation']
    assert not reply['citations'] and 'Retrieved passages' not in response['explanation']
    assert reply['tool_trace'][0]['result']['answer_validation']['reason']=='empty_answer'


def test_disabled_reranker_fails_before_answer_model(system,monkeypatch):
    s=system;d=dataset(s);knowledge.sync(s.owner,d['id']);install_models(monkeypatch)
    monkeypatch.setenv('AEGIS_RERANKER','none')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='application'))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**k:pytest.fail('Do not answer without reranking'))
    model=next(m for m in d['models'] if 'chat' in m['capabilities'])
    response=s.api.post('/api/agent-v2/plans',json={'text':'What can you do?','planner_model_id':model['id'],'dataset_id':d['id']})
    assert response.status_code==502 and 'reranking is unavailable' in response.json()['detail']


def test_chat_validation_and_legacy_validation_stay_separate():
    records=[{'citation_index':1,'data':{'fields':{'phone':None}}},{'citation_index':2,'data':{}}]
    normalized=chat_policy.normalize_citations('Values are missing [1, 2].',records)
    assert chat_policy.answer_problem(normalized,records) is None
    assert not chat_policy.checked_answer('Values are missing [1, 2].',records)
    assert chat_policy.answer_problem('All fields are complete [1].',records)=='unsupported_completeness'
    assert chat_policy.answer_problem('Found 7 documents [1].',records,6)=='incorrect_exact_count'
    assert chat_policy.answer_problem('Details [9].',records)=='unknown_citations'


def test_guidance_only_publication_keeps_document_entries(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d);snapshot,_=knowledge.sync(s.owner,d['id'])
    before=core.local_store.json(knowledge._manifest_ref(snapshot))
    monkeypatch.setattr(knowledge,'GUIDE',dict(knowledge.GUIDE,datasets=knowledge.GUIDE['datasets']+' Updated guidance.'))
    _,result=knowledge.sync(s.owner,d['id'],application_only=True)
    after=core.local_store.json(knowledge._manifest_ref(snapshot))
    assert result['removed']==0 and result['upserted']==len(knowledge.GUIDE)
    assert {k:v for k,v in before['points'].items() if v['source_type']!='application'}=={k:v for k,v in after['points'].items() if v['source_type']!='application'}
    assert 'onboarding alone does not upload' in knowledge.GUIDE['datasets'].lower()


@pytest.mark.parametrize('ids',[ [2], [9] ])
def test_chat_only_structured_citations_are_model_selected(system,monkeypatch,ids):
    from ags_app import chat_agent,ollama_provider,agent_context
    monkeypatch.setattr(agent_context,'fit',lambda messages,cfg,budget,serialize,stage:serialize(messages))
    monkeypatch.setattr(ollama_provider,'generation_options',lambda wire,budget:{'num_predict':budget,'num_ctx':8192})
    captured=[]
    def request(path,payload,timeout):
        captured.append(payload)
        assert payload['format']['properties']['citations']['items']['enum']==[1,2]
        assert payload['format']['properties']['citations']['minItems']==1
        assert 'tools' not in payload
        return {'done':True,'message':{'content':json.dumps({'answer':'Aegis supports datasets.','citations':ids})}}
    monkeypatch.setattr(ollama_provider,'request',request)
    records=[{'citation_index':1},{'citation_index':2}]
    with core.execution_context({'settings':dict(core.settings(),model_provider='ollama',model='qwen3:4b',timeout=30,max_output_tokens=128)}):
        if ids==[9]:
            with pytest.raises(providers.ProviderError,match='invalid answer/citation'):chat_agent.complete_answer([{'role':'system','content':'Use evidence.'},{'role':'user','content':'What can you do?'}],records)
        else:
            output=chat_agent.complete_answer([{'role':'system','content':'Use evidence.'},{'role':'user','content':'What can you do?'}],records)
            assert output['text']=='Aegis supports datasets. [2]' and '[1]' not in output['text']
    assert len(captured)==1
