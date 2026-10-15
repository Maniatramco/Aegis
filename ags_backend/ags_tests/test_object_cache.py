"""Count actual backing operations, including failure and cross-client recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
import pytest
from ags_app import core, object_cache, storage_config, workflow, agent_workspace, dataset_models as routing
from test_dataset_models import system, dataset, upload


class Bucket:
    def __init__(self, values=None):
        self.values=dict(values or {});self.reads=0;self.writes=0
        self.fail_write=False
    def get(self,key):
        self.reads+=1;time.sleep(.001)
        if key not in self.values:raise FileNotFoundError(key)
        return self.values[key]
    def put(self,key,value):
        self.writes+=1;self.values[key]=value
        if self.fail_write:raise RuntimeError('Uncertain transmission')
    def delete(self,key):self.values.pop(key,None)


def cache(bucket, name='one'):
    return object_cache.CachedObjects(bucket,{'oci_storage_bucket':name})


def test_history_polling_reads_each_object_once_and_never_rewrites(system):
    keys=[f'jobs/job-{i}/workflow.json' for i in range(14)]
    bucket=Bucket({k:json.dumps({'status':'completed'}).encode() for k in keys})
    for _ in range(100):
        for key in keys:assert json.loads(cache(bucket).get(key))['status']=='completed'
    assert bucket.reads==14  # 1,400 uncached reads -> 14; no TTL re-polling.
    assert bucket.writes==0
    ref,_=cache(bucket).ref(keys[0])
    if __import__('os').name!='nt':assert core.local_store.path(ref).stat().st_mode & 0o777==0o600


def test_two_clients_share_updates_and_unchanged_puts_are_free(system):
    bucket=Bucket({'agent_plan/p/v1.json':b'{"status":"waiting"}'})
    api,worker=cache(bucket),cache(bucket)
    assert api.get('agent_plan/p/v1.json')==b'{"status":"waiting"}'
    worker.put('agent_plan/p/v1.json',b'{"status":"completed"}')
    for _ in range(10):
        assert api.get('agent_plan/p/v1.json')==b'{"status":"completed"}'
        worker.put('agent_plan/p/v1.json',b'{"status":"completed"}')
    assert (bucket.reads,bucket.writes)==(1,1)


def test_warm_cache_skips_client_creation_for_reads_and_unchanged_writes(system):
    key='agent_plan/lazy/v1.json';bucket=Bucket({key:b'one'});created=[]
    def factory():created.append(True);return bucket
    def client():return object_cache.CachedObjects(factory,{'oci_storage_bucket':'lazy'})
    assert client().get(key)==b'one' and len(created)==1
    for _ in range(20):
        assert client().get(key)==b'one'
        client().put(key,b'one')
    assert len(created)==1 and (bucket.reads,bucket.writes)==(1,0)
    client().put(key,b'two')
    assert client().get(key)==b'two'
    assert len(created)==2 and bucket.writes==1


def test_concurrent_cold_reads_coalesce_without_mixing_destinations(system):
    bucket=Bucket({'template/p/v1.json':b'one'})
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(lambda _:cache(bucket).get('template/p/v1.json'),range(20)))==[b'one']*20
    assert bucket.reads==1
    other=Bucket({'template/p/v1.json':b'two'})
    assert cache(other,'two').get('template/p/v1.json')==b'two'


def test_uncertain_write_forces_canonical_readback(system):
    key='agent_onboarding/p/v1.json';bucket=Bucket({key:b'old'})
    assert cache(bucket).get(key)==b'old'
    bucket.fail_write=True
    with pytest.raises(RuntimeError):cache(bucket).put(key,b'new')
    # Backend committed before the connection failed; never return cached old.
    assert cache(bucket).get(key)==b'new'
    assert bucket.reads==2


def test_late_commit_after_timeout_cannot_leave_cached_old_state(system,monkeypatch):
    key='agent_plan/p/v1.json';bucket=Bucket({key:b'old'});client=cache(bucket)
    assert client.get(key)==b'old'
    def timeout(*args):raise RuntimeError('Still in transit')
    monkeypatch.setattr(bucket,'put',timeout)
    with pytest.raises(RuntimeError):client.put(key,b'new')
    assert client.get(key)==b'old'
    bucket.values[key]=b'new'  # Simulate the timed-out operation committing later.
    assert client.get(key)==b'new' and bucket.reads==3


def test_corrupt_cache_refetches_and_eviction_is_bounded(system,monkeypatch):
    key='jobs/a/workflow.json';bucket=Bucket({key:b'correct'})
    client=cache(bucket);assert client.get(key)==b'correct'
    ref,_=client.ref(key);core.local_store.put_json(ref,{'state':'valid','payload':'eA==','sha256':'wrong'})
    assert client.get(key)==b'correct' and bucket.reads==2
    monkeypatch.setattr(object_cache,'MAX_ENTRIES',2)
    for i in range(5):client.put(f'jobs/{i}/workflow.json',b'{}')
    assert len(list(core.local_store.path('object-cache/marker').parent.glob('*.json')))<=2


def test_originals_parquet_and_large_objects_bypass_cache(system,monkeypatch):
    bucket=Bucket();monkeypatch.setattr(core,'oci_storage',lambda cfg:bucket)
    core.local_store.put_json('configuration/settings.json',{'storage_provider':'oci','oci_storage_bucket':'one'})
    for key in ('documents/d/original','extraction/e/results/v1.parquet'):
        core.store.put(key,b'bytes');assert core.store.get(key)==b'bytes';assert core.store.get(key)==b'bytes'
    assert bucket.reads==4
    monkeypatch.setattr(object_cache,'MAX_ENTRY_BYTES',4)
    client=cache(bucket);client.put('conversation/c/v1.json',b'too-large')
    assert client.get('conversation/c/v1.json')==b'too-large'
    assert client.get('conversation/c/v1.json')==b'too-large' and bucket.reads==6


def test_job_reference_polling_reads_only_requested_authorized_workflow(system,monkeypatch):
    first=upload(system,dataset(system,'First'),run=False)['jobs'][0]['id']
    second=upload(system,dataset(system,'Second'),run=False)['jobs'][0]['id']
    reads=[];original=workflow.read
    monkeypatch.setattr(workflow,'read',lambda id:(reads.append(id),original(id))[1])
    result=system.api.get('/api/jobs',params={'ids':first})
    assert result.status_code==200 and [j['id'] for j in result.json()]==[first]
    assert reads==[first] and second not in reads
    system.owner='bob';reads.clear()
    assert system.api.get('/api/jobs',params={'ids':first}).json()==[] and reads==[]


def test_unchanged_plan_reads_do_not_persist_and_completed_recovery_is_skipped(system,monkeypatch):
    data={'calls':[],'request':'status'}
    record=routing.create('agent_plan',system.owner,'Read only',data,status='query')
    writes=[];original=core.store.put_json
    monkeypatch.setattr(core.store,'put_json',lambda *a,**kw:(writes.append(a[0]),original(*a,**kw))[1])
    for _ in range(10):agent_workspace.plan_public(record,__import__('ags_app.main',fromlist=['main']))
    assert writes==[]
    routing.create('agent_plan',system.owner,'Finished',{'auto_continue':True,
        'calls':[{'tool':'extract','status':'completed'}],'goal':{'status':'completed'}},status='workflow')
    writes.clear()
    monkeypatch.setattr(agent_workspace,'plan_public',lambda *a:pytest.fail('Completed plan reconciled'))
    agent_workspace.advance_workflows()
    assert writes==[]


def test_live_job_progress_projection_does_not_write_plan_on_poll(system,monkeypatch):
    from ags_app import main
    d=dataset(system);accepted=upload(system,d,run=False);jid=accepted['jobs'][0]['id']
    record=routing.create('agent_plan',system.owner,'Progress',{'request':'Upload','calls':[
        {'tool':'upload','status':'waiting','job_ids':[jid],'result':accepted}]},parent=d['id'],status='workflow')
    writes=[];original=core.store.put_json
    monkeypatch.setattr(core.store,'put_json',lambda *a,**kw:(writes.append(a[0]),original(*a,**kw))[1])
    for i in range(10):
        monkeypatch.setattr(main,'job_repr',lambda j:{'id':j.id,'status':'running','progress':i})
        value=agent_workspace.plan_public(record,main)
        assert value['calls'][0]['jobs'][0]['progress']==i
    assert writes==[]
