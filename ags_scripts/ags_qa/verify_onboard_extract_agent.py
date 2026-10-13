"""Read-only verification of the browser's fictional OCI onboarding run."""
import json
import hashlib
import time
from sqlalchemy import select
from ags_app import core, dataset_access, dataset_models, knowledge, providers, parquet_results, storage_config
from qdrant_client.models import Filter,HasIdCondition

with core.Session() as session:
    workflow=session.scalar(select(core.Record).where(core.Record.kind=='agent_onboarding',core.Record.name=='Resume Agent Verification').order_by(core.Record.created_at.desc()))
    assert workflow is not None
    plan=session.get(core.Record,core.store.json(workflow.ref)['plan_id'])
w=core.store.json(workflow.ref);p=core.store.json(plan.ref)
assert workflow.owner=='administrator' and w['agent']=='onboard_extract'
assert w['status']=='completed' and all(step['status']=='completed' for step in w['steps'])
assert p['agent']=='onboard_extract' and p['model_calls']==1
assert len(w['document_ids'])==len(w['extraction_ids'])==1
actor=dataset_access.request_actor.set(workflow.owner)
try:
    document=dataset_access.get_record(w['document_ids'][0],workflow.owner,'document')
    extraction=dataset_access.get_record(w['extraction_ids'][0],workflow.owner,'extraction')
    prompt=dataset_access.get_record(w['template_id'],workflow.owner,'template')
    assert document.status==extraction.status=='ready'
    original_hash=hashlib.sha256(core.store.get(document.ref)).hexdigest()
    assert original_hash=='cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85'
    saved=parquet_results.load(core.store.json(extraction.ref))
    assert saved['result']['full_name']=='Maya Rao' and saved['result']['total_experience_years']==8
    assert 'Python' in saved['result']['skills'] and len(saved['result']['work_experience'])==2
    import jsonschema
    jsonschema.validate(saved['result'],core.store.json(prompt.ref)['schema'])
    locations=[storage_config.route(ref) for ref in (document.ref,prompt.ref,extraction.ref,saved['output_reference'])]
    assert all(value['storage_provider']=='oci' and value['oci_storage_bucket']=='mk-aegis' for value in locations)
    snapshot=knowledge.embedding_snapshot(workflow.owner,w['dataset_id'])
    ids=[]
    for entity in w['vector_publication']['entity_ids']:
        ids.extend(point['id'] for point in knowledge.record_sources(dataset_access.get_record(entity,workflow.owner)))
    with core.execution_context(snapshot):
        count=providers.client().count(snapshot['knowledge_collection'],count_filter=Filter(must=[HasIdCondition(has_id=ids)]),exact=True).count
    assert count==w['vector_publication']['verified_vectors']==len(set(ids))
    assert snapshot['settings']['search_provider']=='oracle'
    search_started=time.perf_counter()
    found=knowledge.search('Maya Rao Python skills years experience',workflow.owner,w['dataset_id'],source_types=['extraction'])
    assert any('Maya Rao' in hit['text'] and 'Python' in hit['text'] for hit in found['matches'])
    search_seconds=round(time.perf_counter()-search_started,3)
    with core.Session() as session:
        jobs=list(session.scalars(select(core.Job).where(core.Job.target_id.in_(w['document_ids']+w['extraction_ids']))))
    assert len(jobs)==2 and all(job.status=='completed' for job in jobs)
    steps=[dict(label=s['label'],seconds=round(s['finished_at']-s['started_at'],3)) for s in w['steps']]
    answer=p.get('chat',{}) or {}
    proof={'workflow_id':workflow.id,'plan_id':plan.id,'dataset_id':w['dataset_id'],
        'document_ids':w['document_ids'],'extraction_ids':w['extraction_ids'],'prompt_id':prompt.id,
        'status':w['status'],'model_calls_to_proposal':p['model_calls'],'agent':p['agent'],
        'steps':steps,'confirmed_to_finished_seconds':round(w['steps'][-1]['finished_at']-w['confirmed_at'],3),
        'vectors':w['vector_publication'],'physical_vector_table':'aegis_knowledge_vectors',
        'files_provider':'oci','bucket':'mk-aegis','original_sha256':original_hash,
        'semantic_extraction_matches':len(found['matches']),'semantic_search_seconds':search_seconds,
        'schema_valid':True,'parquet_reference':saved['output_reference'],
        'result':saved['result'],'jobs_created':len(jobs),'jobs_completed':len(jobs)}
    print(json.dumps(proof,indent=2))
finally:dataset_access.request_actor.reset(actor)
