"""Seed one labelled QA copy of the existing fictional, verified resume result."""
import copy,json,time
from app import core,main,parquet_results,dataset_access,relational
name='QA - Review finalization - 2026-10-13'
actor=dataset_access.request_actor.set('administrator');audit=relational.actor_override.set('administrator')
try:
    existing=next((r for r in main.records('administrator','extraction') if r.name==name),None)
    if existing:
        print(json.dumps({'id':existing.id,'dataset_id':existing.parent_id,'existing':True}))
    else:
        original=main.get_record('220d33d7-b58c-43eb-a22c-35de309acde8','administrator','extraction')
        data=copy.deepcopy(parquet_results.load(core.store.json(original.ref)))
        data.update(review_status='unreviewed',review_locked=False,edited_fields=[],original_evidence=[],
                    qa_fixture=True,qa_fixture_source_id=original.id)
        for key in ('reviewed_at','reviewed_by','reviewed_extraction_version','output_reference','output_sha256','output_format','review_revision','job_id'):
            data.pop(key,None)
        record=main.new_record('extraction','administrator',name,original.parent_id,data={'result':None,'template_id':data['template_id'],'document_ids':data['document_ids']},status='processing')
        data.update(parquet_results.persist(record.id,1,data));core.store.put_json(record.ref,data)
        with core.Session.begin() as db:
            saved=db.get(core.Record,record.id);saved.status='ready';saved.updated_at=time.time()
        print(json.dumps({'id':record.id,'dataset_id':original.parent_id,'template_id':data['template_id'],
                          'document_ids':data['document_ids'],'qa_fixture':True,'copied_verified_result':original.id}))
finally:
    dataset_access.request_actor.reset(actor);relational.actor_override.reset(audit)
