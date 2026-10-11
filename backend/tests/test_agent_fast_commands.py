"""Simple commands skip inference but retain real confirmation and worker checks."""
import pytest
from app import providers, worker, main
from app.agent_workspace import simple_extraction_request
from test_dataset_models import system, dataset, template, upload
from test_agent_workspace import plan, call, send_files, proposal

@pytest.mark.parametrize('text,expected',[
    ('pls run extract','extract'),('extract','extract'),
    ('Please extract the attached documents.','extract'),
    ('Please upload and extract these resumes.','extract'),
    ('Could you upload then extract the attached profiles?','extract'),
    ('upload & extract these files','extract'),('extract the invoices','extract'),
    ('Can you upload and extract these resumes and delete them?',None),
    ('Do not upload and extract these resumes',None),
    ('upload and re-extract the files',None),
    ('Can you run extraction?','extract'),('re-extract the selected files','reextract'),
    ('run reextraction','reextract'),('How do I extract?',None),
    ("Don't extract these files",None),('extract invoice.pdf',None),
    ('If ready, extract',None),('extract and delete the files',None),
    ('extract using a different prompt',None),('What is extraction?',None),
])
def test_only_simple_imperatives_take_the_fast_path(text,expected):
    assert simple_extraction_request(text)==expected

@pytest.mark.parametrize('request_text',['pls run extract','Please upload and extract these resumes.','Could you upload then extract the attached profiles?'])
def test_attached_extract_skips_inference_and_chains_confirmed_upload_and_extraction(system,monkeypatch,request_text):
    s=system;d=dataset(s);t=template(s);old=upload(s,d)['documents'][0]
    monkeypatch.setattr(providers,'plan',lambda *args:pytest.fail('No model needed for this command'))
    p=plan(s,d,text=request_text,attached_filenames=['general.txt'],document_ids=[old['id']],template_id=t['id'])
    assert [c['tool'] for c in p['calls']]==['upload','extract']
    assert p['document_ids']==[] and all(c['status']=='pending' for c in p['calls'])
    assert len(s.api.get('/api/documents').json())==1
    jobs_before=len(s.api.get('/api/jobs').json())
    assert call(s,p,1).status_code==409
    assert len(s.api.get('/api/jobs').json())==jobs_before
    accepted=send_files(s,p);assert accepted.status_code==200,accepted.text
    refs=accepted.json()['calls'][0]['uploaded_document_ids'];assert refs!=[old['id']]
    assert call(s,p,1).status_code==409
    assert worker.run_once()
    result=call(s,p,1);assert result.status_code==200,result.text
    ex=result.json()['calls'][1]['result']['extraction_id']
    assert main.extraction(ex,s.owner)['document_ids']==refs
    assert worker.run_once()
    done=s.api.get('/api/agent-v2/plans/'+p['id']).json()
    assert all(c['status']=='completed' for c in done['calls'])

@pytest.mark.parametrize('text,tool',[('extract','extract'),('re-extract','reextract')])
def test_existing_documents_remain_selected_and_require_confirmation(system,monkeypatch,text,tool):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    monkeypatch.setattr(providers,'plan',lambda *args:pytest.fail('No inference expected'))
    before=len(s.api.get('/api/jobs').json())
    p=plan(s,d,text=text,document_ids=[doc['id']],template_id=t['id'])
    assert [c['tool'] for c in p['calls']]==[tool] and p['calls'][0]['status']=='pending'
    assert p['document_ids']==[doc['id']] and len(s.api.get('/api/jobs').json())==before
    r=s.api.post(f'/api/agent-v2/plans/{p["id"]}/calls/0',json={'confirmed':False})
    assert r.status_code==409 and len(s.api.get('/api/jobs').json())==before

def test_explicit_upload_then_extract_without_files_cannot_extract_old_selection(system,monkeypatch):
    s=system;d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    monkeypatch.setattr(providers,'plan',lambda *args:pytest.fail('Explicit workflow needs no inference'))
    p=plan(s,d,text='Please upload and extract these resumes.',document_ids=[doc['id']],template_id=t['id'])
    assert [c['tool'] for c in p['calls']]==['upload','extract'] and p['document_ids']==[]
    assert call(s,p,1).status_code==409

@pytest.mark.parametrize('values',[{'earlier_request':'Upload the attached documents'}, {'completed_tools':['upload']}, {'text':'re-extract','attached_filenames':['new.txt']}])
def test_clarifications_and_new_file_reextraction_still_use_contextual_planner(system,monkeypatch,values):
    seen=[];monkeypatch.setattr(providers,'plan',lambda *args:seen.append(args) or proposal(('extract',)))
    plan(system,dataset(system),**({'text':'extract'}|values))
    assert len(seen)==1
