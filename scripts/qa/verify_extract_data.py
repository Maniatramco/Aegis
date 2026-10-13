"""Read-only route checks against the live configured OCI dataset and Parquet."""
import csv
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from fastapi.testclient import TestClient
from app import main, core

dataset='36fe2487-eaa3-5132-a9bd-12fdb48bcc52'
extraction='220d33d7-b58c-43eb-a22c-35de309acde8'
# This trusted internal test override affects only this isolated process.
# The running server retains its normal authentication and dataset grants.
main.app.dependency_overrides[main.auth]=lambda:'administrator'
client=TestClient(main.app)
try:
    record=main.get_record(extraction,'administrator','extraction')
    saved=core.store.json(record.ref)
    filters={'dataset_id':dataset,'template_id':saved['template_id']}
    response=client.get('/api/extract-data',params=filters)
    assert response.status_code==200,response.text
    data=response.json();assert data['total']==1 and len(data['rows'])==1
    row=data['rows'][0]
    assert row['extraction_id']==extraction and row['field:/highest_qualification']=='B.Tech in Computer Science'
    assert row['field:/full_name']=='Maya Rao' and row['version']==record.version
    exports={}
    for format in ('json','csv','xlsx'):
        response=client.get('/api/extract-data/export',params=filters|{'format':format})
        assert response.status_code==200,response.text
        assert f'aegis-extract-data.{format}' in response.headers['content-disposition']
        if format=='json':assert response.json()['rows']==data['rows']
        if format=='csv':
            rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
            assert len(rows)==1 and rows[0]['highest qualification']=='B.Tech in Computer Science'
        if format=='xlsx':
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                assert len(sheet.findall('.//s:row',ns))==2
                assert 'B.Tech in Computer Science' in [t.text for t in sheet.findall('.//s:t',ns)]
        exports[format]={'bytes':len(response.content),'passed':True}
    print(json.dumps({'passed':True,'dataset_id':dataset,'template_id':saved['template_id'],
                      'extraction_id':extraction,'row_count':data['total'],
                      'parquet_reference':saved['output_reference'],'exports':exports},indent=2))
finally:
    client.close();main.app.dependency_overrides.clear()
