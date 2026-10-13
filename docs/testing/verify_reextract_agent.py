"""Read back the browser rerun from OCI Object Storage and native vectors."""
import json,hashlib
from pathlib import Path
from sqlalchemy import select
from qdrant_client.models import Filter,HasIdCondition
from app import core,dataset_access,knowledge,providers,parquet_results,storage_config,chat_knowledge

owner='administrator';dataset_id='36fe2487-eaa3-5132-a9bd-12fdb48bcc52'
baseline=json.loads(Path('/tmp/reextract-baseline.json').read_text(encoding='utf-8-sig'))
actor=dataset_access.request_actor.set(owner)
try:
    with core.Session() as session:
        candidates=list(session.scalars(select(core.Record).where(core.Record.kind=='agent_plan',
            core.Record.owner==owner,core.Record.parent_id==dataset_id,core.Record.status=='workflow').order_by(core.Record.created_at.desc()).limit(20)))
    plan=next(r for r in candidates if (lambda value:value.get('agent')=='reextract' and value['request'].startswith('Re-extract maya-rao-sample-resume.pdf'))(core.store.json(r.ref)))
    data=core.store.json(plan.ref);calls=data['calls']
    assert data['model_calls']==1 and len(calls)==1 and calls[0]['tool']=='reextract'
    assert calls[0]['status']==data['goal']['status']=='completed'
    assert data['goal']['answer']['request_route']['model_calls']==0
    receipt=calls[0]['vector_publication'];artifact=receipt['verified_artifacts'][0]
    updated_id=artifact['extraction_id'];assert updated_id!=baseline['old_extraction_id']
    extraction=dataset_access.get_record(updated_id,owner,'extraction');saved=core.store.json(extraction.ref)
    result=parquet_results.load(saved)['result']
    assert result['full_name']=='Maya Rao' and result['total_experience_years']==8
    assert 'B.Tech' in result['highest_qualification'] and 'Computer Science' in result['highest_qualification']
    assert all(skill in result['skills'] for skill in ('Python','SQL','Docker'))
    assert 'highest_qualification' not in baseline['old_result']
    prompt=dataset_access.get_record(saved['template_id'],owner,'template')
    import jsonschema
    jsonschema.validate(result,core.store.json(prompt.ref)['schema'])
    destination=storage_config.route(saved['output_reference'])
    assert destination['storage_provider']=='oci' and destination['oci_storage_bucket']=='mk-aegis'
    adapter=core.store.backend(saved['output_reference'])
    raw=adapter.get(saved['output_reference']);sha=hashlib.sha256(raw).hexdigest()
    assert sha==saved['output_sha256']==artifact['sha256']
    head=adapter.client.head_object(adapter.namespace,adapter.bucket,adapter.object_key(saved['output_reference']))
    assert int(head.headers['content-length'])==len(raw)
    assert head.headers.get('opc-meta-sha256')==sha
    document=dataset_access.get_record(baseline['document_id'],owner,'document')
    assert hashlib.sha256(core.store.get(document.ref)).hexdigest()==baseline['original_sha256']
    assert hashlib.sha256(core.store.get(baseline['old_parquet'])).hexdigest()==baseline['old_parquet_sha256']
    old=dataset_access.get_record(baseline['old_extraction_id'],owner,'extraction')
    assert old.version==baseline['old_version'] and old.status=='ready'
    snapshot=knowledge.embedding_snapshot(owner,dataset_id);assert snapshot['settings']['search_provider']=='oracle'
    expected=knowledge.record_sources(extraction);ids=[p['id'] for p in expected]
    with core.execution_context(snapshot):
        points,offset=providers.client().scroll(snapshot['knowledge_collection'],
            scroll_filter=Filter(must=[HasIdCondition(has_id=ids)]),limit=256,with_payload=True,with_vectors=True)
    assert offset is None and len(points)==len(expected)
    mapping={p['id']:p['payload'] for p in expected}
    for p in points:
        assert p.payload['content_digest']==mapping[str(p.id)]['content_digest']
        assert knowledge.digest({k:v for k,v in p.payload.items() if k!='content_digest'})==p.payload['content_digest']
        assert p.vector and any(v!=0 for v in p.vector)
    assembled=chat_knowledge.assemble([{'id':str(p.id),'payload':p.payload} for p in points])
    assert any(r['value'].get('fields',{}).get('highest_qualification')==result['highest_qualification'] for r in assembled)
    # The read-only Chat view sees the new native payload without file hydration.
    view=chat_knowledge.PublishedKnowledge(owner,dataset_id,[document.id])
    records=chat_knowledge.assemble(view.catalog(['extraction']))
    assert any(r['entity_id'].split(':')[0]==updated_id and r['value'].get('fields',{}).get('highest_qualification')==result['highest_qualification'] for r in records)
    with core.Session() as session:
        jobs=list(session.scalars(select(core.Job).where(core.Job.target_id==updated_id)))
    assert len(jobs)==1 and jobs[0].status=='completed'
    conversation=dataset_access.get_record(data['conversation_id'],owner,'conversation')
    messages=core.store.json(conversation.ref)['messages'];goal_id=plan.id+':0'
    assert sum(m.get('goal_id')==goal_id for m in messages)==1
    proof={'plan_id':plan.id,'conversation_id':conversation.id,'dataset_id':dataset_id,'agent':data['agent'],
        'model_calls_to_proposal':data['model_calls'],'finalization_model_calls':0,
        'proposal_seconds':round(data['agent_duration_ms']/1000,3),
        'confirmed_to_finished_seconds':round(data['goal']['finished_at']-calls[0]['started_at'],3),
        'publication_seconds':round(calls[0]['publication_duration_ms']/1000,3),
        'extraction_seconds':round(jobs[0].updated_at-jobs[0].created_at,3),
        'updated_extraction_id':updated_id,'previous_extraction_id':old.id,'prompt_id':prompt.id,
        'result':result,'parquet':{'provider':'oci','namespace':adapter.namespace,'bucket':adapter.bucket,
            'object_key':adapter.object_key(saved['output_reference']),'reference':saved['output_reference'],
            'bytes':len(raw),'sha256':sha,'head_verified':True},
        'vectors':{'provider':'oracle','table':'aegis_knowledge_vectors','collection':snapshot['knowledge_collection'],
            'updated_result_points':len(points),'embedding_dimensions':sorted({len(p.vector) for p in points}),
            'all_payload_digests_verified':True,'chat_view_sees_updated_field':True},
        'publication_receipt':receipt,'jobs_created':1,'original_unchanged':True,'old_parquet_unchanged':True,
        'completion_receipts':1,'schema_valid':True}
    print(json.dumps(proof,indent=2))
finally:dataset_access.request_actor.reset(actor)
