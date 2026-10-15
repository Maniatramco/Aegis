"""Conversation regression, scoped hybrid retrieval, and pre-display guards."""
import json,os
from pathlib import Path
import pytest
from ags_app import core,knowledge,agent_model,reranker,dataset_models as routing,chat_policy
from ags_app.chat_knowledge import PublishedKnowledge,assemble
from ags_app.chat_retrieval import keyword_ranks,fuse
from ags_app.agent_intent import route_problem
from test_dataset_models import system,dataset,upload
from test_agent_workspace import plan
from test_chat_agent import install_chat_models


def forbidden(*a,**kw):pytest.fail('Exact answers must not use answer generation or chat history.')


@pytest.mark.parametrize('question,source,kind',[
 ('how many prompt files are there','metadata','count'),
 ('prompt json files','metadata','list'),
 ('i mean how many prompt template are there','metadata','count'),
 ('can you bring me what is mentioned in prompt template','prompt','other')])
def test_prompt_routes_ignore_misleading_files_token(question,source,kind,monkeypatch):
    monkeypatch.setattr(agent_model,'schema_decision',forbidden)
    frame=agent_model.classify_vector([{'role':'user','content':question}])
    assert frame['source']==source and frame['answer_kind']==kind
    assert frame['operation']=='none'
    assert route_problem(question,{'agent':'chat','query':'documents','request_evidence':question})


def test_keyword_fusion_keeps_exact_identifier_and_distinct_entities():
    points={'v':{'entity_id':'v','text':'A software developer'},'k':{'entity_id':'k','text':'TS-1937 React accessibility'},
        'k2':{'entity_id':'k','text':'Another fragment TS-1937'}}
    keywords=keyword_ranks('TS-1937',points,25)
    assert set(keywords)=={'k','k2'}
    assert fuse(['v'],keywords,points,25)==['k','v']


def test_answer_checks_reject_false_completeness_and_invalid_citations():
    records=[{'citation_index':1,'data':{'fields':{'phone':None,'education':[{'graduation_year':None}]}}}]
    assert not chat_policy.checked_answer('All fields are present with no missing values. [1]',records)
    assert not chat_policy.checked_answer('The phone is unknown. [7]',records)
    assert not chat_policy.checked_answer('The phone is unknown.',records)
    assert chat_policy.checked_answer('Phone was not extracted. [1]',records)
    text=chat_policy.result_answer([dict(records[0],title='Resume',version=1,review_status='unreviewed')])
    assert 'Not extracted' in text and 'education[0].graduation_year' in text and 'no missing' not in text


def test_named_extraction_is_scoped_even_when_classifier_omits_names(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    current=routing.create('extraction',s.owner,'sample extract',{'document_ids':[doc['id']],'result':{'full_name':'Sara Khan','phone':None}},parent=d['id'])
    routing.create('extraction',s.owner,'other result',{'document_ids':[doc['id']],'result':{'full_name':'Aarav Krishnan'}},parent=d['id'])
    knowledge.sync(s.owner,d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='results',document_names=[],answer_kind='other'))
    install_chat_models(monkeypatch)
    p=plan(s,d,text='Summarize saved extraction named sample extract.')
    assert 'Sara Khan' in p['explanation'] and 'Aarav Krishnan' not in p['explanation']
    assert current.id in p['explanation'] and 'Not extracted' in p['explanation']


def test_document_filename_scope_is_preserved_for_saved_result_questions(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];other=upload(s,d)['documents'][0]
    current=routing.create('extraction',s.owner,'Chosen result',{'document_ids':[doc['id']],'result':{'full_name':'Sara Khan'}},parent=d['id'])
    routing.create('extraction',s.owner,'Other result',{'document_ids':[other['id']],'result':{'full_name':'Aarav Krishnan'}},parent=d['id'])
    knowledge.sync(s.owner,d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='results',document_names=['invoice.txt'],answer_kind='summary'))
    install_chat_models(monkeypatch)
    p=plan(s,d,text='Summarize saved fields from invoice.txt.',document_ids=[doc['id']])
    assert 'Sara Khan' in p['explanation'] and 'Aarav Krishnan' not in p['explanation'] and current.id in p['explanation']


