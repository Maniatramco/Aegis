from pathlib import Path
import pytest
from types import SimpleNamespace
from app import core,main,storage_config as storage,workspace_reset as reset,dataset_access as access
from test_dataset_models import system,dataset,upload,template,post

def test_connection_status_uses_active_database_not_saved_draft(system):
    from app import database_control as db
    core.local_store.put_json(db.REF,{'active_provider':'local','draft':{'provider':'oci','name':'unsaved'}})
    value=system.api.get('/api/storage/status')
    assert value.status_code==200
    assert value.json()['database']=={'provider':'local','name':'Laptop','region':''}
    assert value.json()['knowledge']['provider']=='local'

def test_connection_status_reports_mixed_destinations_without_credentials(system):
    from app import database_control as db
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'local'})
    core.local_store.put_json(db.REF,{'active_provider':'oci','active_connection':{
        'name':'agsora','region':'ap-mumbai-1','username':'PRIVATE_USER','dsn':'PRIVATE_DSN',
        'secret_ref':'PRIVATE_SECRET','wallet_directory':'PRIVATE_WALLET'}})
    value=system.api.get('/api/storage/status')
    assert value.status_code==200
    data=value.json()
    assert data['files']['provider']=='local'
    assert data['database']=={'provider':'oci','name':'agsora','region':'ap-mumbai-1'}
    assert data['knowledge']=={'provider':'oci','name':'Oracle vectors'}
    assert 'PRIVATE' not in value.text

def test_storage_switch_keeps_old_objects_and_pins_new_objects(system,monkeypatch):
    s=system;objects={}
    class Cloud:
        def __init__(self,bucket):self.bucket=bucket
        def put(self,key,data):objects[self.bucket,key]=data
        def get(self,key):return objects[self.bucket,key]
        def delete(self,key):objects.pop((self.bucket,key),None)
    monkeypatch.setattr(core,'oci_storage',lambda cfg=None:Cloud(cfg['oci_storage_bucket']))
    core.store.put('documents/old/original',b'old-local')
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'oci','oci_storage_bucket':'one'})
    core.store.put('documents/new/original',b'cloud-one')
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'oci','oci_storage_bucket':'two'})
    core.store.put('documents/next/original',b'cloud-two')
    assert core.store.get('documents/old/original')==b'old-local'
    assert core.store.get('documents/new/original')==b'cloud-one'
    assert core.store.get('documents/next/original')==b'cloud-two'
    core.store.put('documents/new/original',b'cloud-one-update')
    assert objects['one','documents/new/original']==b'cloud-one-update'
    assert ('two','documents/new/original') not in objects
    core.store.put('documents/new/chunks.json',b'new-index')
    assert objects['one','documents/new/chunks.json']==b'new-index'

def test_older_per_object_routes_anchor_future_entity_files(system,monkeypatch):
    destination={'storage_provider':'oci','oci_storage_bucket':'original-bucket'}
    core.local_store.put_json(storage.route_ref('documents/existing/original'),{'destination':destination})
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'local'})
    assert storage.route('documents/existing/chunks.json',create=True)==destination
    assert storage.route('documents/existing/new-page.json')==destination

def test_legacy_local_and_control_objects_remain_local(system,monkeypatch):
    core.local_store.put('documents/legacy/original',b'legacy')
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'oci'})
    monkeypatch.setattr(core,'oci_storage',lambda cfg=None:pytest.fail('Control files cannot be sent to OCI'))
    assert core.store.get('documents/legacy/original')==b'legacy'
    with pytest.raises(FileNotFoundError):core.store.get('documents/legacy/missing-index.json')
    for key in ('model/m/v1.json','configuration/x','secrets/x','diagnostics/x'):
        core.store.put(key,b'local');assert core.local_store.get(key)==b'local'

def test_local_directory_validation_and_safe_new_directory(system):
    s=system
    assert s.api.put('/api/storage',json={'local_storage_path':str(core.DATA.parent/'outside')}).status_code==400
    target=core.DATA/'new-local'
    result=s.api.put('/api/storage',json={'local_storage_path':str(target)});assert result.status_code==200,result.text
    core.store.put('documents/d/original',b'new-root')
    assert (target/'documents/d/original').read_bytes()==b'new-root'
    assert s.api.put('/api/storage',json={'local_storage_path':str(core.DATA)}).status_code==200
    assert core.store.get('documents/d/original')==b'new-root'

