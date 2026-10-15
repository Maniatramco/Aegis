"""Changing embeddings rebuilds knowledge before a separate, durable rerun."""
import pytest
from sqlalchemy import select
from ags_app import core, main, worker, providers, dataset_models as routing
from test_dataset_models import system, dataset, template, upload, model, mapping, post


def prepared(s, count=1):
    d=dataset(s);t=template(s)
    ids=[upload(s,d)['documents'][0]['id'] for _ in range(count)]
    old=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':ids,'template_id':t['id'],'display_name':'Previous reviewed run'})
    assert worker.run_once()
    # Reviewed results must remain immutable even when they are used as a rerun source.
    record=routing.owned(old['id'],s.owner,'extraction');saved=core.store.json(record.ref)
    saved['review_status']='reviewed';core.store.put_json(record.ref,saved)
    before=core.store.get(record.ref)
    emb=next(m for m in d['models'] if m['id']==d['embedding_model_id'])
    replacement=model(s,emb['connection_profile_id'],'Replacement embeddings',['embedding'])
    changed=mapping(s,d,mappings=d['mappings']+[{'model_id':replacement['id'],'enabled':True}],embedding_model_id=replacement['id'])
    body={'source_version':1,'template_id':t['id'],'display_name':'New run_2026-10-15_21-30-00','idempotency_key':'confirmed-rerun','allow_external':True}
    return changed|{'id':d['id']},t,ids,old,body,record.ref,before


def test_reindex_then_extract_survives_without_browser_and_preserves_review(system):
    s=system;d,t,ids,old,body,ref,before=prepared(s)
    original=core.store.get(routing.owned(ids[0],s.owner,'document').ref)
    path='/api/extractions/'+old['id']+'/rerun'
    accepted=post(s,path,body)
    assert [c['tool'] for c in accepted['calls']]==['upload','reextract']
    assert accepted['calls'][0]['title']=='Reindex selected documents'
    assert accepted['calls'][1]['status']=='pending'
    job_ids=accepted['calls'][0]['job_ids']
    assert len(job_ids)==1
    assert post(s,path,body)['calls'][0]['job_ids']==job_ids
    assert worker.run_once()  # Worker, without GET/polling, starts the extraction.
    with core.Session() as session:
        runs=list(session.scalars(select(core.Record).where(core.Record.kind=='extraction',core.Record.id!=old['id'])))
    assert len(runs)==1 and runs[0].name==body['display_name']
    assert worker.run_once()
    done=post(s,path,body)
    assert all(c['status']=='completed' for c in done['calls'])
    new=main.extraction(runs[0].id,s.owner)
    assert new['status']=='ready' and new['document_ids']==ids
    assert not s.api.get('/api/documents/'+ids[0]).json()['requires_reindex']
    assert core.store.get(ref)==before
    assert core.store.get(routing.owned(ids[0],s.owner,'document').ref)==original
    assert post(s,path,body)['id']==accepted['id']


def test_rerun_idempotency_cannot_change_accepted_inputs(system):
    s=system;d,t,ids,old,body,ref,before=prepared(s)
    path='/api/extractions/'+old['id']+'/rerun';post(s,path,body)
    assert s.api.post(path,json=body|{'display_name':'Other'}).status_code==409
    assert len([j for j in s.api.get('/api/jobs').json() if j['status']=='queued'])==1


@pytest.mark.parametrize('problem',['owner','source_version','template_scope','pending_document','inactive_dataset'])
def test_invalid_reruns_submit_no_jobs(system,problem):
    s=system;d,t,ids,old,body,ref,before=prepared(s)
    if problem=='owner':s.owner='bob'
    if problem=='source_version':body['source_version']=2
    if problem=='template_scope':
        other=dataset(s,'Other')
        body['template_id']=post(s,'/api/templates',{'name':'Other prompt','dataset_id':other['id'],'schema':{'type':'object','properties':{},'additionalProperties':False}})['id']
    if problem=='pending_document':
        with core.Session.begin() as session:session.get(core.Record,ids[0]).status='processing'
    if problem=='inactive_dataset':
        record=routing.owned(d['id'],s.owner,'knowledge_base');saved=core.store.json(record.ref)
        saved['active']=False;core.store.put_json(record.ref,saved)
    with core.Session() as session:before_jobs=len(list(session.scalars(select(core.Job))))
    response=s.api.post('/api/extractions/'+old['id']+'/rerun',json=body)
    assert response.status_code in (400,404,409),response.text
    with core.Session() as session:assert len(list(session.scalars(select(core.Job))))==before_jobs
    assert core.store.get(ref)==before


def test_external_embedding_consent_is_checked_before_any_submission(system,monkeypatch):
    from fastapi import HTTPException
    s=system;d,t,ids,old,body,ref,before=prepared(s)
    seen=[]
    def consent(allowed,embedding=False,cfg=None):
        seen.append(embedding)
        if embedding and not allowed:raise HTTPException(400,'Confirm external embedding processing')
    monkeypatch.setattr(main,'external_check',consent)
    response=s.api.post('/api/extractions/'+old['id']+'/rerun',json=body|{'allow_external':False})
    assert response.status_code==400 and seen==[False,True]
    assert not [j for j in s.api.get('/api/jobs').json() if j['status'] in ('queued','running')]
    assert not routing.rows(s.owner,'agent_plan')


def test_failed_reindex_never_starts_extraction(system,monkeypatch):
    s=system;d,t,ids,old,body,ref,before=prepared(s)
    accepted=post(s,'/api/extractions/'+old['id']+'/rerun',body)
    monkeypatch.setattr(providers,'embed',lambda *args,**kwargs:(_ for _ in ()).throw(providers.ProviderError('Embedding provider quota exceeded')))
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+accepted['id']).json()
    assert done['calls'][0]['status']=='failed' and not done['auto_continue']
    assert done['calls'][1]['status']=='pending'
    assert [e['id'] for e in s.api.get('/api/extractions').json()]==[old['id']]
    assert core.store.get(ref)==before


def test_multi_source_scope_reindexes_only_stale_sources(system):
    s=system;d,t,ids,old,body,ref,before=prepared(s,2)
    post(s,'/api/documents/'+ids[0]+'/reindex',{'allow_external':True});assert worker.run_once()
    accepted=post(s,'/api/extractions/'+old['id']+'/rerun',body)
    assert accepted['calls'][0]['document_ids']==ids[1:]
    assert accepted['calls'][0]['uploaded_document_ids']==ids
    assert worker.run_once() and worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+accepted['id']).json()
    result_id=done['calls'][1]['result']['extraction_id']
    assert main.extraction(result_id,s.owner)['document_ids']==ids
    assert core.store.get(ref)==before


def test_prefilled_name_reaches_independent_upload_extractions(system):
    from test_agent_workspace import plan
    s=system;d=dataset(s);t=template(s)
    proposal=plan(s,d,text='extract',attached_filenames=['a.txt','b.txt'],template_id=t['id'])
    response=s.api.post('/api/agent-v2/plans/'+proposal['id']+'/calls/0/upload',
        data={'confirmed':'true','dataset_id':d['id'],'template_id':t['id'],'continue_extraction':'true',
              'extraction_mode':'independent','display_name':'My extraction_2026-10-15_21-30-00'},
        files=[('files',('a.txt',b'Alice invoice 42','text/plain')),('files',('b.txt',b'Bob invoice 21','text/plain'))])
    assert response.status_code==200,response.text
    accepted=s.api.get('/api/extractions').json()
    assert len(accepted)==2
    assert all(item['name']=='My extraction_2026-10-15_21-30-00' for item in accepted)
