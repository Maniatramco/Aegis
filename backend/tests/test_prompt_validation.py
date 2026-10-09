"""Both preview validation and saving reject invalid extraction templates atomically."""
import pytest
from test_dataset_models import system, dataset

BASE={'type':'object','properties':{'total':{'type':'number'}},'required':['total'],'additionalProperties':False}

@pytest.mark.parametrize('schema,location',[
    ({**BASE,'type':'array'},'$'),
    ({**BASE,'properties':{'total':{'type':'invalid'}}},'$.properties.total.type'),
    ({**BASE,'additionalProperties':True},'$'),
    ({**BASE,'required':[]},'$'),
    ({**BASE,'properties':{'total':{'type':['object','null'],'properties':{}}}},'$.properties.total'),
    ({**BASE,'properties':{'total':{'$ref':'https://example.invalid/schema.json'}}},'$.properties.total.$ref'),
])
def test_invalid_schema_reports_its_location_without_creating_a_template(system,schema,location):
    s=system;d=dataset(s)
    body={'name':'Invalid prompt QA','dataset_id':d['id'],'schema':schema}
    for path in ['/api/templates/validate','/api/templates']:
        response=s.api.post(path,json=body)
        assert response.status_code==400,response.text
        assert location in response.json()['detail']
        assert s.api.get('/api/templates').json()==[]

def test_valid_preview_is_read_only_and_save_round_trips_the_reviewed_schema(system):
    s=system;d=dataset(s);body={'name':'Validated prompt QA','dataset_id':d['id'],'schema':BASE}
    preview=s.api.post('/api/templates/validate',json=body)
    assert preview.status_code==200 and preview.json()['schema']==BASE
    assert s.api.get('/api/templates').json()==[]
    saved=s.api.post('/api/templates',json=body)
    assert saved.status_code==200 and saved.json()['schema']==BASE
    assert len(s.api.get('/api/templates').json())==1

def test_uploaded_filename_is_retained_in_listing_and_when_editing_new_versions(system):
    s=system;d=dataset(s);body={'name':'Dataset prompt rows QA','dataset_id':d['id'],'schema':BASE,'source_filename':'mani.json'}
    saved=s.api.post('/api/templates',json=body).json()
    assert saved['source_filename']=='mani.json'
    assert saved['name']=='mani.json'
    assert s.api.get('/api/templates').json()[0]['source_filename']=='mani.json'
    body.pop('source_filename');body['name']='Renamed prompt'
    edited=s.api.put('/api/templates/'+saved['id'],json=body)
    assert edited.status_code==200 and edited.json()['source_filename']=='mani.json'
    assert edited.json()['name']=='mani.json'
    assert edited.json()['version']==2
    assert all(version['source_filename']=='mani.json' for version in s.api.get('/api/templates/'+saved['id']+'/versions').json())
    assert 'source_filename' not in s.api.get('/api/templates/'+saved['id']+'/export').json()

def test_repeated_filename_uploads_update_one_template_and_keep_prior_versions(system):
    s=system;d=dataset(s);body={'name':'Ignored JSON name','schema':BASE,'dataset_id':d['id'],'source_filename':'mani.json'}
    first=s.api.post('/api/templates',json=body).json()
    for version in [2,3]:
        body['name']='Another embedded name';body['schema']={**BASE,'description':'Revision '+str(version)}
        preview=s.api.post('/api/templates/validate',json=body)
        assert preview.json()['existing_template_id']==first['id'] and preview.json()['name']=='mani.json'
        saved=s.api.post('/api/templates',json=body)
        assert saved.status_code==200 and saved.json()['id']==first['id'] and saved.json()['version']==version
    assert len(s.api.get('/api/templates').json())==1
    versions=s.api.get('/api/templates/'+first['id']+'/versions').json()
    assert [v['version'] for v in versions]==[1,2,3] and versions[0]['schema']==BASE
    exported=s.api.get('/api/templates/'+first['id']+'/export?version=1')
    assert exported.json()['schema']==BASE and "filename*=UTF-8''mani.json" in exported.headers['content-disposition']
    invalid={**body,'schema':{**BASE,'additionalProperties':True}}
    assert s.api.post('/api/templates',json=invalid).status_code==400
    assert len(s.api.get('/api/templates/'+first['id']+'/versions').json())==3

def test_filename_replacement_is_scoped_to_dataset_and_owner(system):
    s=system;one=dataset(s,'One');two=dataset(s,'Two');body={'name':'Ignored','schema':BASE,'source_filename':'mani.json'}
    a=s.api.post('/api/templates',json={**body,'dataset_id':one['id']}).json()
    b=s.api.post('/api/templates',json={**body,'dataset_id':two['id']}).json()
    assert a['id']!=b['id'] and b['version']==1
    shared=s.api.post('/api/templates',json=body).json()
    s.owner='bob';other=s.api.post('/api/templates',json=body).json()
    assert other['id']!=shared['id'] and other['version']==1
    s.owner='alice';listed=s.api.get('/api/templates').json()
    assert len(listed)==3 and all(t['version']==1 for t in listed)

def test_existing_imports_display_their_filename_and_update_their_original_record(system):
    from app import main
    s=system;d=dataset(s)
    legacy=main.new_record('template',s.owner,'Embedded JSON name',parent=d['id'],data={'name':'Embedded JSON name','schema':BASE,'version':1,'dataset_id':d['id'],'source_filename':'mani.json'})
    assert s.api.get('/api/templates').json()[0]['name']=='mani.json'
    saved=s.api.post('/api/templates',json={'name':'Other embedded name','schema':BASE,'dataset_id':d['id'],'source_filename':'mani.json'}).json()
    assert saved['id']==legacy.id and saved['name']=='mani.json' and saved['version']==2
    assert len(s.api.get('/api/templates').json())==1

def test_concurrent_reuploads_keep_distinct_versions_on_the_same_template(system):
    from concurrent.futures import ThreadPoolExecutor
    s=system;body={'name':'Ignored','schema':BASE,'source_filename':'mani.json'}
    first=s.api.post('/api/templates',json=body).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda revision:s.api.post('/api/templates',json={**body,'schema':{**BASE,'description':str(revision)}}),[2,3]))
    assert all(result.status_code==200 and result.json()['id']==first['id'] for result in results)
    assert sorted(result.json()['version'] for result in results)==[2,3]
    assert len(s.api.get('/api/templates').json())==1
    assert len(s.api.get('/api/templates/'+first['id']+'/versions').json())==3

@pytest.mark.parametrize('filename',['../mani.json','C:\\private\\mani.json','mani.txt','bad\nfile.json'])
def test_source_filename_is_a_json_basename_not_a_path(system,filename):
    s=system;response=s.api.post('/api/templates',json={'name':'Invalid filename','schema':BASE,'source_filename':filename})
    assert response.status_code==422
    assert s.api.get('/api/templates').json()==[]