def test_oci_screen_checks_mounts_without_returning_private_contents(system,monkeypatch):
    s=system;folder=core.DATA/'oci';folder.mkdir()
    (folder/'config').write_text('[DEFAULT]\nregion=ap-mumbai-1')
    (folder/'key.pem').write_text('DO_NOT_RETURN_PRIVATE_KEY')
    monkeypatch.setattr(core,'oci_storage',lambda cfg=None:SimpleNamespace(test_connection=lambda:{'ok':True,'write_verified':False}))
    body={'storage_provider':'oci','oci_storage_namespace':'ns','oci_storage_bucket':'bucket','oci_storage_region':'ap-mumbai-1',
        'oci_storage_config_file':str(folder/'config'),'oci_storage_key_file':str(folder/'key.pem')}
    assert s.api.post('/api/storage/test',json=body).status_code==200
    response=s.api.put('/api/storage',json=body);assert response.status_code==200,response.text
    assert 'DO_NOT_RETURN' not in s.api.get('/api/storage').text
    body['oci_storage_key_file']=str(core.DATA.parent/'secret')
    assert s.api.post('/api/storage/test',json=body).status_code==400

def test_regular_users_cannot_configure_or_reset_storage(system):
    s=system
    with core.Session.begin() as session:session.add(core.User(id='bob',username='bob',password_hash='not-used',role='user'))
    s.owner='bob'
    async def authenticated():
        access.request_actor.set('bob');return 'bob'
    main.app.dependency_overrides[main.auth]=authenticated
    try:
        assert s.api.get('/api/storage').status_code==403
        assert s.api.put('/api/storage',json={}).status_code==403
        assert s.api.get('/api/workspace/reset-preview').status_code==403
        assert s.api.post('/api/workspace/reset',json={'confirmation':'START FRESH'}).status_code==403
    finally:main.app.dependency_overrides[main.auth]=lambda:s.owner

def test_fresh_start_archives_and_restores_originals_catalog_jobs_and_grants(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];template(s)
    original=core.store.get('documents/'+doc['id']+'/original')
    core.store.put('agent-state/old-thread/checkpoints.json',b'{"checkpoints":{}}')
    core.store.put('executions/old-request.json',b'{"dataset":"old"}')
    assert s.api.post('/api/workspace/reset',json={'confirmation':'wrong'}).status_code==400
    response=s.api.post('/api/workspace/reset',json={'confirmation':'START FRESH'});assert response.status_code==200,response.text
    archive=response.json();assert archive['status']=='active_workspace_cleared'
    assert s.api.get('/api/datasets').json()==[] and s.api.get('/api/documents').json()==[]
    assert s.api.get('/api/jobs').json()==[] and s.api.get('/api/models').json()
    assert not (core.DATA/'documents').exists()
    assert not (core.DATA/'agent-state').exists() and not (core.DATA/'executions').exists()
    restored=s.api.post('/api/workspace/archives/'+archive['id']+'/restore',json={'confirmation':'RESTORE'})
    assert restored.status_code==200,restored.text
    assert core.store.get('documents/'+doc['id']+'/original')==original
    assert core.store.get('agent-state/old-thread/checkpoints.json')==b'{"checkpoints":{}}'
    assert s.api.get('/api/datasets/'+d['id']).status_code==200 and s.api.get('/api/jobs').json()

def test_reset_refuses_active_jobs_and_restore_refuses_nonempty_workspace(system):
    s=system;d=dataset(s);upload(s,d,run=False)
    assert s.api.post('/api/workspace/reset',json={'confirmation':'START FRESH'}).status_code==409
    assert s.api.post('/api/workspace/archives/00000000-0000-0000-0000-000000000001/restore',json={'confirmation':'RESTORE'}).status_code==409
    assert s.api.get('/api/documents').json()

def test_restore_detects_archive_tampering(system):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0]
    receipt=s.api.post('/api/workspace/reset',json={'confirmation':'START FRESH'}).json()
    path=core.DATA/'workspace-archives'/receipt['id']/'files/documents'/doc['id']/'original'
    path.write_bytes(b'changed')
    response=s.api.post('/api/workspace/archives/'+receipt['id']+'/restore',json={'confirmation':'RESTORE'})
    assert response.status_code==400 and s.api.get('/api/documents').json()==[]

def test_archive_includes_custom_local_directory_and_preserves_its_destination(system):
    s=system;root=core.DATA/'resumes'
    assert s.api.put('/api/storage',json={'local_storage_path':str(root)}).status_code==200
    d=dataset(s);doc=upload(s,d)['documents'][0]
    original=core.store.get('documents/'+doc['id']+'/original')
    receipt=s.api.post('/api/workspace/reset',json={'confirmation':'START FRESH'});assert receipt.status_code==200,receipt.text
    assert not (root/'documents').exists()
    assert s.api.put('/api/storage',json={'local_storage_path':str(core.DATA)}).status_code==200
    restored=s.api.post('/api/workspace/archives/'+receipt.json()['id']+'/restore',json={'confirmation':'RESTORE'})
    assert restored.status_code==200,restored.text
    assert core.store.get('documents/'+doc['id']+'/original')==original
