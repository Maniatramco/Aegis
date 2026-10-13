"""Storage/queue failure tests complement the separate actual-model acceptance run."""
import io
import json
import pytest
from app import core, main, worker, providers, parquet_results
from test_dataset_models import system, dataset, upload, template, post


def test_original_pdf_page_image_is_scoped_and_preserves_source(system):
    from test_merged_documents import pdf
    from PIL import Image
    s=system;d=dataset(s);raw=pdf('Original fictional invoice reference V1-104')
    response=s.api.post('/api/documents/upload',data={'dataset_id':d['id']},files={'files':('source.pdf',raw,'application/pdf')})
    assert response.status_code==200
    id=response.json()['documents'][0]['id']
    assert s.api.get('/api/documents/'+id+'/preview').json()['page_count']==1
    rendered=s.api.get('/api/documents/'+id+'/page-image?page=1')
    assert rendered.status_code==200 and rendered.headers['content-type']=='image/png'
    assert Image.open(io.BytesIO(rendered.content)).width>100
    assert s.api.get('/api/documents/'+id+'/download').content==raw
    assert s.api.get('/api/documents/'+id+'/page-image?page=0').status_code==422
    assert s.api.get('/api/documents/'+id+'/page-image?page=2').status_code==422
    s.owner='bob';assert s.api.get('/api/documents/'+id+'/page-image?page=1').status_code==404
    assert s.api.get('/api/documents/'+id+'/preview').status_code==404


def test_review_page_count_includes_blank_original_pages_before_indexing(system):
    from pypdf import PdfWriter
    s=system;d=dataset(s);writer=PdfWriter()
    writer.add_blank_page(width=300,height=400);writer.add_blank_page(width=300,height=400)
    output=io.BytesIO();writer.write(output);raw=output.getvalue()
    response=s.api.post('/api/documents/upload',data={'dataset_id':d['id']},files={'files':('two-pages.pdf',raw,'application/pdf')})
    assert response.status_code==200
    id=response.json()['documents'][0]['id']
    assert s.api.get('/api/documents/'+id+'/preview').json()['page_count']==2
    assert s.api.get('/api/documents/'+id+'/page-image?page=2').status_code==200
    assert s.api.get('/api/documents/'+id+'/page-image?page=3').status_code==422
    assert s.api.get('/api/documents/'+id+'/download').content==raw


def run_extraction(s):
    d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once()
    return d,doc,s.api.get('/api/extractions/'+e['id']).json(),e['job']['id']


def test_real_parquet_and_immutable_review_revision(system):
    d,doc,e,jid=run_extraction(system);url='/api/extractions/'+e['id']
    raw=system.api.get(url+'/export?format=parquet').content
    assert raw[:4]==b'PAR1' and raw[-4:]==b'PAR1'
    assert parquet_results.decode(raw)==e['result']
    saved=system.api.patch(url,json={'version':1,'result':{'owner':'Reviewed Alice'}})
    assert saved.status_code==200,saved.text
    assert saved.json()['review_revision']==2
    assert saved.json()['output_reference']!=e['output_reference']
    assert system.api.get(url).json()['result']=={'owner':'Reviewed Alice'}
    assert parquet_results.decode(core.store.get(e['output_reference']))==e['result']
    assert system.api.patch(url,json={'version':1,'result':{'owner':'Overwrite'}}).status_code==409


