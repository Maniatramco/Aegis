import json
import pytest
from ags_app import core, main, knowledge, dataset_models as routing, agent_model, worker
from test_dataset_models import system, dataset, upload, template, post
from test_agent_workspace import plan


def query(s,d=None,**values):
    body={'text':'supplier invoices','limit':12}|({'dataset_id':d['id']} if d else {})|values
    response=s.api.post('/api/knowledge/search',json=body)
    assert response.status_code==200,response.text
    return response.json()


def test_unified_sources_are_real_versioned_and_do_not_index_chat_or_credentials(system):
    s=system;d=dataset(s,'Supplier invoice archive');doc=upload(s,d)['documents'][0];t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']});assert worker.run_once()
    record=routing.owned(d['id'],s.owner,'knowledge_base')
    content=core.store.json(record.ref);content.update(description='Annual supplier billing and money due',password='DO_NOT_INDEX_SECRET')
    routing.write_version(record,content)
    routing.create('conversation',s.owner,'Private discussion',{'messages':[{'text':'DO_NOT_INDEX_CHAT'}]},parent=d['id'])
    snapshot,receipt=knowledge.sync(s.owner,d['id'])
    manifest=core.local_store.json(knowledge._manifest_ref(snapshot));text=json.dumps(manifest)
    assert 'DO_NOT_INDEX_SECRET' not in text and 'DO_NOT_INDEX_CHAT' not in text
    assert {'dataset','document','document_chunk','extraction','prompt','model','application'}<={p['source_type'] for p in manifest['points'].values()}
    match=query(s,d,source_types=['dataset'])['matches'][0]
    assert match['entity_id']==d['id'] and 'Annual supplier' in match['text']
    source=s.api.get(match['source_url']);assert source.status_code==200 and source.json()['text']==match['text']
    assert all(len(p['text'].encode())<=knowledge.TEXT_BYTES for p in manifest['points'].values())


def test_scope_is_enforced_before_search_and_again_on_source_open(system):
    s=system;one=dataset(s,'One');first=upload(s,one)['documents'][0];two=dataset(s,'Two');second=upload(s,two)['documents'][0]
    matches=query(s,one,source_types=['document_chunk'])['matches'];assert matches and {m['document_id'] for m in matches}=={first['id']}
    assert s.api.post('/api/knowledge/search',json={'text':'x','dataset_id':one['id'],'document_ids':[second['id']]}).status_code==400
    source_url=matches[0]['source_url'];s.owner='bob'
    assert s.api.post('/api/knowledge/search',json={'text':'x','dataset_id':one['id']}).status_code==404
    assert s.api.get(source_url).status_code==404


def test_updates_delete_old_points_and_canonical_reads_reject_stale_or_poisoned_payload(system):
    s=system;d=dataset(s,'Old name');match=query(s,d,source_types=['dataset'])['matches'][0]
    payload=core.local_store.json(knowledge._manifest_ref(knowledge.embedding_snapshot(s.owner,d['id'])))['points'][match['knowledge_id']]
    forged=dict(payload,text='Invented facts');assert knowledge.hydrate(s.owner,match['knowledge_id'],forged)['text']==match['text']
    record=routing.owned(d['id'],s.owner,'knowledge_base');data=core.store.json(record.ref);data['description']='New description';routing.write_version(record,data)
    assert knowledge.hydrate(s.owner,match['knowledge_id'],payload) is None
    new=query(s,d,source_types=['dataset']);assert new['index']['removed']>=1 and new['matches'][0]['source_version']==match['source_version']+1
    assert s.api.get(match['source_url']).status_code==404
    with core.Session.begin() as session:session.delete(session.get(core.Record,d['id']))
    assert knowledge.hydrate(s.owner,new['matches'][0]['knowledge_id'],new['matches'][0]) is None


def test_extraction_index_follows_review_edits_and_preserves_document_filter(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':template(s)['id']});assert worker.run_once()
    first=query(s,d,source_types=['extraction']);assert any('fields' in m['text'] for m in first['matches'])
    record=routing.owned(ex['id'],s.owner,'extraction');data=core.store.json(record.ref)
    data['result']={'owner':'Carol'};data.pop('artifacts',None);data.pop('parquet',None)
    # Write a complete revision using the same canonical artifact contract.
    from ags_app import parquet_results
    data.update(parquet_results.persist(record.id,record.version+1,data))
    routing.write_version(record,data)
    second=query(s,d,source_types=['extraction']);assert any('Carol' in m['text'] for m in second['matches'])
    assert not any('Alice' in m['text'] for m in second['matches'])
    other=upload(s,d)['documents'][0]
    assert query(s,d,source_types=['extraction'],document_ids=[other['id']])['matches']==[]


def test_sync_is_idempotent_and_survives_new_process_state(system,monkeypatch):
    s=system;d=dataset(s);upload(s,d)
    first=query(s,d);second=query(s,d);assert second['index']['upserted']==0
    assert first['index']['points']==second['index']['points']
    assert knowledge.search('owner',s.owner,d['id'],source_types=['document_chunk'])['matches']


def test_semantic_graph_uses_unified_search_and_returns_provenance_without_mutations(system,monkeypatch):
    s=system;d=dataset(s,'Supplier billing');upload(s,d)
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='knowledge',knowledge_types=['dataset'],knowledge_scope='accessible_datasets'))
    seen=[]
    def complete(messages,tools,**kwargs):
        seen.append((messages,tools));return {'text':'Supplier billing is the relevant dataset [1].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    before=s.api.get('/api/jobs').json();p=plan(s,d,text='Find a dataset about bills from vendors')
    assert p['phase']=='answered' and p['calls']==[] and seen[0][1]==[]
    assert s.api.get('/api/jobs').json()==before
    conversation=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)
    message=conversation['messages'][-1]
    assert message['tool_trace'][0]['tool']=='search_knowledge'
    assert message['citations'][0]['kind']=='knowledge' and message['citations'][0]['dataset_id']==d['id']
    assert message['answer_workflow']['status']=='completed'


def test_bad_source_types_and_path_traversal_are_rejected(system):
    s=system;d=dataset(s)
    assert s.api.post('/api/knowledge/search',json={'text':'x','dataset_id':d['id'],'source_types':['credentials']}).status_code==400
    assert s.api.get('/api/knowledge/sources/x?collection=../../secrets').status_code==400


def test_result_filters_for_list_requests_cannot_loop_on_empty_skill_filter(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    ex=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']});assert worker.run_once()
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(source='results',answer_kind='list',fields=[],filters=[{'field':'owner','operator':'contains','value':''}]))
    monkeypatch.setattr(agent_model,'complete',lambda messages,tools,**kwargs:{'text':'Alice [1]','calls':[]})
    p=plan(s,d,text='List all owners');assert 'tool-step limit' not in p['explanation'] and p['phase']=='answered'
    trace=core.store.json(main.get_record(p['conversation_id'],s.owner,'conversation').ref)['messages'][-1]['tool_trace']
    assert next(o for o in trace if o['tool']=='read_extraction_results')['arguments']['filters']==[]
    read=next(o for o in trace if o['tool']=='read_extraction_results')
    assert read['arguments']['fields']==['owner']
    from ags_app import parquet_results
    saved=parquet_results.load(core.store.json(main.get_record(ex['id'],s.owner,'extraction').ref))
    assert read['result']['records'][0]['fields']=={'owner':saved['result']['owner']}
