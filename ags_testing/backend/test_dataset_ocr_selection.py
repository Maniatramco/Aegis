"""Independent dataset OCR choices preserve embeddings, access and queued work."""
import json
import copy
import pytest
from ags_app import core, dataset_models as routing, worker, ocr, agent_consent, main
from ags_app.ags_models import cloud_ocr
from ags_app.ags_models.connection import ModelConnection
from test_dataset_models import system, dataset, mapping
from test_model_registration import body, register, select
from test_ocr import scan


def vision(s,name='gpt-4o-mini'):
    return register(s,body('extraction','openai-compatible',name='OCR '+name,provider_model=name,context_limit=128000,max_output_tokens=4096))


def choose(s,d,m):
    cfg=s.api.get('/api/datasets/'+d['id']+'/models').json()
    entries=cfg['mappings']+([{'model_id':m['id'],'enabled':True}] if m and not any(x['model_id']==m['id'] for x in cfg['mappings']) else [])
    return mapping(s,d,mappings=entries,ocr_model_id=m['id'] if m else None)


def test_ocr_saved_independently_and_old_clients_preserve_choice(system):
    s=system;d=dataset(s);m=vision(s)
    assert m['ocr_eligible'] and not next(x for x in d['models'] if x['id']==d['embedding_model_id'])['ocr_eligible']
    saved=choose(s,d,m)
    for key in ('embedding_model_id','default_chat_model_id','default_extraction_model_id','index_generation','embedding_selection'):
        assert saved[key]==d[key]
    assert s.api.get('/api/datasets/'+d['id']+'/models').json()['ocr_model_id']==m['id']
    assert mapping(s,d)['ocr_model_id']==m['id']  # Omitted field is not an implicit reset.
    assert choose(s,d,None)['ocr_model_id'] is None


def test_ocr_uses_selected_model_instead_of_default_extraction_and_local_is_explicit(system):
    s=system;d=dataset(s);default=vision(s,'gpt-4o');select(s,d,default,'extraction');selected=vision(s)
    choose(s,d,selected)
    record=routing.owned(d['id'],s.owner,'knowledge_base')
    snap=routing.execution_snapshot(record,'embedding')
    assert snap['ocr_execution']['model_id']==selected['id']
    assert snap['settings']['ocr_model']=='gpt-4o-mini'
    assert snap['settings']['ocr_provider']=='openai'
    mapping(s,d,ocr_model_id='local')
    assert 'ocr_execution' not in routing.execution_snapshot(routing.owned(d['id'],s.owner,'knowledge_base'),'embedding')
    mapping(s,d,ocr_model_id=None)
    assert routing.execution_snapshot(routing.owned(d['id'],s.owner,'knowledge_base'),'embedding')['ocr_execution']['model_id']==default['id']


@pytest.mark.parametrize('which',['embedding','text','disabled','unmapped','foreign'])
def test_invalid_ocr_choice_never_changes_saved_mappings(system,which):
    s=system;d=dataset(s);m=vision(s)
    if which=='text':m=vision(s,'gpt-3.5-turbo')
    if which=='foreign':
        s.owner='bob';m=vision(s);s.owner='alice'
    cfg=s.api.get('/api/datasets/'+d['id']+'/models').json()
    value=d['embedding_model_id'] if which=='embedding' else m['id']
    payload=copy.deepcopy({key:cfg[key] for key in ('mappings','embedding_model_id','default_chat_model_id','default_extraction_model_id')})
    if which not in ('embedding','unmapped'):payload['mappings']+=[{'model_id':m['id'],'enabled':which!='disabled'}]
    response=s.api.put('/api/datasets/'+d['id']+'/models',json=payload|{'ocr_model_id':value})
    assert response.status_code in (400,404),response.text
    assert s.api.get('/api/datasets/'+d['id']+'/models').json()==cfg


def test_selected_ocr_mapping_cannot_be_disabled_or_lost_by_stale_client(system):
    s=system;d=dataset(s);m=vision(s);choose(s,d,m)
    cfg=s.api.get('/api/datasets/'+d['id']+'/models').json()
    payload={key:cfg[key] for key in ('mappings','embedding_model_id','default_chat_model_id','default_extraction_model_id')}
    payload['mappings']=[entry|{'enabled':False} if entry['model_id']==m['id'] else entry for entry in cfg['mappings']]
    assert s.api.put('/api/datasets/'+d['id']+'/models',json=payload).status_code==400
    stale=s.api.put('/api/datasets/'+d['id']+'/models',json={**payload,'ocr_model_id':None,'expected_version':cfg['version']-1})
    assert stale.status_code==409


def test_queued_index_keeps_ocr_choice_after_a_new_mapping_is_saved(system,monkeypatch):
    s=system;d=dataset(s);mini=vision(s);full=vision(s,'gpt-4o');choose(s,d,mini)
    monkeypatch.setattr(ocr,'call',lambda *a,**k:pytest.fail('Explicit cloud OCR contacted local Ollama'))
    sent=[]
    def post(self,path,payload,headers=None):
        sent.append(payload['model'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':'Synthetic total USD 42.50','unreadable':False})}}]}
    monkeypatch.setattr(ModelConnection,'post',post)
    result=s.api.post('/api/documents/upload',files={'files':('scan.pdf',scan(),'application/pdf')},data={'dataset_id':d['id'],'allow_external':'true'})
    assert result.status_code==200,result.text
    doc=result.json()['documents'][0]
    choose(s,d,full)
    assert worker.run_once()
    parsed=core.store.json('documents/'+doc['id']+'/parsed.json')
    assert sent==['gpt-4o-mini'] and parsed['ocr']['model']=='gpt-4o-mini'
    assert s.api.get('/api/documents/'+doc['id']).json()['status']=='ready'
    current=routing.execution_snapshot(routing.owned(d['id'],s.owner,'knowledge_base'),'embedding')
    assert current['ocr_execution']['model_id']==full['id']
    notices=agent_consent.notices(current,'embedding',main)
    assert any(n['title']=='OpenAI OCR' for n in notices)


def test_cloud_ocr_eligibility_excludes_chat_and_embedding_registrations(system):
    s=system
    for category,model in [('chat','gpt-4o'),('embedding','text-embedding-3-small')]:
        assert not register(s,body(category,'openai-compatible',provider_model=model))['ocr_eligible']
