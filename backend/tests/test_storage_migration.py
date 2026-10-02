"""No cloud requests: migration safety and interruption contracts."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest

spec=importlib.util.spec_from_file_location('migration',Path(__file__).resolve().parents[2]/'scripts'/'migrate_storage.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class MemoryStorage:
    def __init__(self,values=None):self.values=dict(values or {})
    def get(self,key):
        if key not in self.values:raise FileNotFoundError(key)
        return self.values[key]
    def put(self,key,data):self.values[key]=data
    def put_json(self,key,value):self.put(key,m.json.dumps(value).encode())


@pytest.fixture
def fixture(tmp_path):
    raw={'documents/a/original':b'original','documents/a/chunks.json':b'[]','template/t/v1.json':b'{}','template/t/v2.json':b'{"new":true}','conversation/c/v1.json':b'{"messages":[]}','jobs/j.json':b'{}'}
    for key,value in raw.items():
        path=tmp_path/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    for key in ['configuration/settings.json','secrets/provider.enc','model-cache/weights','diagnostics/probe']:
        path=tmp_path/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'SECRET')
    cfg={'storage_provider':'local'}
    target={'provider':'oci','namespace':'namespace','bucket':'bucket','prefix':'aegis','region':'us-chicago-1','auth_mode':'config_file','profile':'DEFAULT'}
    source=MemoryStorage(raw)
    plan=m.create_plan(source,{'provider':'local'},target,tmp_path,cfg,['documents/a/original'])
    return tmp_path,source,plan,cfg


def test_plan_all_versions_no_secrets(fixture):
    _,source,plan,_=fixture
    assert {e['key'] for e in plan['objects']}==set(source.values)
    assert plan['object_count']==6
    assert 'SECRET' not in m.json.dumps(plan)
    assert plan['total_bytes']==sum(map(len,source.values.values()))


def test_copy_verify_idempotent_retains_source(fixture):
    _,source,plan,_=fixture;target=MemoryStorage()
    before=dict(source.values);m.copy_and_verify(plan,source,target)
    assert plan['phase']=='copied_verified';assert target.values==before;assert source.values==before
    m.copy_and_verify(plan,source,target);assert target.values==before


def test_conflicting_target_never_overwritten(fixture):
    _,source,plan,_=fixture;key=plan['objects'][0]['key'];target=MemoryStorage({key:b'OTHER'})
    with pytest.raises(ValueError,match='conflicting'):m.copy_and_verify(plan,source,target)
    assert target.get(key)==b'OTHER';assert plan['phase']=='planned'


def test_checksum_failure_not_marked_verified(fixture):
    _,source,plan,_=fixture
    class Corrupt(MemoryStorage):
        def put(self,key,data):super().put(key,b'corrupt')
    with pytest.raises(ValueError,match='checksum'):m.copy_and_verify(plan,source,Corrupt())
    assert plan['phase']=='planned'


def test_source_drift_rejected(fixture):
    root,source,plan,cfg=fixture;key=plan['objects'][0]['key'];source.values[key]=b'changed'
    with pytest.raises(ValueError,match='changed'):m.check_source(plan,source,root,cfg,[])


def test_settings_drift_rejected(fixture):
    root,source,plan,cfg=fixture
    with pytest.raises(ValueError,match='Settings changed'):m.check_source(plan,source,root,cfg|{'storage_provider':'oci'},[])


def test_missing_reference_rejected(fixture):
    root,source,_,cfg=fixture
    with pytest.raises(ValueError,match='missing database'):m.create_plan(source,{'provider':'local'},{'provider':'oci'},root,cfg,['documents/missing/original'])


def test_secret_or_traversal_manifest_rejected(fixture):
    _,source,plan,_=fixture
    for key in ['secrets/provider.enc','documents/../secrets','/documents/a']:
        plan['objects'][0]['key']=key
        with pytest.raises(ValueError):m.copy_and_verify(plan,source,MemoryStorage())


def test_activation_requires_verified_copy_preserves_secrets(fixture):
    _,source,plan,cfg=fixture;local=MemoryStorage({'secrets/provider.enc':b'private'})
    with pytest.raises(ValueError):m.activate_settings(plan,cfg,local)
    target=MemoryStorage();m.copy_and_verify(plan,source,target);m.verify_destination(plan,target)
    updated=m.activate_settings(plan,cfg,local)
    assert updated['storage_provider']=='oci';assert updated['oci_storage_bucket']=='bucket'
    assert local.get('secrets/provider.enc')==b'private'
    assert 'private' not in local.get('configuration/settings.json').decode()


def test_remote_listing_pagination_filters_secrets():
    client=Mock();client.list_objects.side_effect=[NS(data=NS(objects=[NS(name='aegis/documents/a/original'),NS(name='aegis/secrets/key')],next_start_with='next')),NS(data=NS(objects=[NS(name='aegis/template/t/v1.json')],next_start_with=None))]
    source=NS(client=client,namespace='n',bucket='b')
    result=m.source_keys(source,{'provider':'oci','prefix':'aegis'},Path('/unused'))
    assert result==['documents/a/original','template/t/v1.json']
    assert client.list_objects.call_args.kwargs['start']=='next'


def test_manifest_written_private_and_reload_validates(fixture,tmp_path):
    _,_,plan,_=fixture;path=tmp_path/'private-manifest.json'
    m.write_manifest(path,plan)
    assert path.stat().st_mode & 0o777==0o600
    assert m.validate_manifest(m.json.loads(path.read_text()))['object_count']==6


def test_symlinks_rejected(fixture):
    root,source,_,_=fixture;(root/'documents'/'unsafe').symlink_to(root/'secrets'/'provider.enc')
    with pytest.raises(ValueError,match='Symlink'):m.source_keys(source,{'provider':'local'},root)


def test_named_configuration_profile_does_not_block_migration(fixture):
    root,source,_,cfg=fixture
    profile_key='configuration/profiles/profile-id/v1.json'
    profile_path=root/profile_key;profile_path.parent.mkdir(parents=True,exist_ok=True)
    profile_bytes=b'{"settings":{"storage_provider":"local"}}'
    profile_path.write_bytes(profile_bytes)
    local=MemoryStorage({profile_key:profile_bytes,'secrets/provider.enc':b'private-key'})
    refs=m.content_references(['documents/a/original',profile_key,'secrets/provider.enc','diagnostics/probe',''])
    assert refs==['documents/a/original']
    destination={'provider':'oci','namespace':'n','bucket':'b','prefix':'p','region':'us-chicago-1','auth_mode':'config_file','profile':'DEFAULT'}
    plan=m.create_plan(source,{'provider':'local'},destination,root,cfg,refs)
    target=MemoryStorage();m.copy_and_verify(plan,source,target)
    m.check_source(plan,source,root,cfg,refs)
    m.activate_settings(plan,cfg,local)
    assert profile_key not in target.values
    assert not any(k.split('/')[0] in m.LOCAL_ONLY_ROOTS for k in target.values)
    assert profile_path.read_bytes()==profile_bytes
    assert local.get(profile_key)==profile_bytes
    assert local.get('secrets/provider.enc')==b'private-key'


def test_unknown_database_reference_root_fails_closed():
    with pytest.raises(ValueError,match='Unknown database reference root'):
        m.content_references(['new_document_type/x/content.json'])
    with pytest.raises(ValueError,match='Invalid storage key'):
        m.content_references(['configuration/../documents/original'])
