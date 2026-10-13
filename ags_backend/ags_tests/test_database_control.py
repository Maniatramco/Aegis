from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import create_engine,select
from fastapi import HTTPException
import pytest
from ags_app import core,main,database_control as db,oracle_vectors
from test_dataset_models import system,dataset,upload,template

def wallet():
    path=core.DATA/'oci/database/wallet';path.mkdir(parents=True,exist_ok=True)
    (path/'tnsnames.ora').write_text('agsora_low = (DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST=adb.example.oraclecloud.com)))')
    (path/'ewallet.pem').write_text('Encrypted fixture; never returned')
    return path

def body(**extra):return db.Connection(username='AEGIS',password='Private-db-test-password',wallet_password='Private-wallet-test-password',wallet_directory=str(wallet()),**extra)

def test_database_screen_preserves_active_provider_and_encrypts_saved_secrets(system,monkeypatch):
    monkeypatch.setattr(db,'candidate',lambda cfg:SimpleNamespace(dispose=lambda:None))
    monkeypatch.setattr(db,'probe',lambda engine:{'ok':True,'message':'Verified'})
    cfg=body();request=cfg.model_dump(mode='json');request.update(password=cfg.password.get_secret_value(),wallet_password=cfg.wallet_password.get_secret_value())
    assert system.api.post('/api/storage/database/test',json=request).status_code==200
    assert db.state()['active_provider']=='local' and not core.local_store.path(db.REF).exists()
    response=system.api.put('/api/storage/database',json=request);assert response.status_code==200,response.text
    current=system.api.get('/api/storage/database').json()
    assert current['active_provider']=='local' and current['password_saved'] and current['wallet_password_saved']
    stored=core.local_store.json(db.state()['draft']['secret_ref'])
    assert 'Private-db-test-password' not in str(stored) and 'Private-wallet-test-password' not in str(current)
    assert db.resolved(db.Connection(**current['form']))['_password']=='Private-db-test-password'
    changed=current['form']|{'dsn':'another_alias'}
    assert not db.resolved(db.Connection(**changed))['_password']

def test_saved_cloud_credentials_survive_selecting_local(system):
    cfg=db.resolved(body());db.save_draft(cfg)
    db.save_draft(cfg|{'provider':'local'})
    assert db.resolved(body())['_password']=='Private-db-test-password'
    assert db.public()['password_saved']

def test_wallet_validation_and_tls_identity_checks(system):
    cfg=db.resolved(body());params=db.parameters(cfg)
    assert params['dsn']=='agsora_low' and params['ssl_server_dn_match'] is True
    assert params['retry_count']==0 and params['wallet_location']==cfg['wallet_directory']
    for modified in (cfg|{'wallet_directory':str(core.DATA.parent)},cfg|{'dsn':'wrong_alias'},cfg|{'_wallet_password':''},cfg|{'_password':''}):
        with pytest.raises(ValueError):db.parameters(modified)
    with pytest.raises(ValueError):db.parameters(cfg|{'auth_mode':'tls','dsn':'tcp://other:1521/service'})
    assert db.parameters(cfg|{'auth_mode':'tls','dsn':'tcps://db.oraclecloud.com:1521/service'})['ssl_server_dn_match']

def test_local_only_deployment_blocks_oci_database_connections(system,monkeypatch):
    cfg=db.resolved(body());monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    with pytest.raises(ValueError,match='local-only'):db.parameters(cfg)

def test_database_admin_permissions_and_sanitized_provider_errors(system,monkeypatch):
    monkeypatch.setattr(db,'candidate',lambda cfg:(_ for _ in ()).throw(RuntimeError('Private password provider body')))
    cfg=body();request=cfg.model_dump(mode='json');request.update(password='Private-db-test-password',wallet_password='Private-wallet-test-password')
    failed=system.api.post('/api/storage/database/test',json=request)
    assert failed.status_code==400 and 'Private password provider body' not in failed.text
    with core.Session.begin() as session:session.add(core.User(id='bob',username='bob',password_hash='unused',role='user'))
    async def auth():
        from ags_app import dataset_access
        dataset_access.request_actor.set('bob');return 'bob'
    main.app.dependency_overrides[main.auth]=auth
    try:
        for path,method in [('/api/storage/database','GET'),('/api/storage/database','PUT'),('/api/storage/database/prepare','POST'),('/api/storage/database/activate','POST')]:
            assert system.api.request(method,path,json=request if method!='GET' else None).status_code==403
    finally:main.app.dependency_overrides[main.auth]=lambda:system.owner

