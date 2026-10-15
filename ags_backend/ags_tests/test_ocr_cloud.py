"""Cloud OCR preserves pinned credentials, external consent and page failure guards."""
import copy
import io
import json
import pytest
from PIL import Image
from ags_app import core, ocr, main, worker, dataset_models as routing, agent_consent
from ags_app.ags_models.connection import ModelConnection
from ags_app.ags_models.providers.ags_gcp import ocr as gemini_ocr
from test_dataset_models import system, dataset
from test_ocr import scan


def snapshot():
    cfg = core.DEFAULTS | {'model_provider':'registered', 'model':'gemini-3.5-flash-lite',
        'context_limit':32768, 'max_output_tokens':2048, 'extra_parameters':{'reasoning_effort':'minimal'},
        'model_connection':{'protocol':'openai-compatible','endpoint':'https://generativelanguage.googleapis.com/v1beta/openai','auth_mode':'api_key'}}
    return {'settings':cfg,'provider_model':cfg['model'],'model_id':'cloud-model','model_version':1,
        'connection_profile_id':'cloud-profile','connection_profile_version':3,'secret_refs':{'connection':'pinned/cloud.enc'}}


@pytest.fixture
def cloud(monkeypatch):
    pinned = snapshot()
    def credentials(provider):
        assert provider == 'connection'
        assert core._execution.get()['secret_refs']['connection'] == 'pinned/cloud.enc'
        return json.dumps({'api_key':'unit-test-credential'})
    monkeypatch.setattr(core, 'execution_secret', credentials)
    monkeypatch.setattr(ocr, 'call', lambda *a,**k:pytest.fail('Cloud OCR attempted local Ollama'))
    return pinned


def test_scan_uses_pinned_gemini_model_and_credentials_and_retains_provenance(cloud, monkeypatch):
    requests=[]
    def post(self, path, payload, headers=None):
        assert self.secret == {'api_key':'unit-test-credential'}
        requests.append((path,payload))
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':'Cloud invoice total USD 29.50','unreadable':False})}}]}
    monkeypatch.setattr(ModelConnection,'post',post)
    with core.execution_context({'settings':core.DEFAULTS,'ocr_execution':cloud}):
        pages=worker.parse_document('scan.pdf',scan('Cloud invoice'))
    assert pages[0]['text_origin']=='ocr' and '29.50' in pages[0]['text']
    meta=pages[0]['ocr']
    assert meta['provider']=='gemini' and meta['model']=='gemini-3.5-flash-lite'
    assert meta['digest_type']=='configuration' and meta['verified'] is False and meta['coordinates'] is None
    path,payload=requests[0]
    assert path=='/chat/completions' and payload['model']==cloud['provider_model']
    assert payload['max_completion_tokens']==2048 and payload['reasoning_effort']=='minimal'
    assert payload['response_format']['json_schema']['schema']==ocr.SCHEMA
    assert payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
    assert 'unit-test-credential' not in json.dumps(payload) and len(requests)==1
    assert ocr.summary(pages)['model']==cloud['provider_model']


@pytest.mark.parametrize('finish,content,reason',[
    ('length','{"text":"partial","unreadable":false}','incomplete'),
    ('content_filter',None,'incomplete'),
    ('stop','invalid JSON','invalid'),
    ('stop','{"text":"partial","unreadable":true}','unreadable'),
    ('stop','{"text":"","unreadable":false}','no text'),
    ('stop','{"text":"ok","unreadable":false,"extra":1}','invalid')])
def test_cloud_partial_refused_or_invalid_pages_are_never_accepted(cloud, monkeypatch, finish, content, reason):
    monkeypatch.setattr(ModelConnection,'post',lambda *a,**k:{'choices':[{'finish_reason':finish,'message':{'content':content}}]})
    image=io.BytesIO();Image.new('RGB',(240,160),'white').save(image,format='PNG')
    with core.execution_context({'settings':core.DEFAULTS,'ocr_execution':cloud}):
        with pytest.raises(ocr.OcrError,match=reason):ocr.transcribe(image.getvalue(),ocr.available())


def test_cloud_service_failure_does_not_leak_response_or_use_local_model(cloud, monkeypatch):
    def failure(*a,**k):raise RuntimeError('secret-provider-response')
    monkeypatch.setattr(ModelConnection,'post',failure)
    with core.execution_context({'settings':core.DEFAULTS,'ocr_execution':cloud}):
        with pytest.raises(ocr.OcrError,match='Gemini OCR request failed') as error:ocr.read_page(scan(),0,'')
    assert 'secret-provider-response' not in str(error.value)


def test_embedding_job_pins_dataset_extraction_registration_for_ocr(system, monkeypatch):
    s=system;item=dataset(s)
    record=routing.owned(item['id'],s.owner,'knowledge_base')
    real=routing.resolve_model
    cloud=snapshot()
    monkeypatch.setattr(routing,'resolve_model',lambda r,cap,id=None:copy.deepcopy(cloud) if cap=='extraction' else real(r,cap,id))
    pinned=routing.execution_snapshot(record,'embedding')
    assert pinned['ocr_execution']['connection_profile_version']==3
    assert pinned['settings']['ocr_provider']=='gemini'
    cloud['connection_profile_version']=4
    assert pinned['ocr_execution']['connection_profile_version']==3


def test_cloud_ocr_alone_requires_consent_even_with_local_embeddings():
    cfg=core.DEFAULTS|{'model_provider':'ollama','embedding_provider':'ollama','search_provider':'local','storage_provider':'local','ocr_provider':'gemini'}
    with pytest.raises(main.HTTPException) as error:main.external_check(False,True,cfg)
    assert error.value.status_code==409
    notices=agent_consent.notices({'settings':cfg},'embedding',main)
    assert any(n['title']=='Gemini OCR' and 'images' in n['description'] for n in notices)


def test_cloud_ocr_configuration_version_changes_cache_identity():
    first=snapshot();second=copy.deepcopy(first);second['connection_profile_version']+=1
    limits={'enabled':True,'context':8192,'output':3000,'timeout':60,'dpi':180,'batch':128}
    assert gemini_ocr.configure(first,limits)['digest']!=gemini_ocr.configure(second,limits)['digest']
