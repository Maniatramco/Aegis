"""Read-only installation discovery and opt-in public-document local inference."""
import os
from pathlib import Path
import httpx
import pytest
from app import core, ollama_provider as ollama, worker
from test_dataset_models import system,dataset,model,mapping,post

def test_installed_metadata_is_readonly_loopback(monkeypatch):
    original=httpx.Client
    def handle(request):
        assert request.method=='GET' and str(request.url)==ollama.base_url()+'/api/tags'
        return httpx.Response(200,json={'models':[{'name':'qwen3:4b','digest':'synthetic','size':42},{'name':'cloud-model'}]})
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(ollama.httpx,'Client',client)
    assert ollama.installed()=={'available':True,'models':[{'name':'qwen3:4b','digest':'synthetic','size':42}]}

def test_missing_daemon_is_explicit(monkeypatch):
    def fail(**kwargs):raise httpx.ConnectError('Synthetic offline')
    monkeypatch.setattr(ollama.httpx,'Client',fail)
    assert ollama.installed()=={'available':False,'models':[]}

@pytest.mark.skipif(os.getenv('AEGIS_TEST_PUBLIC_OLLAMA')!='true',reason='Opt-in local models and downloaded public RFC8259 required')
def test_public_rfc_two_models_same_index_saved_chat(system,monkeypatch):
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true');system.owner='Dottie'
    raw=Path(os.environ['AEGIS_PUBLIC_SAMPLE']).read_bytes()
    assert b'The JavaScript Object Notation (JSON)' in raw
    result=system.api.patch('/api/settings',json={'model_provider':'ollama','model':'qwen3:4b','embedding_provider':'ollama','embedding_model':'nomic-embed-text','search_provider':'local','storage_provider':'local','timeout':180,'top_k':3,'chunk_size':800,'chunk_overlap':100})
    assert result.status_code==200,result.text
    d=dataset(system,'Dottie public RFC8259')
    qwen=next(m for m in d['models'] if 'chat' in m['capabilities'])
    small=model(system,qwen['connection_profile_id'],'SmolLM2 lightweight',caps=['chat'],provider_model='smollm2:1.7b-instruct-q4_K_M')
    mapped=mapping(system,d,mappings=d['mappings']+[{'model_id':small['id'],'enabled':True}])
    assert mapped['index_generation']==d['index_generation']
    result=system.api.post('/api/documents/upload',files={'files':('RFC8259-public.txt',raw,'text/plain')},data={'dataset_id':d['id']})
    assert result.status_code==200,result.text
    doc=result.json()['documents'][0];assert worker.run_once()
    assert system.api.get('/api/documents/'+doc['id']).json()['status']=='ready'
    index_before=core.store.get('documents/'+doc['id']+'/index.json')
    conversation=post(system,'/api/conversations',{'dataset_id':d['id'],'document_ids':[doc['id']]})
    for selected in (qwen,small):
        answer=system.api.post('/api/conversations/'+conversation['id']+'/messages',json={'text':'Which character encoding MUST JSON text use when exchanged between systems that are not part of a closed ecosystem? Cite the source.','dataset_id':d['id'],'document_ids':[doc['id']],'model_id':selected['id']})
        assert answer.status_code==200,answer.text
        message=answer.json()['message']
        assert 'UTF-8' in message['text'],message['text']
        assert message['citations'] and all(c['document_id']==doc['id'] for c in message['citations']),message['text']
        assert message['model_selection']['model_id']==selected['id']
        print(selected['provider_model']+': grounded UTF-8 answer with citations passed')
    assert core.store.get('documents/'+doc['id']+'/index.json')==index_before
    assert len(system.api.get('/api/conversations').json())==1
    empty=dataset(system,'Dottie no-evidence fixture')
    empty_conversation=post(system,'/api/conversations',{'dataset_id':empty['id']})
    result=system.api.post('/api/conversations/'+empty_conversation['id']+'/messages',json={'text':"What is Dottie's birthday?",'dataset_id':empty['id']})
    assert result.status_code==200 and not result.json()['message']['citations']
    assert 'evidence' in result.json()['message']['text'].lower()


@pytest.mark.parametrize('port',['11434','11435'])
def test_endpoint_is_fixed_loopback(monkeypatch,port):
    monkeypatch.setenv('AEGIS_OLLAMA_PORT',port)
    assert ollama.base_url()=='http://127.0.0.1:'+port

@pytest.mark.parametrize('value',['443','http://example.com','11435/path','11435@evil',''])
def test_invalid_model_endpoint_rejected(monkeypatch,value):
    monkeypatch.setenv('AEGIS_OLLAMA_PORT',value)
    with pytest.raises(ollama.OllamaError):ollama.base_url()