def test_hybrid_reranker_receives_only_selected_dataset_and_document(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    other=upload(s,d)['documents'][0];foreign=dataset(s,'Foreign');foreign_doc=upload(s,foreign)['documents'][0]
    knowledge.sync(s.owner,d['id']);knowledge.sync(s.owner,foreign['id'])
    view=PublishedKnowledge(s.owner,d['id'],[doc['id']]);received=[]
    def rank(query,candidates,top_k):
        received.extend(candidates)
        assert all(r['dataset_id']==d['id'] and r['document_ids']==[doc['id']] for r in candidates)
        return candidates[:top_k]
    monkeypatch.setenv('AEGIS_RERANKER','local');monkeypatch.setattr(reranker,'rank',rank)
    result=assemble(view.search('invoice total',{'document_chunk'}))
    assert received and result and view.search_diagnostics['mode']=='hybrid' and view.search_diagnostics['reranker_enabled']
    assert all(r['document_ids']==[doc['id']] for r in result)
    assert other['id'] not in json.dumps(result) and foreign_doc['id'] not in json.dumps(result)
    s.owner='bob'
    with pytest.raises(Exception):PublishedKnowledge(s.owner,d['id'])


def test_semantic_skill_predicates_return_only_supported_profiles(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    routing.create('extraction',s.owner,'Sara',{'document_ids':[doc['id']],'result':{'full_name':'Sara Khan','skills':['React','Accessibility']}},parent=d['id'])
    routing.create('extraction',s.owner,'Aarav',{'document_ids':[doc['id']],'result':{'full_name':'Aarav Krishnan','skills':['React','Python']}},parent=d['id'])
    knowledge.sync(s.owner,d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='knowledge',knowledge_types=['extraction']))
    install_chat_models(monkeypatch)
    p=plan(s,d,text='Semantically find saved extracted profiles with React and Accessibility in their skills.')
    assert 'Sara Khan' in p['explanation'] and 'Aarav Krishnan' not in p['explanation']
    assert 'Accessibility' in p['explanation'] and 'could not validate' not in p['explanation']


@pytest.mark.parametrize('goal_request',['can you extract','Extract and summarize the owner.'])
def test_completed_extraction_cannot_claim_missing_values_are_complete(system,monkeypatch,goal_request):
    from test_agent_goals import completed_plan,goal
    from ags_app import main,agent_goals
    record,ex,_=completed_plan(system)
    value=core.store.json(ex.ref);value['result']['phone']=None;routing.write_version(ex,value)
    data=core.store.json(record.ref);data['goal']['request']=goal_request;core.store.put_json(record.ref,data)
    def answer(*args,**kwargs):
        assert 'on_token' not in kwargs
        assert goal_request!='can you extract','Simple completion must render the saved fields directly.'
        return {'text':'All fields are present with no missing values. [1]','calls':[]}
    monkeypatch.setattr(agent_model,'classify',forbidden);monkeypatch.setattr(agent_model,'complete',answer)
    agent_goals.advance(record,main)
    result=goal(record)
    assert result['status']=='completed'
    assert 'Not extracted' in result['answer']['text'] and 'no missing values' not in result['answer']['text']


def test_exported_conversation_one_round(system,monkeypatch):
    path=os.getenv('AEGIS_CONVERSATION_REPLAY_FILE')
    if not path:pytest.skip('Set the local conversation export path to replay actual user requests.')
    exported=json.loads(Path(path).read_text(encoding='utf-8-sig'));messages=exported['messages']
    s=system;d=dataset(s,'Conversation replay');foreign=dataset(s,'Excluded dataset')
    docs=messages[7]['tool_trace'][0]['result']['records'];doc_ids={}
    for item in docs:
        record=routing.create('document',s.owner,item['data']['filename'],{},parent=d['id'])
        doc_ids[item['id']]=record.id
    routing.create('document',s.owner,'FOREIGN_SENTINEL.pdf',{},parent=foreign['id'])
    prompt=messages[13]['tool_trace'][0]['result']['records'][0]
    template=routing.create('template',s.owner,prompt['title'],{'schema':prompt['data']['schema'],
        'instructions':prompt['data']['instructions'],'source_filename':prompt['title']},parent=d['id'])
    first=messages[3];sara=first['tool_trace'][0]['result']['records'][0]['fields']
    old=sara|{'full_name':'Older Sara record'}
    earlier=routing.create('extraction',s.owner,'Earlier Sara',{'document_ids':[doc_ids[docs[0]['id']]],'result':old,'template_id':template.id},parent=d['id'])
    current=routing.create('extraction',s.owner,'sample extract',{'document_ids':[doc_ids[docs[0]['id']]],'result':sara,'template_id':template.id},parent=d['id'])
    aarav=messages[5]['tool_trace'][0]['result']['records'][1]['data']['fields']
    routing.create('extraction',s.owner,'Aarav result',{'document_ids':[doc_ids[docs[2]['id']]],'result':aarav},parent=d['id'])
    knowledge.sync(s.owner,d['id']);knowledge.sync(s.owner,foreign['id'])
    archived=routing.create('conversation',s.owner,'Replay',{'mode':'agent','dataset_id':d['id'],'messages':[
        {'role':'assistant','status':'completed','text':'OLD_CHAT_SENTINEL All values are present.',
         'citations':[{'document_id':doc_ids[docs[0]['id']]}], 'review_actions':[{'extraction_id':current.id}],
         'tool_trace':[{'tool':'read_extraction_results','result':{'records':[]}}]}]},parent=d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    original=agent_model.classify
    def route(inputs):
        assert 'OLD_CHAT_SENTINEL' not in json.dumps(inputs)
        question=inputs[-1]['content']
        if question==messages[6]['text']:
            return {'intent':'answer','source':'metadata','initial_reads':['list_documents'],'metadata_answer':'document_count','answer_kind':'count'}
        return original(inputs)
    monkeypatch.setattr(agent_model,'classify',route);install_chat_models(monkeypatch)
    results=[]
    for index in (4,6,8,10,12,14):
        question=messages[index]['text']
        response=plan(s,d,text=question,conversation_id=archived.id)
        answer=response['explanation'];results.append((question,answer))
        assert 'FOREIGN_SENTINEL' not in answer and not response['calls']
        if index==4:
            assert 'Sara Khan' in answer and 'Aarav Krishnan' not in answer and earlier.id not in answer
            assert 'Not extracted' in answer and 'no missing values' not in answer
        if index==6:assert '4 documents' in answer
        if index in (8,12):assert '1 prompt template' in answer and '4 documents' not in answer
        if index==10:assert prompt['title'] in answer and '.pdf' not in answer
        if index==14:
            assert 'Instructions:' in answer and 'Never guess absent values' in answer
            assert 'Extraction IDs:' not in answer and 'Fields:' in answer
    assert len(results)==6 and not s.api.get('/api/jobs').json()
