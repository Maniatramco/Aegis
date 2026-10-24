"""Real admin auth, current mappings and end-to-end scoped cleanup."""
from sqlalchemy import select
from ags_app import core, worker, document_storage, knowledge
from test_dataset_models import system, dataset, upload, template, post, mapping, model
from test_user_management import accounts, login

def setup(accounts,system):
    login(accounts);d=dataset(system);return system,d

def extraction(s,d,ids):
    result=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':ids,'template_id':template(s)['id'],'allow_external':True})
    assert worker.run_once()
    assert s.api.get('/api/extractions/'+result['id']).json()['status']=='ready'
    return result

def remove(s,doc):
    preview=s.api.get('/api/admin/documents/'+doc['id']+'/deletion-preview')
    token=preview.json().get('impact_token','0'*64)
    return s.api.request('DELETE','/api/admin/documents/'+doc['id'],json={'confirmation':doc['name'],'expected_version':doc['version'],'expected_impact':token})

def test_admin_auth_is_required_for_every_operation(accounts,system):
    s,d=setup(accounts,system);doc=upload(s,d)['documents'][0]
    login(accounts,'Colleague')
    for result in (accounts.get('/api/admin/documents'),accounts.get('/api/admin/documents/'+doc['id']+'/deletion-preview'),
                   accounts.post('/api/admin/documents/'+doc['id']+'/retry',json={'allow_external':True}),remove(s,doc)):
        assert result.status_code==403
    assert core.store.get('documents/'+doc['id']+'/original')

def test_listing_tracks_status_and_current_model_retry(accounts,system):
    s,d=setup(accounts,system);doc=upload(s,d)['documents'][0];result=extraction(s,d,[doc['id']])
    row=s.api.get('/api/admin/documents?search=invoice').json()['items'][0]
    assert row['storage']['status']=='present' and row['index_job']['status']=='completed'
    assert row['extractions'][0]['id']==result['id'] and row['extractions'][0]['status']=='ready'
    assert row['requires_reindex'] is False
    emb=next(m for m in d['models'] if m['id']==d['embedding_model_id'])
    replacement=model(s,emb['connection_profile_id'],'Current embeddings',['embedding'])
    mapping(s,d,mappings=d['mappings']+[{'model_id':replacement['id'],'enabled':True}],embedding_model_id=replacement['id'])
    job=post(s,'/api/admin/documents/'+doc['id']+'/retry',{'allow_external':True})
    assert core.store.json('jobs/'+job['id']+'.json')['execution']['model_id']==replacement['id']
    assert worker.run_once()
    assert s.api.get('/api/admin/documents').json()['items'][0]['requires_reindex'] is False
    assert s.api.get('/api/admin/documents?search=absent').json()['total']==0

