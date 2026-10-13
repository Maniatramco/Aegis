"""Production-default Chat Agent with actual indexing/API/graph boundaries."""
import json,copy
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import core,main,worker,knowledge,agent_model,providers,parquet_results,dataset_models as routing
from app.agent_tools import Tools
from app.chat_knowledge import PublishedKnowledge,assemble
from test_dataset_models import system,dataset,upload,template,post
from test_agent_workspace import plan

def prepared(s):
    d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once();knowledge.sync(s.owner,d['id'])
    return d,doc,t,ex

def activate(monkeypatch,frame):
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setattr(agent_model,'classify',lambda messages:dict(intent='answer',operation='none',**frame))

def forbid(*a,**kw):pytest.fail('Chat must use published vectors without canonical reads or index writes.')

def test_exact_filename_count_uses_no_query_embeddings_or_answer_model(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    activate(monkeypatch,dict(source='metadata',initial_reads=['list_documents'],metadata_answer='document_count',answer_kind='count'))
    for module,name in ((knowledge,'sync'),(knowledge,'hydrate'),(providers,'embed'),(agent_model,'complete'),(Tools,'snapshot'),(Tools,'list_documents')):monkeypatch.setattr(module,name,forbid)
    p=plan(s,d,text='How many documents are in this dataset?')
    assert p['agent']=='chat' and p['model_calls']==1 and '1 document' in p['explanation']
    thread=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)
    assert [x['tool'] for x in thread['messages'][-1]['tool_trace']]==['query_unified_knowledge']

