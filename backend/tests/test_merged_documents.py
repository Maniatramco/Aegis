"""Merged uploads retain all originals; one result cannot silently omit a source."""
import copy
import io
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
from app import core, main, worker, providers, merged_documents
from test_dataset_models import system, dataset, template
from test_agent_workspace import plan


def merged_flow(s, strategy='records'):
    d=dataset(s);t=template(s)
    p=plan(s,d,text='extract',attached_filenames=['Alice.txt','Bob.txt','Carol.txt'],template_id=t['id'])
    parts=[(name+'.txt',f'{name} owns this project. Total 42.'.encode()) for name in ('Alice','Bob','Carol')]
    r=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0/upload',data={'dataset_id':d['id'],'confirmed':'true','continue_extraction':'true','extraction_mode':'merge','merge_strategy':strategy,'template_id':t['id']},files=[('files',(name,raw,'text/plain')) for name,raw in parts])
    assert r.status_code==200,r.text
    return p,parts,r.json()


def test_single_upload_three_records_provenance_download_and_schema(system,monkeypatch):
    s=system;calls=[]
    def extract(text,schema,sources):
        found=[name for name in ('Alice','Bob','Carol') if name+' owns' in text]
        assert len(found)==1
        calls.append(found[0]);return {'owner':found[0]},[]
    monkeypatch.setattr(providers,'extract_with_evidence',extract)
    p,parts,accepted=merged_flow(s)
    docs=s.api.get('/api/documents').json();assert len(docs)==3
    assert len(accepted['calls'][0]['jobs'])==3
    for name,raw in parts:
        doc=next(d for d in docs if d['name']==name)
        assert s.api.get(f'/api/documents/{doc["id"]}/download').content==raw
    assert all(worker.run_once() for _ in range(4))
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    entry=done['calls'][1]['result']['extractions'][0]
    assert entry['status']=='completed'
    e=s.api.get('/api/extractions/'+entry['extraction_id']).json()
    assert set(e['document_ids'])=={d['id'] for d in docs}
    assert e['merge']['logical'] and e['merge']['source_count']==3
    assert [r['fields']['owner'] for r in e['result']['records']]==['Alice','Bob','Carol']
    assert calls==['Alice','Bob','Carol']
    assert s.api.get('/api/extractions/'+e['id']+'/export?format=parquet').content[:4]==b'PAR1'
    exported=s.api.get('/api/extractions/'+e['id']+'/export?format=json').json()
    assert exported['extraction_id']==e['id'] and exported['merge']['source_count']==3
    bad=copy.deepcopy(e['result']);bad['records'].pop()
    assert s.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':bad}).status_code==400
    bad=copy.deepcopy(e['result']);bad['records'][0]['source_filename']='Other.txt'
    assert s.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':bad}).status_code==400
    s.owner='other'
    assert s.api.get(f'/api/documents/{doc["id"]}/merged-sources/1/source').status_code==404
    assert s.api.get('/api/extractions/'+e['id']+'/merged-file').status_code==404


def test_same_record_parts_still_use_one_template_call(system,monkeypatch):
    seen=[]
    monkeypatch.setattr(providers,'extract_with_evidence',lambda text,schema,sources:(seen.append(text) or {'owner':'Combined'},[]))
    p,_,_=merged_flow(system,'single')
    assert all(worker.run_once() for _ in range(4))
    assert len(seen)==1 and all(x+' owns' in seen[0] for x in ('Alice','Bob','Carol'))
    done=system.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert done['calls'][1]['result']['extractions'][0]['data']=={'owner':'Combined'}


def pdf(text):
    writer=PdfWriter();page=writer.add_blank_page(width=300,height=300)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 10 250 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out);return out.getvalue()


