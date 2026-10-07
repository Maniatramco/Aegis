"""Real durable storage/worker transitions with controlled provider faults."""
import io,csv,json,zipfile,time
import xml.etree.ElementTree as ET
import pytest
from app import core,main,worker,providers,temporary_files
from test_dataset_models import system,dataset,upload,template,post

def extracted(s):
    d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':t['id']})
    assert worker.run_once();return d,doc,s.api.get('/api/extractions/'+e['id']).json()

def test_extraction_list_links_only_owned_documents_and_saved_versions(system):
    s=system;d,doc,e=extracted(s)
    saved=s.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':{'owner':'Reviewed Alice'}}).json()
    rows=s.api.get('/api/extractions').json()
    item=next(r for r in rows if r['id']==e['id'])
    assert item['document_ids']==[doc['id']] and item['version']==saved['version']
    assert item['review_status']=='reviewed' and item['template_id']==e['template_id']
    assert 'result' not in item and 'schema' not in item
    s.owner='bob'
    assert s.api.get('/api/extractions').json()==[]

def test_prompt_template_instructions_reach_the_extraction_model(system,monkeypatch):
    captured=[]
    def extract(text,schema):
        captured.append(text);return {'data':{'owner':'Alice'},'evidence':[]}
    monkeypatch.setattr(providers,'extract',extract)
    schema={'type':'object','description':'Copy the project owner exactly; never guess.','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}
    providers.extract_with_evidence('Alice owns the project.',schema,[])
    assert 'Copy the project owner exactly; never guess.' in captured[0]

def test_versions_conflict_schema_and_saved_exports(system):
    s=system;d,doc,e=extracted(s);url='/api/extractions/'+e['id'];original=core.store.get('documents/'+doc['id']+'/original')
    value='  =HYPERLINK("https://invalid.example")\nCafé, 東京'
    saved=s.api.patch(url,json={'version':e['version'],'result':{'owner':value}})
    assert saved.status_code==200,saved.text
    assert saved.json()['version']==2 and saved.json()['review_status']=='reviewed'
    assert s.api.patch(url,json={'version':1,'result':{'owner':'Overwrite'}}).status_code==409
    assert s.api.patch(url,json={'version':2,'result':{'bad':'wrong schema'}}).status_code==400
    assert s.api.patch(url,content=json.dumps({'version':2,'result':{'owner':'\ud800'}}),headers={'Content-Type':'application/json'}).status_code==400
    assert s.api.get(url).json()['result']=={'owner':value}
    versions=s.api.get(url+'/versions').json();assert len(versions)==2 and versions[0]['result']!=versions[1]['result']
    assert core.store.get('documents/'+doc['id']+'/original')==original
    payload=s.api.get(url+'/export?format=json').json();assert payload['result']['owner']==value and payload['version']==2 and payload['sources']
    exported=s.api.get(url+'/export?format=csv');rows=list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows[0]['value']=="'"+value and rows[0]['extraction_id']==e['id'] and rows[0]['field']=='/owner'
    result=s.api.get(url+'/export?format=xlsx');assert result.content[:2]==b'PK'
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        for name in archive.namelist():ET.fromstring(archive.read(name))
        sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'));ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert not sheet.findall('.//s:f',ns);assert value in [t.text for t in sheet.findall('.//s:t',ns)]
    assert s.api.get(url+'/export?format=html').status_code==400
    s.owner='bob'
    assert s.api.get(url+'/export?format=xlsx').status_code==404
    assert s.api.get('/api/documents/'+doc['id']+'/source').status_code==404

def test_retry_failed_index_same_job_reuses_extraction(system,monkeypatch):
    s=system;d=dataset(s);data=upload(s,d,run=False);doc=data['documents'][0];jid=data['jobs'][0]['id']
    parse=worker.parse_document;calls=[]
    def track(*args):calls.append(args[0]);return parse(*args)
    monkeypatch.setattr(worker,'parse_document',track);embed=providers.embed
    def fail(*args):raise providers.ProviderError('Synthetic embedding outage')
    monkeypatch.setattr(providers,'embed',fail);assert worker.run_once()
    job=s.api.get('/api/jobs').json()[0];assert job['status']=='failed' and job['workflow']['stages']['extract']['status']=='completed' and job['workflow']['stages']['index']['status']=='failed'
    assert s.api.post('/api/jobs/'+jid+'/retry').status_code==200
    assert s.api.post('/api/jobs/'+jid+'/retry').status_code==409
    assert s.api.post('/api/documents/'+doc['id']+'/reindex',json={}).status_code==409
    monkeypatch.setattr(providers,'embed',embed);assert worker.run_once();assert len(calls)==1
    jobs=s.api.get('/api/jobs').json();assert len(jobs)==1 and jobs[0]['id']==jid
    assert all(stage['status']=='completed' for stage in jobs[0]['workflow']['stages'].values())
    assert s.api.get('/api/documents/'+doc['id']).json()['status']=='ready'

def test_reextract_preserves_original_reviews_versions_and_duplicate_guard(system):
    s=system;d,doc,e=extracted(s);url='/api/extractions/'+e['id'];did=doc['id'];original=core.store.get('documents/'+did+'/original')
    saved=s.api.patch(url,json={'version':1,'result':{'owner':'Reviewed Alice'}}).json()
    assert s.api.post('/api/documents/'+did+'/reextract',json={}).status_code==409
    r=s.api.post('/api/documents/'+did+'/reextract',json={'confirm_reviewed':True});assert r.status_code==200,r.text
    assert s.api.post('/api/documents/'+did+'/reextract',json={'confirm_reviewed':True}).status_code==409
    assert worker.run_once();assert core.store.get('documents/'+did+'/original')==original
    assert core.store.get('documents/'+did+'/versions/v1/parsed.json')
    assert s.api.get(url).json()['result']=={'owner':'Reviewed Alice'}
    assert s.api.post(url+'/reextract',json={'version':2}).status_code==409
    assert s.api.post(url+'/reextract',json={'version':2,'confirm_reviewed':True}).status_code==200
    assert worker.run_once();assert s.api.get(url).json()['version']==3
    current=s.api.get(url).json()
    assert current['review_status']=='unreviewed' and current['edited_fields']==[] and current['original_evidence']==[]
    assert not any(key in current for key in ('reviewed_at','reviewed_by','evidence_notice'))
    reviewed=s.api.get(url+'/versions').json()[1]
    assert reviewed['result']=={'owner':'Reviewed Alice'} and reviewed['edited_fields']==['/owner']

def test_failed_save_keeps_last_version(system,monkeypatch):
    s=system;d,doc,e=extracted(s);url='/api/extractions/'+e['id'];put=core.store.put_json
    def fail(key,value):
        if key==f'extraction/{e["id"]}/v2.json':raise OSError('Synthetic disk failure')
        return put(key,value)
    monkeypatch.setattr(core.store,'put_json',fail)
    with pytest.raises(OSError):s.api.patch(url,json={'version':1,'result':{'owner':'Draft'}})
    assert s.api.get(url).json()['version']==1 and s.api.get(url).json()['result']==e['result']

def test_temporary_cleanup_expiry_and_permanent_reference_protection(system):
    s=system;d=dataset(s);permanent=upload(s,d)['documents'][0]
    session=post(s,'/api/temporary-chat/sessions')
    def temp(name):
        data=s.api.post('/api/documents/upload',files={'files':(name,b'Alice is the project owner. Safe temporary test.','text/plain')},data={'dataset_id':d['id'],'temporary_session_id':session['id']});assert data.status_code==200,data.text;assert worker.run_once();return data.json()['documents'][0]
    disposable=temp('disposable.txt');kept=temp('kept.txt');used=temp('used.txt')
    assert s.api.post('/api/documents/'+kept['id']+'/keep').status_code==200
    post(s,'/api/conversations',{'dataset_id':d['id'],'document_ids':[used['id']]})
    result=post(s,'/api/temporary-chat/messages',{'text':'Who owns the project?','dataset_id':d['id'],'document_ids':[permanent['id'],disposable['id']]})
    assert result['message']['citations'] and len(s.api.get('/api/conversations').json())==1
    cleaned=s.api.delete('/api/temporary-chat/sessions/'+session['id']).json();assert cleaned['deleted_document_ids']==[disposable['id']]
    for doc in (kept,used,permanent):assert s.api.get('/api/documents/'+doc['id']).status_code==200
    for suffix in ('original','chunks.json','index.json','parsed.json','retention.json'):
        with pytest.raises(FileNotFoundError):core.store.get('documents/'+disposable['id']+'/'+suffix)
    expired=temp('expiry.txt');record=main.get_record(session['id'],s.owner,'temporary_session');core.store.put_json(record.ref,{'expires_at':time.time()-1});temporary_files.purge_expired()
    assert s.api.get('/api/documents/'+expired['id']).status_code==404
    assert s.api.get('/api/documents/'+permanent['id']).status_code==200
    s.owner='bob';assert s.api.delete('/api/temporary-chat/sessions/'+session['id']).status_code==404