def test_failed_write_never_completes_and_retry_reuses_model_checkpoint(system,monkeypatch):
    d=dataset(system);doc=upload(system,d)['documents'][0];t=template(system)
    e=post(system,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    original=core.store.put;calls=[];generate=providers.extract_with_evidence
    def count(*args):calls.append(1);return generate(*args)
    def fail(key,payload):
        if key.endswith('.parquet'):raise OSError('Synthetic disk failure')
        return original(key,payload)
    monkeypatch.setattr(providers,'extract_with_evidence',count);monkeypatch.setattr(core.store,'put',fail)
    assert worker.run_once()
    assert system.api.get('/api/extractions/'+e['id']).json()['status']=='failed'
    assert system.api.get('/api/extractions/'+e['id']+'/export?format=parquet').status_code==409
    monkeypatch.setattr(core.store,'put',original)
    assert system.api.post('/api/jobs/'+e['job']['id']+'/retry').status_code==200
    assert worker.run_once()
    assert system.api.get('/api/extractions/'+e['id']).json()['status']=='ready'
    assert len(calls)==1


def test_review_write_failure_preserves_saved_parquet(system,monkeypatch):
    d,doc,e,jid=run_extraction(system);original=core.store.put
    def fail(key,payload):
        if key.endswith('.parquet'):raise OSError('Synthetic disk failure')
        return original(key,payload)
    monkeypatch.setattr(core.store,'put',fail)
    response=system.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':{'owner':'Unsaved draft'}})
    assert response.status_code==503
    saved=system.api.get('/api/extractions/'+e['id']).json()
    assert saved['version']==1 and saved['result']==e['result'] and saved['output_reference']==e['output_reference']


def test_upload_id_precedes_index_and_replay_does_not_duplicate(system):
    d=dataset(system);t=template(system)
    args={'files':[('files',('same.txt',b'Alice is the owner.','text/plain'))],
          'data':{'dataset_id':d['id'],'template_id':t['id'],'display_name':'Editable extraction name','idempotency_key':'fixture-upload'}}
    accepted=system.api.post('/api/documents/upload',**args)
    assert accepted.status_code==200,accepted.text
    e=accepted.json()['extractions'][0]
    assert e['id'] and e['job']['status']=='blocked' and e['name']=='Editable extraction name'
    replay=system.api.post('/api/documents/upload',**args)
    assert replay.json()['extraction_id']==e['id']
    assert len(system.api.get('/api/documents').json())==1
    assert worker.run_once();assert worker.run_once()
    assert system.api.get('/api/extractions/'+e['id']).json()['status']=='ready'
    system.owner='bob'
    assert system.api.get('/api/extractions/'+e['id']).status_code==404


def test_nested_json_roundtrip_and_tamper_detection(system):
    value={'name':'Café 東京','items':[{'value':42.5,'code':None}],'empty':[],'object':{},'mixed':[1,'two',{}],'absent':None}
    data={'dataset_id':'test','document_ids':['doc'],'template_version':1,'result':value}
    output=parquet_results.persist('fixture',1,data)
    assert parquet_results.load(data|output)['result']==value
    core.store.put(output['output_reference'],b'corrupt')
    with pytest.raises(ValueError):parquet_results.load(data|output)


def test_corrected_prompt_resumes_new_revision_and_rejects_stale_revision(system,monkeypatch):
    d=dataset(system);doc=upload(system,d)['documents'][0];t=template(system)
    generate=providers.extract_with_evidence
    monkeypatch.setattr(providers,'extract_with_evidence',lambda *args:(_ for _ in ()).throw(ValueError('Synthetic invalid output')))
    e=post(system,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once()
    assert system.api.get('/api/extractions/'+e['id']).json()['status']=='failed'
    corrected=post(system,'/api/templates',{'name':'Corrected','schema':t['schema'],'instructions':'Copy the owner from the document.'})
    url='/api/extractions/'+e['id']+'/resume'
    resumed=post(system,url,{'version':1,'template_id':corrected['id']})
    assert resumed['version']==2 and resumed['template_version']==1 and resumed['template_id']==corrected['id']
    assert system.api.post(url,json={'version':1,'template_id':corrected['id']}).status_code==409
    monkeypatch.setattr(providers,'extract_with_evidence',generate)
    assert worker.run_once()
    saved=system.api.get('/api/extractions/'+e['id']).json()
    assert saved['status']=='ready' and '/v2-' in saved['output_reference']


def test_cpu_device_is_requested(system,monkeypatch):
    from app import ollama_provider
    monkeypatch.setenv('AEGIS_INFERENCE_DEVICE','cpu')
    monkeypatch.setattr(core,'settings',lambda:{'context_limit':8192,'max_output_tokens':1024,'extra_parameters':{'temperature':0.2}})
    assert ollama_provider.generation_options([{'role':'user','content':'Hello'}],1024)['num_gpu']==0
