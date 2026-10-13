"""Read-only proof of browser finalization, stored artifacts, and rejected edits."""
import hashlib,json
from fastapi.testclient import TestClient
from ags_app import core,main,parquet_results,dataset_access,relational
id='06007e9d-b1e2-4bc8-b80a-7427e4ca18ce'
main.app.dependency_overrides[main.auth]=lambda:'administrator'
client=TestClient(main.app)
try:
    response=client.get('/api/extractions/'+id);assert response.status_code==200,response.text
    data=response.json();assert data['qa_fixture'] and data['review_status']=='reviewed' and data['review_locked']
    assert data['version']==2
    record=main.get_record(id,'administrator','extraction');stored=core.store.json(record.ref)
    result=parquet_results.load(stored)['result'];assert result==data['result']
    assert client.patch('/api/extractions/'+id,json={'version':2,'result':result}).status_code==409
    assert client.post('/api/extractions/'+id+'/reextract',json={'version':2,'confirm_reviewed':True}).status_code==409
    original=main.get_record(data['qa_fixture_source_id'],'administrator','extraction')
    assert original.version==1 and core.store.json(original.ref)['review_status']=='unreviewed'
    original_pdf=core.store.get('documents/71ad6802-04f9-4a0d-ad0e-5f1ba39fca34/original')
    assert hashlib.sha256(original_pdf).hexdigest()=='cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85'
    historical=client.get('/api/extractions/'+id+'/source-evidence',params={'version':1}).json()
    assert historical['version']==1 and historical['fields']==result
    print(json.dumps({'passed':True,'qa_extraction_id':id,'version':2,'reviewed_locked':True,
                      'parquet_verified':True,'output_reference':stored['output_reference'],
                      'original_fixture_unchanged':True,'original_pdf_sha256':hashlib.sha256(original_pdf).hexdigest(),
                      'edit_rejected':True,'same_result_reextract_rejected':True,'historical_citation_verified':True},indent=2))
finally:
    client.close();main.app.dependency_overrides.clear()
