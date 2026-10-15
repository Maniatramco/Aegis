import copy
import pytest
from ags_app import core, model_registry, dataset_models as routing, ollama_provider
from test_dataset_models import system, dataset, upload
from test_model_registration import body, register


def test_identical_local_registration_rejected_but_category_and_tuning_are_distinct(system):
    s=system;value=body(protocol='ollama',provider_model='qwen3:4b',context_limit=8192,max_output_tokens=1024)
    model=register(s,value)
    duplicate=s.api.post('/api/model-registrations',json=value|{'name':'Misleading duplicate'})
    assert duplicate.status_code==409 and model['name'] in duplicate.text
    assert len(s.api.get('/api/models').json())==1
    assert register(s,value|{'context_limit':16384,'name':'Different budget'})['context_limit']==16384
    assert register(s,value|{'category':'extraction','name':'Extraction role'})['capabilities']==['extraction']
    assert s.api.put('/api/model-registrations/'+model['id'],json=value|{'name':'Renamed Chat'}).status_code==200


def test_legacy_dataset_import_reuses_equivalent_registrations(system):
    s=system;first=dataset(s);second=dataset(s,'Second')
    assert len(s.api.get('/api/models').json())==2
    assert first['default_chat_model_id']==second['default_chat_model_id']
    assert first['embedding_model_id']==second['embedding_model_id']
    existing=next(m for m in first['models'] if m['capabilities']==['chat','extraction'])
    duplicate=s.api.post('/api/models',json={k:existing[k] for k in ('name','connection_profile_id','provider_model','capabilities','enabled')})
    assert duplicate.status_code==409
    assert len(s.api.get('/api/models').json())==2


def test_consolidation_preserves_old_versions_rebinds_roles_and_queues_indexes(system,monkeypatch):
    s=system
    with core.Session.begin() as db:
        db.add(core.User(id=s.owner,username='QA admin',password_hash='not-used',role='administrator'))
    d=dataset(s);doc=upload(s,d)['documents'][0];old=routing.dataset_config(routing.owned(d['id'],s.owner,'knowledge_base'))
    # The network-free fixture begins with mock indexing. Mark its connection
    # as local Ollama for consolidation; real indexing is covered separately.
    records=routing.rows(s.owner,'model')
    for model in records:
        md=routing.model_data(model);profile=routing.owned(md['connection_profile_id'],s.owner,'config_profile')
        cfg=core.local_store.json(profile.ref);cfg['settings'].update(model_provider='ollama',embedding_provider='ollama')
        core.local_store.put_json(profile.ref,cfg)
    cfg=dict(core.settings(),model_provider='ollama',embedding_provider='ollama')
    profile=routing.create('config_profile',s.owner,'Canonical connection',{'settings':cfg})
    canonical={}
    for role in ('embedding','chat','extraction'):
        original=next(m for m in records if role in routing.model_data(m)['capabilities'])
        md=routing.model_data(original)
        model=routing.create('model',s.owner,'Canonical '+role,md|{'capabilities':[role],'connection_profile_id':profile.id,'connection_profile_version':1})
        canonical[role]=model.id
    monkeypatch.setattr(ollama_provider,'model_digest',lambda _: 'synthetic-installed-digest')
    dry=model_registry.consolidate(canonical)
    assert dry['archived_count']==2 and dry['datasets_changed']==1 and dry['reindex_count']==1
    assert routing.dataset_config(routing.owned(d['id'],s.owner,'knowledge_base'))==old
    report=model_registry.consolidate(canonical,True)
    assert len(report['jobs'])==1 and len(s.api.get('/api/models').json())==3
    assert len(s.api.get('/api/models?include_archived=true').json())==5
    current=routing.owned(d['id'],s.owner,'knowledge_base');config=routing.dataset_config(current)
    assert config['default_chat_model_id']==canonical['chat'] and config['default_extraction_model_id']==canonical['extraction']
    assert config['embedding_model_id']==canonical['embedding'] and config['index_generation']==old['index_generation']+1
    assert core.local_store.json(report['report_ref'])['datasets'][0]['before']==old
    assert core.store.json('knowledge_base/'+d['id']+'/v'+str(current.version-1)+'.json')==old
    assert routing.resolve_model(current,'chat',old['default_chat_model_id'])['model_id']==canonical['chat']
    assert routing.resolve_model(current,'extraction',old['default_chat_model_id'])['model_id']==canonical['extraction']
    assert core.store.get('documents/'+doc['id']+'/original')
    for original in records:assert routing.model_data(original).get('archived') is None  # Old version reference still intact.
    queued=next(j for j in s.api.get('/api/jobs').json() if j['id']==report['jobs'][0])
    assert queued['status']=='queued' and queued['target_id']==doc['id']
    with pytest.raises(ValueError,match='active jobs'):model_registry.consolidate(canonical)
