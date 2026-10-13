"""Read-only proof of OCI metadata, native vectors and canonical resume reads."""
import json
import hashlib
from collections import Counter
from sqlalchemy import select,inspect,func
from app import core,relational,database_control as db,providers,knowledge,dataset_access,parquet_results

assert db.state()['active_provider']=='oci' and core.settings()['search_provider']=='oracle'
engine=core.current_engine()
assert engine is not core.engine
expected=set(core.Base.metadata.tables)|{'aegis_knowledge_vectors'}
assert len(expected)==13 and expected<=set(inspect(engine).get_table_names())
with core.Session() as session:
    records=list(session.scalars(select(core.Record)))
counts=dict(Counter(r.kind for r in records))
assert all(counts.get(kind)==1 for kind in ('knowledge_base','document','template','extraction'))
dataset=next(r for r in records if r.kind=='knowledge_base');document=next(r for r in records if r.kind=='document')
extraction=next(r for r in records if r.kind=='extraction')
result=parquet_results.load(core.store.json(extraction.ref))
assert result['result']['full_name']=='Maya Rao' and result['result']['total_experience_years']==8
assert hashlib.sha256(core.store.get(document.ref)).hexdigest()=='cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85'
token=dataset_access.request_actor.set(dataset.owner)
try:
    found=knowledge.search('Maya Rao Python eight years experience',dataset.owner,dataset.id,source_types=['extraction'])
    assert any('Maya Rao' in m['text'] and 'Python' in m['text'] for m in found['matches'])
    with core.execution_context(__import__('app.dataset_models',fromlist=['embedding_snapshot']).embedding_snapshot(dataset)):
        original=providers.search('Blue Harbor Analytics data pipelines',dataset.owner,[document],3)
    assert original and any('Blue Harbor Analytics' in m['text'] for m in original)
finally:dataset_access.request_actor.reset(token)
vector_client=providers.client()
assert vector_client.__class__.__name__=='OracleVectors'
collections={c.name:vector_client.get_collection(c.name).points_count for c in vector_client.get_collections().collections}
assert len(collections)==2 and all(count>0 for count in collections.values())
with engine.connect() as connection:
    table_counts={t.name:connection.execute(select(func.count()).select_from(t)).scalar() for t in core.Base.metadata.tables.values()}
    vector_rows=connection.exec_driver_sql("SELECT source_type,COUNT(*) FROM aegis_knowledge_vectors WHERE point_id<>'__collection__' GROUP BY source_type").all()
proof={'database':'agsora','region':'ap-mumbai-1','connection_alias':'agsora_low','authentication':'mtls',
    'active_database':'oci','active_vector_provider':'oracle','schema_tables':sorted(expected),
    'table_counts':table_counts,'record_counts':counts,'collections':collections,'vector_source_types':dict(vector_rows),
    'dataset_id':dataset.id,'document_id':document.id,'extraction_id':extraction.id,
    'original_unchanged':True,'full_name':result['result']['full_name'],'experience_years':result['result']['total_experience_years'],
    'semantic_saved_result_matches':len(found['matches']),'semantic_original_matches':len(original)}
conversation=next((r for r in records if r.kind=='conversation'),None)
if conversation:
    replies=[m for m in core.store.json(conversation.ref)['messages'] if m.get('role')=='assistant']
    successful=[m for m in replies if m.get('citations') and 'Blue Harbor' in m.get('text','')]
    if successful:
        reply=successful[-1]
        proof['agent_source_answer']=reply['text']
        proof['agent_tools']=[o['tool'] for o in reply.get('tool_trace',[])]
        proof['agent_source_citations']=len(reply['citations'])
print(json.dumps(proof,indent=2))