def test_metadata_copy_preserves_all_rows_and_rejects_other_workspaces(system):
    with core.Session.begin() as session:
        if not session.get(core.User,'alice'):session.add(core.User(id='alice',username='alice',password_hash='fixture',role='administrator'))
    d=dataset(system);upload(system,d);template(system)
    target=create_engine('sqlite:///'+str(core.DATA/'other.db'))
    core.Base.metadata.create_all(target)
    counts=db.migrate_metadata(core.engine,target)
    assert counts[core.Record.__tablename__]>=4
    with target.begin() as connection:
        user=connection.execute(select(core.User.__table__)).mappings().first()
        connection.execute(core.User.__table__.insert().values(dict(user)|{'id':'other-user','username':'other-user','created_by':None,'updated_by':None}))
    with pytest.raises(ValueError,match='different Aegis workspace'):db.migrate_metadata(core.engine,target)
    with target.connect() as connection:assert connection.execute(select(core.User.id).where(core.User.id=='other-user')).first()
    target.dispose()

def test_active_jobs_block_database_activation_and_source_retained(system):
    d=dataset(system);upload(system,d,run=False)
    with pytest.raises(HTTPException) as error:db.no_jobs()
    assert error.value.status_code==409 and db.state()['active_provider']=='local'

def test_database_sessions_resolve_shared_active_engine_before_each_session(system,monkeypatch):
    target=create_engine('sqlite:///'+str(core.DATA/'route.db'))
    maker=core.DatabaseSessions(core.engine,expire_on_commit=False)
    monkeypatch.setattr(db,'active_engine',lambda:target)
    with maker() as session:assert session.get_bind() is target
    monkeypatch.setattr(db,'active_engine',lambda:core.engine)
    with maker.begin() as session:assert session.get_bind() is core.engine
    target.dispose()

def test_failed_vector_copy_never_activates_oci_or_clears_source(system,monkeypatch):
    dataset(system)
    target=create_engine('sqlite:///'+str(core.DATA/'destination.db'));core.Base.metadata.create_all(target)
    monkeypatch.setattr(db,'candidate',lambda cfg:target)
    monkeypatch.setattr(db,'probe',lambda engine:{'ok':True,'schema_ready':True})
    from ags_app import providers
    monkeypatch.setattr(providers,'client',lambda:(_ for _ in ()).throw(RuntimeError('Vector service unavailable')))
    with pytest.raises(RuntimeError):db.activate(db.resolved(body()))
    assert db.state()['active_provider']=='local'
    from ags_app.workspace_reset import paused
    assert not paused()
    with core.Session() as session:assert session.scalar(select(core.Record.id).where(core.Record.kind=='knowledge_base'))

def test_oracle_vector_filters_are_bound_and_scope_before_ranking():
    from qdrant_client.models import Filter,FieldCondition,MatchAny,MatchValue,HasIdCondition
    vectors=oracle_vectors.OracleVectors(SimpleNamespace())
    filter=Filter(must=[FieldCondition(key='owner',match=MatchValue(value="bob' OR 1=1")),FieldCondition(key='dataset_id',match=MatchAny(any=['d1','d2'])),HasIdCondition(has_id=['p1'])])
    sql,values=vectors.where('namespace',filter)
    assert "bob' OR 1=1" not in sql and "bob' OR 1=1" in values.values()
    assert 'owner_id IN' in sql and 'dataset_id IN' in sql and 'point_id IN' in sql
    empty,_=vectors.where('namespace',ids=[]);assert '1=0' in empty

def test_oracle_vector_queries_filter_namespace_dimensions_and_use_native_distance():
    from contextlib import contextmanager
    calls=[]
    class Cursor:
        def execute(self,sql,values):calls.append((sql,values))
        def fetchall(self):return [('point','{"entity_id":"allowed"}',0.1)]
    vectors=oracle_vectors.OracleVectors(SimpleNamespace())
    @contextmanager
    def cursor(write=False):yield Cursor()
    vectors.cursor=cursor
    hits=vectors.query_points('namespace',[1.,0.],limit=2)
    sql,values=calls[-1]
    assert 'VECTOR_DISTANCE' in sql and 'dimensions=:dimensions' in sql and "point_id<>'__collection__'" in sql
    assert values['dimensions']==2 and hits.points[0].score==pytest.approx(.9)

def test_vector_switch_copies_current_points_removes_stale_target_and_archives_it(system):
    from ags_app import providers
    def point(id):return SimpleNamespace(id=id,vector=[1.,0.],payload={'dataset_id':'dataset'})
    class Vectors:
        def __init__(self,ids):self.items={id:point(id) for id in ids}
        def get_collections(self):return SimpleNamespace(collections=[SimpleNamespace(name='aegis_test')])
        def collection_exists(self,name):return True
        def get_collection(self,name):return SimpleNamespace(points_count=len(self.items))
        def scroll(self,*args,**kwargs):return list(self.items.values()),None
        def upsert(self,name,points,wait=True):self.items.update({str(p.id):p for p in points})
        def delete(self,name,selector,wait=True):
            for id in selector.points:self.items.pop(str(id),None)
    a='00000000-0000-0000-0000-000000000001';b='00000000-0000-0000-0000-000000000002'
    old=Vectors([a]);target=Vectors([b])
    assert db.migrate_vectors(old,target)==1 and set(target.items)=={a}
    backups=list((core.DATA/'configuration/database-migrations').glob('vectors-*.json'))
    assert len(backups)==1 and b in backups[0].read_text()
