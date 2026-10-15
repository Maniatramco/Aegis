"""One typed file drives runtime limits, precedence and deployment reloads."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from ags_app import runtime_config,providers,extraction_retrieval,reranker,core
from ags_app.ags_agent import chat_agent,agent_context
from test_user_management import accounts,login
from test_dataset_models import system


@pytest.fixture(autouse=True)
def clean_runtime_environment(monkeypatch):
    monkeypatch.delenv('AEGIS_CONFIG_FILE',raising=False)
    monkeypatch.delenv('AEGIS_CONFIG_PROFILE',raising=False)
    _,settings,_=runtime_config._document(str(runtime_config.DEFAULT_FILE))
    for name in settings:monkeypatch.delenv(name,raising=False)


def use_file(tmp_path,monkeypatch,*replacements):
    text=runtime_config.DEFAULT_FILE.read_text(encoding='utf-8')
    for before,after in replacements:
        assert before in text;text=text.replace(before,after)
    path=tmp_path/'runtime.toml';path.write_text(text,encoding='utf-8')
    monkeypatch.setenv('AEGIS_CONFIG_FILE',str(path))
    return path


def test_file_profile_and_environment_precedence_preserve_model_clamps(monkeypatch):
    assert runtime_config.get('AEGIS_TIMEOUT')==60
    monkeypatch.setenv('AEGIS_CONFIG_PROFILE','oci')
    assert runtime_config.get('AEGIS_TIMEOUT')==1200
    assert runtime_config.get('AEGIS_RERANKER')=='local'
    monkeypatch.setenv('AEGIS_TIMEOUT','90')
    resolved=runtime_config.validate()
    assert resolved['values']['models']['AEGIS_TIMEOUT']==90
    assert resolved['environment_overrides']==['AEGIS_TIMEOUT']
    assert chat_agent.chat_limits({'context_limit':32768,'max_output_tokens':512})=={'context_tokens':32768,'output_tokens':512,'evidence_bytes':1000000}


@pytest.mark.parametrize('value',['abc','-1','1000001','true'])
def test_invalid_environment_evidence_budget_fails_closed(monkeypatch,value):
    monkeypatch.setenv('AEGIS_CHAT_EVIDENCE_BYTES',value)
    with pytest.raises(runtime_config.ConfigurationError,match='AEGIS_CHAT_EVIDENCE_BYTES'):runtime_config.get('AEGIS_CHAT_EVIDENCE_BYTES')


@pytest.mark.parametrize('replacement',[
    ('AEGIS_CHAT_CONTEXT_TOKENS = 262144','AEGIS_CHAT_CONTEXT_TOKENS = true'),
    ('AEGIS_CHAT_CONTEXT_TOKENS = 262144','AEGIS_CHAT_CONTEXT_TOKENS = 262145'),
    ('schema_version = 1','schema_version = 99'),
    ('[profiles.oci]','[profiles.oci]\nAEGIS_UNKNOWN_VALUE = 5'),
    ('[models]','[models]\nAEGIS_API_KEY = "DO-NOT-PRINT-THIS"'),
    ('AEGIS_OLLAMA_BATCH_SIZE = [1, 2048]','AEGIS_OLLAMA_BATCH_SIZE = [1]'),
])
def test_invalid_or_sensitive_files_are_rejected(tmp_path,monkeypatch,replacement):
    use_file(tmp_path,monkeypatch,replacement)
    with pytest.raises(runtime_config.ConfigurationError) as failure:runtime_config.validate()
    assert 'DO-NOT-PRINT-THIS' not in str(failure.value)


def test_missing_file_bad_toml_unknown_profile_and_cross_field_guards(tmp_path,monkeypatch):
    monkeypatch.setenv('AEGIS_CONFIG_FILE',str(tmp_path/'missing.toml'))
    with pytest.raises(runtime_config.ConfigurationError,match='Cannot read'):runtime_config.get('AEGIS_TIMEOUT')
    bad=tmp_path/'bad.toml';bad.write_text('[invalid');monkeypatch.setenv('AEGIS_CONFIG_FILE',str(bad))
    with pytest.raises(runtime_config.ConfigurationError,match='Cannot read'):runtime_config.validate()
    monkeypatch.delenv('AEGIS_CONFIG_FILE');monkeypatch.setenv('AEGIS_CONFIG_PROFILE','typo')
    with pytest.raises(runtime_config.ConfigurationError,match='Unknown'):runtime_config.validate()
    monkeypatch.delenv('AEGIS_CONFIG_PROFILE');monkeypatch.setenv('AEGIS_CHUNK_OVERLAP','1300')
    with pytest.raises(runtime_config.ConfigurationError,match='OVERLAP'):runtime_config.validate()
    monkeypatch.delenv('AEGIS_CHUNK_OVERLAP');monkeypatch.setenv('AEGIS_WORKER_LEASE_SECONDS','60');monkeypatch.setenv('AEGIS_WORKER_HEARTBEAT_SECONDS','40')
    with pytest.raises(runtime_config.ConfigurationError,match='heartbeat'):runtime_config.validate()


def test_extraction_retrieval_and_compact_quotes_follow_the_file(tmp_path,monkeypatch):
    use_file(tmp_path,monkeypatch,
        ('AEGIS_EXTRACTION_CHUNKS_PER_FIELD = 5','AEGIS_EXTRACTION_CHUNKS_PER_FIELD = 2'),
        ('AEGIS_EXTRACTION_NEIGHBOR_CHUNKS = 1','AEGIS_EXTRACTION_NEIGHBOR_CHUNKS = 0'),
        ('AEGIS_EXTRACTION_FULL_CONTEXT_CHARS = 12000','AEGIS_EXTRACTION_FULL_CONTEXT_CHARS = 1'),
        ('AEGIS_RERANK_CANDIDATES = 25','AEGIS_RERANK_CANDIDATES = 3'),
        ('AEGIS_COMPACT_EVIDENCE_ITEMS = 8','AEGIS_COMPACT_EVIDENCE_ITEMS = 2'),
        ('AEGIS_COMPACT_EVIDENCE_QUOTE_CHARS = 160','AEGIS_COMPACT_EVIDENCE_QUOTE_CHARS = 40'))
    sources=[{'id':str(n),'document_id':'doc','document_name':'test.txt','page':1,'text':'Synthetic evidence '+str(n)} for n in range(4)]
    seen=[]
    def retrieve(query,owner,documents,limit):
        seen.append(limit);return [{'chunk_id':c['id']} for c in sources[:limit]]
    monkeypatch.setattr(providers,'_retrieve',retrieve)
    selected,diagnostic=extraction_retrieval.retrieve({'type':'object','properties':{'amount':{'type':'number'}}},
        [SimpleNamespace(id='doc',owner='alice')],{'settings':{'model_provider':'mock','embedding_provider':'mock'}},sources)
    assert seen==[3] and [c['id'] for c in selected]==['0','1']
    assert diagnostic['context_expanded'] is False
    schema={'type':'object','properties':{str(n):{'type':'string'} for n in range(4)}}
    quotes=providers.evidence_schema(schema,True)['properties']['evidence']
    assert quotes['maxItems']==2 and quotes['items']['properties']['quote']['maxLength']==40


def test_shared_headroom_reaches_wire_budget_and_snapshots_omit_credentials(tmp_path,monkeypatch):
    use_file(tmp_path,monkeypatch,('AEGIS_CONTEXT_HEADROOM_TOKENS = 512','AEGIS_CONTEXT_HEADROOM_TOKENS = 1024'))
    monkeypatch.setenv('OPENAI_API_KEY','DO-NOT-PRINT-THIS')
    messages=[{'role':'user','content':'Synthetic complete evidence'}];audits=[]
    with agent_context.observe(audits.append):
        assert agent_context.fit(messages,{'context_limit':4096},512,lambda values:values,'answer')==messages
    assert audits[-1]['safety_tokens']==1024
    assert runtime_config.model_defaults()['headroom_tokens']==1024
    assert 'DO-NOT-PRINT-THIS' not in json.dumps(runtime_config.snapshot())


def test_admin_inspection_uses_live_file_and_is_not_exposed_to_other_users(accounts):
    login(accounts)
    response=accounts.get('/api/runtime-config');assert response.status_code==200,response.text
    assert response.json()['values']['chat']['AEGIS_CHAT_EVIDENCE_BYTES']==1000000
    defaults=accounts.get('/api/settings').json()['model_defaults']
    assert defaults['context_limit']==runtime_config.get('AEGIS_DEFAULT_MODEL_CONTEXT_TOKENS')
    assert defaults['max_output_tokens']==runtime_config.get('AEGIS_DEFAULT_MODEL_OUTPUT_TOKENS')
    login(accounts,'Colleague')
    assert accounts.get('/api/runtime-config').status_code==403


def test_deployment_plan_embeds_one_file_and_retires_duplicate_environment(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('runtime_deploy',root/'ags_deploy/ags_oke/ags_runtime_config.py')
    deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)
    path=use_file(tmp_path,monkeypatch)
    first=deploy.plan(path)
    assert first['configmap']['data']['runtime.toml']==path.read_text()
    assert first['environment_patch']['data']['AEGIS_CHAT_EVIDENCE_BYTES'] is None
    assert first['environment_patch']['data']['AEGIS_OCR_TIMEOUT'] is None
    assert 'AEGIS_MASTER_KEY' not in first['managed_keys']
    containers=first['deployment_patch']['spec']['template']['spec']['containers']
    assert [c['name'] for c in containers]==['api','worker']
    assert all(c['volumeMounts'][0]['readOnly'] for c in containers)
    path.write_text(path.read_text().replace('AEGIS_CHAT_OUTPUT_TOKENS = 1024','AEGIS_CHAT_OUTPUT_TOKENS = 2048'))
    second=deploy.plan(path)
    assert second['sha256']!=first['sha256']
    with pytest.raises(ValueError,match='digest'):deploy.plan(path,backend_image='backend:latest')