def test_end_to_end_cleanup_is_scoped_to_document(accounts,system):
    s,d=setup(accounts,system);doc=upload(s,d)['documents'][0];other=upload(s,d)['documents'][0]
    result=extraction(s,d,[doc['id']]);unrelated=extraction(s,d,[other['id']])
    thread=post(s,'/api/conversations',{'dataset_id':d['id'],'document_ids':[doc['id']]})
    core.store.put_json('documents/'+doc['id']+'/ocr/cached-page.json',{'text':'private OCR'})
    core.store.put_json('documents/'+doc['id']+'/versions/v1/unknown-derived.json',{'private':'prior text'})
    core.store.put('documents/'+doc['id']+'/merged-sources/1/original',b'synthetic original')
    core.store.put_json('agent-state/'+thread['id']+'/checkpoints.json',{'private':'conversation'})
    core.local_store.put_json('object-cache/legacy.json',{'state':'valid','payload':'old scoped OCR payload'})
    core.local_store.put_json('object-cache/uncertain.json',{'state':'pending','expected_sha256':'hash-only'})
    knowledge.sync('administrator',d['id'])
    preview=s.api.get('/api/admin/documents/'+doc['id']+'/deletion-preview').json()
    assert preview['affected']['extractions']==preview['affected']['conversations']==1
    response=remove(s,doc);assert response.status_code==200,response.text
    assert not core.local_store.path('object-cache/legacy.json').exists()
    assert core.local_store.json('object-cache/uncertain.json')['state']=='pending'
    for prefix in ('documents/'+doc['id']+'/','extraction/'+result['id']+'/','conversation/'+thread['id']+'/','agent-state/'+thread['id']+'/'):
        assert document_storage.inventory([prefix])==[]
    assert s.api.get('/api/documents/'+doc['id']).status_code==404
    assert s.api.get('/api/extractions/'+result['id']).status_code==404
    assert s.api.get('/api/conversations/'+thread['id']).status_code==404
    assert s.api.get('/api/documents/'+other['id']).status_code==200
    assert s.api.get('/api/extractions/'+unrelated['id']).status_code==200
    with core.Session() as session:assert not session.scalar(select(core.Job).where(core.Job.target_id.in_([doc['id'],result['id']])))
    for path in core.local_store.path('knowledge/marker').parent.glob('*/manifest.json'):
        manifest=core.local_store.json(str(path.relative_to(core.DATA)).replace('\\','/'))
        assert doc['id'] not in manifest['entities'] and result['id'] not in manifest['entities']
        assert not any(doc['id'] in p.get('document_ids',[]) for p in manifest['points'].values())

def test_partial_cleanup_is_quarantined_and_resumes(accounts,system,monkeypatch):
    s,d=setup(accounts,system);doc=upload(s,d)['documents'][0];result=extraction(s,d,[doc['id']])
    workflow=core.Record(id=core.uid(),kind='agent_plan',owner='administrator',name='Synthetic workflow',parent_id=d['id'],status='workflow',ref='')
    workflow.ref='agent_plan/'+workflow.id+'/v1.json'
    core.store.put_json(workflow.ref,{'dataset_id':d['id'],'document_ids':[doc['id']],'calls':[{'status':'completed'}]})
    with core.Session.begin() as session:session.add(workflow)
    erase=document_storage.erase
    def partial(prefixes,keys):
        erase(prefixes,keys);raise OSError('Synthetic storage outage after file cleanup')
    monkeypatch.setattr(document_storage,'erase',partial)
    assert remove(s,doc).status_code==503
    assert s.api.get('/api/documents/'+doc['id']).status_code==404
    assert s.api.post('/api/admin/documents/'+doc['id']+'/retry',json={'allow_external':True}).status_code==409
    assert s.api.get('/api/admin/documents').json()['items'][0]['status']=='deleting'
    assert s.api.get('/api/admin/documents/'+doc['id']+'/deletion-preview').json()['cleanup_stage']=='files'
    monkeypatch.setattr(document_storage,'erase',erase)
    assert remove(s,doc).status_code==200
    assert s.api.get('/api/admin/documents').json()['total']==0

def test_confirmation_version_and_active_jobs_protect_files(accounts,system):
    s,d=setup(accounts,system);doc=upload(s,d,run=False)['documents'][0]
    assert remove(s,doc).status_code==409
    assert core.store.get('documents/'+doc['id']+'/original')
    assert worker.run_once()
    url='/api/admin/documents/'+doc['id']
    impact=s.api.get(url+'/deletion-preview').json()['impact_token']
    assert s.api.request('DELETE',url,json={'confirmation':'wrong','expected_version':1,'expected_impact':impact}).status_code==400
    assert s.api.request('DELETE',url,json={'confirmation':doc['name'],'expected_version':2,'expected_impact':impact}).status_code==409
    assert remove(s,doc).status_code==200

def test_shared_result_removal_preserves_other_original(accounts,system):
    s,d=setup(accounts,system);one=upload(s,d)['documents'][0];two=upload(s,d)['documents'][0]
    result=extraction(s,d,[one['id'],two['id']])
    assert remove(s,one).status_code==200
    assert s.api.get('/api/extractions/'+result['id']).status_code==404
    assert core.store.get('documents/'+two['id']+'/original')

