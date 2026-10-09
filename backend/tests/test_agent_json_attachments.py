"""Real JSON ingestion, schema import, and extraction with isolated storage."""
import json
import pytest
from app import worker
from app.json_documents import json_document_text
from test_dataset_models import system, dataset, post, template, upload
from test_agent_workspace import planner, proposal, plan, send_files, call

def test_json_document_upload_retains_original_indexes_and_extracts(system, monkeypatch):
    s=system;d=dataset(s);t=template(s);planner(monkeypatch,proposal())
    raw=b'\xef\xbb\xbf'+json.dumps({'owner':'Alice','topic':'Kubernetes','total':42}).encode()
    p=plan(s,d,template_id=t['id'],attached_filenames=['data.json'])
    response=send_files(s,p,[('files',('data.json',raw,'application/json'))])
    assert response.status_code==200,response.text
    id=response.json()['calls'][0]['uploaded_document_ids'][0]
    assert s.api.get('/api/documents/'+id+'/download').content==raw
    assert s.api.get('/api/documents/'+id+'/source').headers['content-type']=='application/json'
    assert worker.run_once()
    assert s.api.get('/api/documents/'+id).json()['status']=='ready'
    assert 'Kubernetes' in s.api.get('/api/documents/'+id+'/preview').text
    response=call(s,p,1);assert response.status_code==200,response.text
    extraction=response.json()['calls'][1]['result']['extraction_id']
    assert s.api.get('/api/extractions/'+extraction).json()['template_id']==t['id']
    assert worker.run_once()
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'][1]['status']=='completed'

def test_invalid_json_rejects_entire_agent_batch_before_creating_documents(system, monkeypatch):
    s=system;d=dataset(s);planner(monkeypatch,proposal(('upload',)))
    p=plan(s,d,attached_filenames=['good.txt','broken.json'])
    response=send_files(s,p,[('files',('good.txt',b'Valid document text','text/plain')),('files',('broken.json',b'{broken','application/json'))])
    assert response.status_code==422,response.text
    assert 'Invalid JSON' in response.json()['detail']
    assert s.api.get('/api/documents').json()==[]
    assert s.api.get('/api/jobs').json()==[]
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'][0]['status']=='pending'

def test_prompt_validation_saves_a_template_without_creating_a_document(system, monkeypatch):
    s=system;d=dataset(s)
    payload={'name':'Uploaded prompt','dataset_id':d['id'],'schema':{'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}}
    assert post(s,'/api/templates/validate',payload)['valid']
    assert s.api.get('/api/templates').json()==[]
    saved=post(s,'/api/templates',payload)
    assert s.api.get('/api/documents').json()==[]
    assert s.api.get('/api/jobs').json()==[]
    doc=upload(s,d)['documents'][0];planner(monkeypatch,proposal(('extract',)))
    p=plan(s,d,template_id=saved['id'],document_ids=[doc['id']])
    assert call(s,p,0).status_code==200
    assert worker.run_once()
    assert s.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'][0]['status']=='completed'

@pytest.mark.parametrize('value',[{'topic':'Kubernetes'},[1,2,3],'text',42,None])
def test_json_document_can_be_an_object_array_or_scalar(value):
    assert json.loads(json_document_text(json.dumps(value).encode()))==value

@pytest.mark.parametrize('raw',[b'{bad',b'{"x":NaN}',b'{"x":Infinity}',b'{} trailing',b'\xff'])
def test_invalid_json_documents_fail_with_a_readable_error(raw):
    with pytest.raises(ValueError,match='Invalid JSON document'):json_document_text(raw)