def test_pdf_merge_has_every_page_and_valid_local_schema_references(system):
    parts=[(f'{x}.pdf',pdf(f'{x} owns this fictional project.')) for x in ('Alice','Bob','Carol')]
    name,raw,data=merged_documents.prepare(parts)
    reader=PdfReader(io.BytesIO(raw))
    assert name.endswith('.pdf') and len(reader.pages)==3
    assert all(x in reader.pages[n].extract_text() for n,x in enumerate(('Alice','Bob','Carol')))
    assert [(s['merged_page_start'],s['merged_page_end']) for s in data['sources']]==[(1,1),(2,2),(3,3)]
    from jsonschema import validate, ValidationError
    schema={'type':'object','$defs':{'name':{'type':'string'}},'properties':{'name':{'$ref':'#/$defs/name'}},'required':['name']}
    wrapped=merged_documents.records_schema(schema,data['sources'])
    result={'records':[{'source_filename':s['name'],'source_key':s['key'],'fields':{'name':'Alice'}} for s in data['sources']]}
    validate(result,wrapped)
    result['records'][0]['fields']['name']=42
    with pytest.raises(ValidationError):validate(result,wrapped)


def test_failed_second_record_is_not_reported_complete_and_job_retry_reuses_first(system,monkeypatch):
    calls=[];fail=[True]
    def extract(text,schema,sources):
        name=next(x for x in ('Alice','Bob','Carol') if x+' owns' in text);calls.append(name)
        if name=='Bob' and fail[0]:raise providers.ProviderError('Model generation timed out. Retry processing.')
        return {'owner':name},[]
    monkeypatch.setattr(providers,'extract_with_evidence',extract)
    p,_,_=merged_flow(system)
    assert all(worker.run_once() for _ in range(4))
    stopped=system.api.get('/api/agent-v2/plans/'+p['id']).json()['calls'][1]
    assert stopped['status']=='failed'
    entry=stopped['result']['extractions'][0]
    assert entry['record_progress']['completed']==1
    fail[0]=False
    assert system.api.post('/api/jobs/'+stopped['job_ids'][0]+'/retry').status_code==200
    assert worker.run_once()
    saved=main.extraction(entry['extraction_id'],system.owner)
    assert saved['status']=='ready' and len(saved['result']['records'])==3
    assert calls==['Alice','Bob','Bob','Carol']


def test_invalid_merge_creates_no_catalog_document(system):
    s=system;d=dataset(s)
    r=s.api.post('/api/documents/upload',data={'dataset_id':d['id'],'merge_files':'true'},files=[('files',('a.txt',b'Valid text','text/plain')),('files',('b.pdf',b'Broken','application/pdf'))])
    assert r.status_code==422 and s.api.get('/api/documents').json()==[]


def test_verified_quote_retains_original_page_and_export_provenance(system,monkeypatch):
    from types import SimpleNamespace
    from app import result_exports
    chunk={'id':'chunk-second','document_id':'merged','document_name':'merged.pdf','page':5,'text':'Bob owns this project.','source_key':'2','source_filename':'Bob.pdf','source_page':2}
    monkeypatch.setattr(providers,'extract',lambda *args:{'data':{'owner':'Bob'},'evidence':[{'field':'/owner','chunk_id':chunk['id'],'quote':'Bob'}]})
    schema={'type':'object','properties':{'owner':{'type':'string'}},'required':['owner']}
    _,quotes=providers.extract_with_evidence(chunk['text'],schema,[chunk])
    assert quotes[0]['source_page']==2 and quotes[0]['source_key']=='2'
    data={'merge_records':True,'merge':{'document_id':'merged','sources':[{'key':'1'},{'key':'2'}]},'result':{'records':[{'fields':{'owner':'Alice'}},{'fields':{'owner':'Bob'}}]},'sources':[{'document_id':'merged','source_key':'1','page':1},{'document_id':'merged','source_key':'2','page':5}]}
    rows=list(result_exports.rows(SimpleNamespace(id='extract',version=1),data))
    assert len(rows)==2 and rows[0][7]==1 and rows[1][7]==5
