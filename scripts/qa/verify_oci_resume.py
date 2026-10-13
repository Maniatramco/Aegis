"""Read-only live proof for the single fictional resume onboarding."""
import json
import hashlib
from collections import Counter
from sqlalchemy import select
from app import core, storage_config, parquet_results, providers, knowledge, dataset_access

with core.Session() as session:
    records=list(session.scalars(select(core.Record)))
    jobs=list(session.scalars(select(core.Job)))
counts=dict(Counter(r.kind for r in records))
assert all(counts.get(kind)==1 for kind in ('knowledge_base','document','template','extraction','agent_onboarding'))
assert all(j.status=='completed' for j in jobs) and len(jobs)==2
dataset=next(r for r in records if r.kind=='knowledge_base')
document=next(r for r in records if r.kind=='document')
extraction=next(r for r in records if r.kind=='extraction')
prompt=next(r for r in records if r.kind=='template')
assert dataset.name=='Resume Extraction' and document.status==extraction.status=='ready'
original=core.store.get(document.ref)
original_hash=hashlib.sha256(original).hexdigest()
assert original_hash=='cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85'
saved=parquet_results.load(core.store.json(extraction.ref))
expected={
    'full_name':'Maya Rao','professional_title':'Senior Data Engineer',
    'email':'maya.rao@example.com','phone':'+1 202 555 0108','location':'Hyderabad, India',
    'total_experience_years':8,
    'skills':['Python','SQL','FastAPI','Docker','Apache Airflow','PostgreSQL','AWS','Git'],
    'work_experience':[
        {'company':'Blue Harbor Analytics','title':'Senior Data Engineer','start_date':'2021-07','end_date':None},
        {'company':'Cedar Systems','title':'Data Engineer','start_date':'2018-06','end_date':'2021-06'}],
    'education':[{'degree':'B.Tech in Computer Science','institution':'Sunrise Example Institute of Technology','graduation_year':2018}],
    'certifications':['AWS Certified Data Engineer - Associate | 2025']}
assert saved['result']==expected,(saved['result'],expected)
schema=core.store.json(prompt.ref)['schema']
import jsonschema
jsonschema.validate(saved['result'],schema)
paths=[document.ref,prompt.ref,extraction.ref,saved['output_reference']]
assert all(storage_config.route(p)['storage_provider']=='oci' for p in paths)
cloud=core.oci_storage(storage_config.route(document.ref))
objects=[];start=None
while True:
    page=cloud.client.list_objects(cloud.namespace,cloud.bucket,prefix=cloud.prefix+'/',start=start).data
    objects.extend(o.name for o in page.objects)
    start=page.next_start_with
    if not start:break
archive=core.local_store.json('workspace-archives/9933bdb7-be9e-4dd9-af85-ba1d2b3bc153/manifest.json')
old_ids={r['id'] for r in archive['records']}
assert not any(part in old_ids for name in objects for part in name.split('/'))
assert not any(name.split('/')[1] in ('secrets','configuration','model','models','diagnostics','workspace-archives') for name in objects)
assert not (core.DATA/'agent-state').exists() and not (core.DATA/'executions').exists()
conversation=next(r for r in records if r.kind=='conversation')
reply=[m for m in core.store.json(conversation.ref)['messages'] if m.get('role')=='assistant'][-1]
assert 'Maya Rao' in reply['text'] and '8' in reply['text'] and 'Python' in reply['text']
assert any(o['tool']=='read_extraction_results' for o in reply.get('tool_trace',[]))
token=dataset_access.request_actor.set(dataset.owner)
try:
    found=knowledge.search('Maya Rao Python skills eight years experience',dataset.owner,dataset.id,source_types=['extraction'])
    assert any('Maya Rao' in h['text'] and 'Python' in h['text'] for h in found['matches'])
finally:dataset_access.request_actor.reset(token)
collections=[c.name for c in providers.client().get_collections().collections if c.name.startswith('aegis_')]
assert len(collections)==2,collections
for name in collections:
    points,offset=providers.client().scroll(name,limit=100,with_payload=True,with_vectors=False)
    assert offset is None
    for p in points:
        payload=p.payload or {}
        assert payload.get('dataset_id','') not in old_ids
        assert payload.get('entity_id','') not in old_ids
proof={'dataset_id':dataset.id,'document_id':document.id,'prompt_id':prompt.id,'extraction_id':extraction.id,
    'active_counts':counts,'jobs':dict(Counter(j.status for j in jobs)),
    'original_sha256':original_hash,'original_unchanged':True,'result':saved['result'],
    'schema_valid':True,'expected_fields_equal':True,'parquet_reference':saved['output_reference'],
    'parquet_sha256':saved['output_sha256'],'oci_bucket':cloud.bucket,'oci_namespace':cloud.namespace,
    'oci_objects':objects,'old_objects_uploaded':False,'new_collections':collections,
    'semantic_result_matches':len(found['matches']),'archive_id':'9933bdb7-be9e-4dd9-af85-ba1d2b3bc153',
    'active_provider':storage_config.active()['storage_provider'],
    'agent_answer':reply['text'],'agent_tools':[o['tool'] for o in reply.get('tool_trace',[])]}
print(json.dumps(proof,indent=2))
