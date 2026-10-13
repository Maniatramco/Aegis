import hashlib
from ags_app import core, main, parquet_results
from test_dataset_models import system
from test_review_workflow import extracted
from test_user_management import accounts, login, OLD


def test_review_without_edits_is_final_and_all_mutation_paths_are_blocked(system):
    s=system;d,doc,e=extracted(s);url='/api/extractions/'+e['id']
    before=core.store.get('documents/'+doc['id']+'/original')
    result=s.api.patch(url,json={'version':e['version'],'result':e['result']})
    assert result.status_code==200,result.text
    saved=result.json();assert saved['review_locked'] and saved['review_status']=='reviewed'
    record=main.get_record(e['id'],s.owner,'extraction');reference=core.store.json(record.ref)['output_reference']
    digest=hashlib.sha256(core.store.get(reference)).hexdigest()
    for body in ({'version':saved['version'],'result':e['result']},{'version':saved['version'],'result':{'owner':'Overwrite'}}):
        assert s.api.patch(url,json=body).status_code==409
    assert s.api.post(url+'/reextract',json={'version':saved['version'],'confirm_reviewed':True}).status_code==409
    with core.Session.begin() as db:
        job=next(j for j in db.query(core.Job).all() if j.target_id==e['id']);job.status='failed';job_id=job.id
    assert s.api.post('/api/jobs/'+job_id+'/retry').status_code==409
    assert s.api.get(url).json()['version']==saved['version']
    assert hashlib.sha256(core.store.get(reference)).hexdigest()==digest
    assert core.store.get('documents/'+doc['id']+'/original')==before


def test_citation_evidence_uses_pinned_revision_and_enforces_scope(system):
    s=system;d,doc,e=extracted(s);url='/api/extractions/'+e['id']
    original=s.api.get(url+'/source-evidence',params={'version':1}).json()
    assert original['fields']==e['result'] and original['sources'][0]['document_name']==doc['name']
    assert original['sources'][0]['source_base']=='/documents/'+doc['id']
    assert s.api.patch(url,json={'version':1,'result':{'owner':'Reviewed Alice'}}).status_code==200
    assert s.api.get(url+'/source-evidence',params={'version':1}).json()['fields']==e['result']
    assert s.api.get(url+'/source-evidence',params={'version':2}).json()['fields']=={'owner':'Reviewed Alice'}
    assert s.api.get(url+'/source-evidence',params={'version':3}).status_code==404
    assert s.api.get(url+'/source-evidence',params={'record_index':99}).status_code==404
    assert s.api.get(url+'/source-evidence',params={'version':0}).status_code==422
    s.owner='bob';assert s.api.get(url+'/source-evidence').status_code==404


def test_evidence_never_invents_missing_page_or_field_quote(system):
    s=system;d,doc,e=extracted(s);record=main.get_record(e['id'],s.owner,'extraction')
    data=core.store.json(record.ref);data.update(sources=[],evidence=[]);core.store.put_json(record.ref,data)
    detail=s.api.get('/api/extractions/'+e['id']+'/source-evidence').json()
    assert detail['sources'][0]['page'] is None and not detail['sources'][0]['field_evidence']
    assert detail['sources'][0]['excerpt']==''


def test_chat_session_marker_is_stable_for_reload_and_changes_on_relogin(accounts):
    client=accounts;login(client)
    current=client.get('/api/auth/me').json();assert current['chat_session_id']
    assert current['chat_session_id']!=current['csrf_token']
    assert client.get('/api/auth/me').json()['chat_session_id']==current['chat_session_id']
    assert client.post('/api/auth/logout').status_code==200
    login(client)
    assert client.get('/api/auth/me').json()['chat_session_id']!=current['chat_session_id']


def test_multi_record_citation_excludes_other_documents_even_without_source_key(system):
    s=system;d,doc,e=extracted(s)
    other=main.new_record('document',s.owner,'Other original.txt',d['id'])
    record=main.get_record(e['id'],s.owner,'extraction');data=core.store.json(record.ref)
    data.update(document_ids=[doc['id'],other.id],merge={'sources':[{'key':'a','document_id':doc['id']},{'key':'b','document_id':other.id}]},
                result={'records':[{'source_key':'a','fields':{'owner':'Alice'}},{'source_key':'b','fields':{'owner':'Bob'}}]},evidence=[],
                sources=[{'document_id':other.id,'page':2,'text':'Bob only'}, {'document_id':doc['id'],'page':1,'text':'Alice only'}])
    data.update(parquet_results.persist(record.id,1,data));core.store.put_json(record.ref,data)
    detail=s.api.get('/api/extractions/'+e['id']+'/source-evidence',params={'record_index':0}).json()
    assert detail['fields']=={'owner':'Alice'}
    assert {source['document_id'] for source in detail['sources']}=={doc['id']}
    assert detail['sources'][0]['page']==1 and detail['sources'][0]['excerpt']=='Alice only'
