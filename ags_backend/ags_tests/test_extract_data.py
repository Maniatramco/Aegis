import csv
import io
import json
import zipfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from ags_app import core, main, extract_data, parquet_results
from test_dataset_models import system, dataset, template
from test_review_workflow import extracted


def saved(s, d, t, result, status='ready'):
    r=main.new_record('extraction',s.owner,'Table result',d['id'],status=status)
    data={'dataset_id':d['id'],'template_id':t['id'],'template_version':2,'document_ids':[],
          'result':result,'review_status':'unreviewed'}
    data.update(parquet_results.persist(r.id,1,data))
    core.store.put_json(r.ref,data)
    return r


def test_latest_review_filters_and_authorization(system):
    s=system;d,doc,e=extracted(s)
    old=s.api.get('/api/extract-data',params={'dataset_id':d['id'],'template_id':e['template_id']}).json()
    assert old['total']==1 and old['rows'][0]['field:/owner']=='MOCK TEST VALUE'
    response=s.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':{'owner':'Reviewed Alice'}})
    assert response.status_code==200
    other=dataset(s,'Other dataset');t=template(s);saved(s,other,t,{'owner':'Other owner'})
    data=s.api.get('/api/extract-data',params={'dataset_id':d['id'],'template_id':e['template_id']}).json()
    assert data['total']==1 and data['rows'][0]['version']==2
    assert data['rows'][0]['field:/owner']=='Reviewed Alice' and data['rows'][0]['review_status']=='reviewed'
    assert s.api.get('/api/extract-data',params={'dataset_id':d['id'],'template_id':t['id']}).json()['total']==0
    assert s.api.get('/api/extract-data/export',params={'dataset_id':d['id'],'template_id':e['template_id'],'format':'json'}).json()['rows']==data['rows']
    s.owner='bob'
    for path in ('/api/extract-data','/api/extract-data/export'):
        assert s.api.get(path,params={'dataset_id':d['id'],'template_id':e['template_id']}).status_code==404
        assert s.api.get(path,params={'template_id':t['id']}).status_code==404


def test_records_are_rows_nested_objects_columns_arrays_lossless(system):
    s=system;d=dataset(s);t=template(s)
    result={'records':[{'source_filename':'one.pdf','fields':{'name':'One','address':{'city':'東京'},'skills':['SQL','Python'],'years':8}},
                       {'source_filename':'two.pdf','fields':{'name':'Two','email':None,'years':0}}]}
    r=saved(s,d,t,result)
    data=s.api.get('/api/extract-data',params={'template_id':t['id']}).json()
    assert data['total']==2 and data['extraction_count']==1
    assert [row['document'] for row in data['rows']]==['one.pdf','two.pdf']
    assert data['rows'][0]['field:/skills']==['SQL','Python'] and data['rows'][0]['field:/address/city']=='東京'
    assert data['rows'][1]['field:/years']==0 and data['rows'][1]['field:/email'] is None
    assert 'field:/source_filename' not in {c['key'] for c in data['columns']}
    assert all(row['extraction_id']==r.id for row in data['rows'])


def test_pagination_export_all_rows_and_spreadsheet_safety(system):
    s=system;d=dataset(s);t=template(s)
    saved(s,d,t,[{'owner':'=1+2','index':n} for n in range(27)])
    saved(s,d,t,{'owner':'Not completed'},status='processing')
    first=s.api.get('/api/extract-data',params={'template_id':t['id'],'limit':25}).json()
    second=s.api.get('/api/extract-data',params={'template_id':t['id'],'limit':25,'offset':25}).json()
    assert first['total']==27 and len(first['rows'])==25 and len(second['rows'])==2
    csv_response=s.api.get('/api/extract-data/export',params={'template_id':t['id'],'format':'csv'})
    rows=list(csv.DictReader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
    assert len(rows)==27 and rows[0]['owner']=="'=1+2"
    xlsx=s.api.get('/api/extract-data/export',params={'template_id':t['id'],'format':'xlsx'})
    assert xlsx.status_code==200
    with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
        sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert len(sheet.findall('.//s:row',ns))==28 and not sheet.findall('.//s:f',ns)
    assert s.api.get('/api/extract-data/export',params={'template_id':t['id'],'format':'html'}).status_code==400
    assert s.api.get('/api/extract-data',params={'template_id':t['id'],'offset':-1}).status_code==422
    assert s.api.get('/api/extract-data',params={'template_id':t['id'],'limit':101}).status_code==422


def test_corrupt_saved_result_blocks_partial_listing_and_export(system):
    s=system;d=dataset(s);t=template(s);r=saved(s,d,t,{'owner':'Alice'})
    ref=core.store.json(r.ref)['output_reference'];core.store.put(ref,b'corrupted')
    for path in ('/api/extract-data','/api/extract-data/export'):
        response=s.api.get(path,params={'template_id':t['id']})
        assert response.status_code==503 and 'no partial results' in response.json()['detail']


def test_one_prompt_required_and_other_prompt_results_excluded(system):
    s=system;d=dataset(s);first=template(s);second=template(s)
    saved(s,d,first,{'owner':'First prompt'})
    saved(s,d,second,{'owner':'Second prompt'})
    for path in ('/api/extract-data','/api/extract-data/export'):
        assert s.api.get(path).status_code==422
        assert s.api.get(path,params={'template_id':''}).status_code==422
        response=s.api.get(path,params={'template_id':first['id'],'format':'json'})
        assert response.status_code==200
        assert response.json()['total']==1 and response.json()['rows'][0]['field:/owner']=='First prompt'


def test_scalar_field_paths_do_not_collide_with_metadata():
    r=SimpleNamespace(id='id',name='name',version=1,created_at=1)
    data=extract_data.table([(r,{'result':{'version':7,'a/b':False,'empty':{},'items':[],'Dataset':'Field dataset'}},'Dataset','Prompt',[])])
    assert data['rows'][0]['version']==1 and data['rows'][0]['field:/version']==7
    assert data['rows'][0]['field:/a~1b'] is False and data['rows'][0]['field:/items']==[]
    assert json.loads(extract_data.render(data,'json')[0])['rows']==data['rows']
    exported=list(csv.DictReader(io.StringIO(extract_data.render(data,'csv')[0].decode('utf-8-sig'))))
    assert exported[0]['Dataset (dataset)']=='Dataset' and exported[0]['Dataset (field:/Dataset)']=='Field dataset'