def test_extracted_answer_only_reads_complete_vector_payloads_and_exposes_review(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    activate(monkeypatch,dict(source='results',fields=['owner']))
    expected=parquet_results.load(core.store.json(routing.owned(ex['id'],s.owner,'extraction').ref))['result']['owner']
    monkeypatch.setattr(knowledge,'sync',forbid);monkeypatch.setattr(knowledge,'hydrate',forbid)
    monkeypatch.setattr(parquet_results,'load',forbid);monkeypatch.setattr(Tools,'snapshot',forbid)
    seen=[]
    def answer(messages,tools,**kw):
        seen.append(messages);assert tools==[]
        assert expected in messages[-1]['content']
        return {'text':'The saved owner is '+expected+' [2].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    p=plan(s,d,text='What owner was extracted?',document_ids=[doc['id']])
    assert p['agent']=='chat' and p['model_calls']==2 and len(seen)==1
    m=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert m['review_actions'][0]['extraction_id']==ex['id']
    assert any(c.get('extraction_id')==ex['id'] for c in m['citations'])

def test_catalog_has_no_top_k_truncation(system,monkeypatch):
    s=system;d=dataset(s)
    for i in range(30):routing.create('document',s.owner,f'file-{i}.txt',{},parent=d['id'])
    knowledge.sync(s.owner,d['id'])
    activate(monkeypatch,dict(source='metadata',initial_reads=['list_documents'],answer_kind='list'))
    monkeypatch.setattr(providers,'embed',forbid);monkeypatch.setattr(agent_model,'complete',forbid)
    p=plan(s,d,text='List every filename and count them.')
    assert '30 indexed documents' in p['explanation'] and all(f'file-{i}.txt' in p['explanation'] for i in range(30))

def test_changed_revision_fails_closed_without_rebuilding_during_question(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    record=routing.owned(ex['id'],s.owner,'extraction');value=core.store.json(record.ref)
    value['result']={'owner':'Carol'};value.update(parquet_results.persist(record.id,record.version+1,value));routing.write_version(record,value)
    activate(monkeypatch,dict(source='results',fields=['owner']))
    monkeypatch.setattr(knowledge,'sync',forbid);monkeypatch.setattr(agent_model,'complete',forbid)
    p=plan(s,d,text='Show the saved owner.')
    assert 'Knowledge is updating' in p['explanation'] and 'Alice' not in p['explanation']

def test_unselected_results_never_enter_evidence(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s);other=upload(s,d)['documents'][0];knowledge.sync(s.owner,d['id'])
    activate(monkeypatch,dict(source='results'))
    monkeypatch.setattr(agent_model,'complete',forbid)
    p=plan(s,d,text='Show results.',document_ids=[other['id']])
    assert 'No published knowledge' in p['explanation'] and ex['id'] not in p['explanation']

def test_all_fragments_reassemble_without_losing_long_extracted_values():
    text=json.dumps({'fields':{'skills':['Python']*1200,'name':'Alice'}})
    points=list(knowledge.point('extraction','one:record:0','dataset','alice','Long result',text))
    assert len(points)>1 and assemble(points)[0]['value']==json.loads(text)
    with pytest.raises(HTTPException):assemble(points[:-1])

def test_remote_vector_payload_poisoning_is_rejected_without_canonical_hydration(system,monkeypatch):
    s=system;d=dataset(s);knowledge.sync(s.owner,d['id']);view=PublishedKnowledge(s.owner,d['id'])
    expected=[{'id':id,'payload':copy.deepcopy(p)} for id,p in view.manifest['points'].items() if p['source_type']=='dataset']
    expected[0]['payload']['text']='Invented facts'
    fake=SimpleNamespace(scroll=lambda *a,**kw:([SimpleNamespace(**p) for p in expected],None))
    view.snapshot['settings']['search_provider']='oracle';monkeypatch.setattr(providers,'client',lambda:fake);monkeypatch.setattr(knowledge,'hydrate',forbid)
    with pytest.raises(HTTPException,match='Knowledge verification failed'):view.catalog(['dataset'])

def test_deletion_and_access_changes_exclude_old_vectors(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];knowledge.sync(s.owner,d['id'])
    with core.Session.begin() as session:session.delete(session.get(core.Record,doc['id']))
    assert PublishedKnowledge(s.owner,d['id']).catalog(['document'])==[]
    s.owner='bob'
    with pytest.raises(HTTPException):PublishedKnowledge(s.owner,d['id'])

def test_archive_never_enters_routing_or_answer_and_chat_has_no_mutation_contracts(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    old=routing.create('conversation',s.owner,'Long chat',{'mode':'agent','dataset_id':d['id'],
        'messages':[{'id':core.uid(),'role':role,'text':'OLD_CHAT_SENTINEL '+('irrelevant history '*500),'status':'completed'}
            for _ in range(50) for role in ('user','assistant')]},parent=d['id'])
    activate(monkeypatch,dict(source='results',fields=['owner']))
    seen=[]
    def classify(messages):
        seen.extend(messages);return {'intent':'answer','source':'results','fields':['owner']}
    monkeypatch.setattr(agent_model,'classify',classify)
    def answer(messages,tools,**kw):
        seen.extend(messages);assert tools==[]
        return {'text':'Saved owner [2].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    p=plan(s,d,text='Show the saved owner.',conversation_id=old.id)
    assert 'OLD_CHAT_SENTINEL' not in json.dumps(seen) and p['model_calls']==2
    assert not p['calls']

def test_chat_refuses_an_unexpected_model_tool_call(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    activate(monkeypatch,dict(source='results'))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:{'text':'','calls':[{'name':'prepare_workflow','arguments':{'operation':'extract'}}]})
    before=s.api.get('/api/jobs').json()
    p=plan(s,d,text='Summarize saved fields.')
    assert 'unexpected tool call' in p['explanation'] and p['calls']==[]
    assert s.api.get('/api/jobs').json()==before

def test_exact_predicate_count_does_not_use_similarity_as_a_filter(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    value=parquet_results.load(core.store.json(routing.owned(ex['id'],s.owner,'extraction').ref))['result']['owner']
    activate(monkeypatch,dict(source='results',answer_kind='count',filters=[{'field':'owner','operator':'equals','value':value}]))
    monkeypatch.setattr(providers,'embed',forbid);monkeypatch.setattr(agent_model,'complete',forbid)
    p=plan(s,d,text='Count extracted owners with the exact specified value.')
    assert '1 indexed extracted records' in p['explanation']

def test_published_source_preview_does_not_hydrate_files_and_requires_access(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    view=PublishedKnowledge(s.owner,d['id']);record=assemble(view.catalog(['extraction']))[-1]
    monkeypatch.setattr(parquet_results,'load',forbid);monkeypatch.setattr(knowledge,'hydrate',forbid)
    url='/api/knowledge/published-sources/'+record['knowledge_id']+'?collection='+view.snapshot['knowledge_collection']+'&dataset_id='+d['id']
    response=s.api.get(url);assert response.status_code==200,response.text
    assert response.json()['text']==record['text']
    s.owner='bob';assert s.api.get(url).status_code==404

def test_small_selected_original_reads_indexed_chunks_without_embedding_switch(system,monkeypatch):
    s=system;d,doc,t,ex=prepared(s)
    activate(monkeypatch,dict(source='documents'))
    monkeypatch.setattr(providers,'embed',forbid);monkeypatch.setattr(providers,'search',forbid);monkeypatch.setattr(knowledge,'hydrate',forbid)
    def answer(messages,tools,**kw):
        assert tools==[] and 'Invoice total 42.' in messages[-1]['content']
        return {'text':'The original says invoice total 42 [1].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    p=plan(s,d,text='What amount is written in the selected original?',document_ids=[doc['id']])
    assert '42' in p['explanation'] and p['model_calls']==2

def test_global_model_catalog_does_not_claim_a_dataset_mapping(system,monkeypatch):
    s=system;d=dataset(s);knowledge.sync(s.owner,d['id'])
    activate(monkeypatch,dict(source='metadata',initial_reads=['get_model_configuration']))
    monkeypatch.setattr(providers,'embed',forbid);monkeypatch.setattr(agent_model,'complete',forbid)
    p=plan(s,d,text='List the registered models.',dataset_id='')
    assert 'indexed models' in p['explanation'] and '- Embedding:' not in p['explanation']
    assert p['agent']=='chat' and p['model_calls']==1

def test_named_updated_extraction_does_not_mix_earlier_results_for_the_same_document(system,monkeypatch):
    s=system;d,doc,t,old=prepared(s)
    updated=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id'],'display_name':'Updated invoice'})
    assert worker.run_once();knowledge.sync(s.owner,d['id'])
    activate(monkeypatch,dict(source='results',document_names=['Updated invoice'],fields=['owner']))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:{'text':'The updated owner [2].','calls':[]})
    p=plan(s,d,text='Show saved owner in Updated invoice.')
    message=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert {r['extraction_id'] for r in message['review_actions']}=={updated['id']}
    evidence=message['tool_trace'][0]['result']['records']
    assert all(r['id'].split(':')[0]==updated['id'] for r in evidence)

@pytest.mark.parametrize('scope_field',['extraction_name','document_names','source_names'])
def test_extraction_name_predicate_filters_vector_metadata_not_saved_field_values(system,monkeypatch,scope_field):
    s=system;d,doc,t,old=prepared(s)
    updated=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id'],'display_name':'Updated invoice'})
    assert worker.run_once();knowledge.sync(s.owner,d['id'])
    activate(monkeypatch,dict(source='results',fields=['owner_alias'],filters=[{'field':scope_field,'operator':'equals','value':'Updated invoice'}]))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:{'text':'The updated owner [2].','calls':[]})
    p=plan(s,d,text='Show saved owner in extraction named Updated invoice.')
    message=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    assert {r['extraction_id'] for r in message['review_actions']}=={updated['id']}
    assert all(r['id'].split(':')[0]==updated['id'] for r in message['tool_trace'][0]['result']['records'])

@pytest.mark.parametrize('arguments,source,operation,read',[
    ({'agent':'chat','query':'document_count'},'metadata','none','list_documents'),
    ({'agent':'chat','query':'documents'},'metadata','none','list_documents'),
    ({'agent':'chat','query':'models'},'metadata','none','get_model_configuration'),
    ({'agent':'chat','query':'semantic','source_types':['extraction']},'knowledge','none',None),
    ({'agent':'onboard_extract','operation':'onboard_dataset','dataset_name':'Hiring'},'action','onboard_dataset',None),
    ({'agent':'reextract','operation':'reextract'},'action','reextract',None)])
def test_single_agent_handoff_has_typed_vector_plan(system,monkeypatch,arguments,source,operation,read):
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true');seen=[]
    request={'document_count':'How many documents are in this dataset?','documents':'List the documents.','models':'Which models are mapped?','semantic':'Find matching extracted profiles.','onboard_dataset':'Create a new dataset named Hiring.','reextract':'Re-extract the saved file.'}[arguments.get('query') or arguments['operation']]
    arguments={**arguments,'request_evidence':request}
    def choose(messages,tools,cfg,**kw):
        seen.append(tools);return {'calls':[{'name':'route_aegis','arguments':arguments}]}
    monkeypatch.setattr(agent_model,'schema_decision',choose)
    with core.execution_context({'settings':dict(core.settings(),model_provider='ollama',model='qwen3:4b')}):
        frame=agent_model.classify([{'role':'user','content':request}])
    assert len(seen)==1 and frame['source']==source and frame['operation']==operation
    if read:assert read in frame['initial_reads']
    if arguments.get('query')=='document_count':assert frame['answer_kind']=='count' and frame['metadata_answer']=='document_count'
    if arguments.get('query')=='semantic':assert frame['knowledge_scope']=='selected_dataset'