def test_changed_impact_requires_a_new_confirmation_and_upload_replay_is_sanitized(accounts,system):
    s,d=setup(accounts,system)
    response=s.api.post('/api/documents/upload',files={'files':('receipt.txt',b'Synthetic receipt document','text/plain')},data={'dataset_id':d['id'],'allow_external':'true','idempotency_key':'synthetic-receipt'})
    assert response.status_code==200;doc=response.json()['documents'][0];assert worker.run_once()
    url='/api/admin/documents/'+doc['id'];preview=s.api.get(url+'/deletion-preview').json()
    extraction(s,d,[doc['id']])
    assert s.api.request('DELETE',url,json={'confirmation':doc['name'],'expected_version':1,'expected_impact':preview['impact_token']}).status_code==409
    chat=core.Record(id=core.uid(),kind='dataset_chat',owner='administrator',name='Dataset chat',parent_id='',ref='',status='ready')
    chat.ref='dataset_chat/'+chat.id+'/v1.json'
    core.store.put_json(chat.ref,{'dataset_ids':[d['id']],'document_ids':[doc['id']],'messages':[]})
    with core.Session.begin() as session:session.add(chat)
    assert remove(s,doc).status_code==200
    with core.Session() as session:assert session.get(core.Record,chat.id) is None
    receipts=[r for r in document_storage.routes() if r['key'].startswith('upload-receipts/')]
    assert len(receipts)==1 and core.store.json(receipts[0]['key']).get('deleted') is True
    assert doc['id'] not in str(core.store.json(receipts[0]['key']))

def test_pinned_oci_prefix_cleanup_erases_cached_and_unregistered_objects(system,monkeypatch):
    from ags_app import storage_config
    from ags_app.object_cache import CachedObjects
    class Bucket(storage_config.DirectoryStorage):
        def __init__(self):super().__init__(core.DATA/'synthetic-bucket')
        def require_permanent_delete(self):pass
    bucket=Bucket();monkeypatch.setattr(core,'oci_storage',lambda destination:bucket)
    cfg=core.DEFAULTS|{'storage_provider':'oci','oci_storage_bucket':'synthetic','oci_storage_namespace':'synthetic','oci_storage_region':'synthetic'}
    core.local_store.put_json('configuration/settings.json',cfg)
    prefix='documents/pinned/'
    core.store.put(prefix+'original',b'original');core.store.put_json(prefix+'ocr/page.json',{'text':'private'})
    destination=storage_config.route(prefix+'original')
    cache=CachedObjects(bucket,destination);assert cache.get(prefix+'ocr/page.json')
    bucket.put(prefix+'versions/v1/unregistered.bin',b'derived orphan')
    bucket.put('documents/unrelated/original',b'preserved')
    core.local_store.put_json('configuration/settings.json',core.DEFAULTS|{'storage_provider':'local'})
    assert document_storage.erase([prefix])==3
    assert bucket.list_prefix(prefix)==[]
    assert bucket.get('documents/unrelated/original')==b'preserved'
    assert not core.local_store.path(cache.ref(prefix+'ocr/page.json')[0]).exists()

def test_oci_inventory_pagination_is_prefix_scoped():
    from types import SimpleNamespace as S
    from ags_app.oci_adapters import OCIStorageAdapter
    calls=[]
    class Client:
        def list_objects(self,namespace,bucket,**kwargs):
            calls.append(kwargs);suffix='ocr/page.json' if kwargs.get('start') else 'original'
            return S(data=S(objects=[S(name='aegis/documents/one/'+suffix,size=10)],next_start_with=None if kwargs.get('start') else 'page2'))
    adapter=OCIStorageAdapter(Client(),'namespace','bucket','aegis')
    assert [v['key'] for v in adapter.list_prefix('documents/one/')]==['documents/one/original','documents/one/ocr/page.json']
    assert len(calls)==2 and calls[0]['prefix']=='aegis/documents/one/'
