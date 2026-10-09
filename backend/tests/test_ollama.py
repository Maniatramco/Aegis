"""Ollama contracts and opt-in real local inference; no paid provider calls."""
import hashlib
import os
import httpx
import pytest
from app import core,providers,ollama_provider as ollama,worker
from test_dataset_models import system,dataset,conversation,post

@pytest.mark.parametrize('name',['qwen3:4b-cloud','https://evil/model','host/model','../model','',None])
def test_remote_model_names_rejected(name):
    with pytest.raises(ollama.OllamaError):ollama.local_model_name(name)

def test_loopback_transport_ignores_proxy_and_credentials(monkeypatch):
    original=httpx.Client;seen=[]
    def handle(request):
        seen.append(request)
        assert str(request.url)=='http://127.0.0.1:11434/api/embed'
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'embeddings':[[3,4]]})
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(ollama.httpx,'Client',client)
    assert ollama.embed('nomic-embed-text',['synthetic'],30)==[[0.6,0.8]]
    assert len(seen)==1

@pytest.mark.parametrize('vectors',[[],[[0,0]],[[float('nan'),1]],[[1,2],[3]],'invalid'])
def test_bad_embeddings_fail_closed(monkeypatch,vectors):
    monkeypatch.setattr(ollama,'request',lambda *a:{'embeddings':vectors})
    with pytest.raises(ollama.OllamaError):ollama.embed('nomic-embed-text',['sample'],30)

def test_schema_and_incomplete_output_rejected(monkeypatch):
    schema={'type':'object','properties':{'count':{'type':'integer'}},'required':['count']}
    monkeypatch.setattr(ollama,'request',lambda *a:{'done':True,'message':{'content':'{"count":"bad"}'}})
    with pytest.raises(ollama.OllamaError):ollama.extract('qwen3:4b','Synthetic',schema,30)
    monkeypatch.setattr(ollama,'request',lambda *a:{'done':True,'done_reason':'length','message':{'content':'truncated'}})
    with pytest.raises(ollama.OllamaError):ollama.chat('qwen3:4b','Q',[{'document_name':'x','text':'x'}],[],30)


def test_qwen_legacy_thinking_template_returns_only_completed_answer(monkeypatch):
    monkeypatch.setattr(ollama,'request',lambda *a:{'done':True,'done_reason':'stop',
        'message':{'content':'Internal analysis\n</think>\nKeep the approved version. [1]'}})
    assert ollama.chat('qwen3:4b','What if validation fails?',
        [{'document_name':'workflow','text':'Keep the approved version on failure.'}],[],30)=='Keep the approved version. [1]'
    monkeypatch.setattr(ollama,'request',lambda *a:{'done':True,'done_reason':'length',
        'message':{'content':'Internal analysis\n</think>\nPartial answer [1]'}})
    with pytest.raises(ollama.OllamaError):
        ollama.chat('qwen3:4b','Q',[{'document_name':'x','text':'x'}],[],30)


def test_extraction_reserves_space_for_late_document_facts(monkeypatch):
    text='Synthetic document content. '*600+'The last named service is Late Service.'
    schema={'type':'object','properties':{'service':{'type':'string','description':'The last explicitly named software service, not a workflow action'}},'required':['service']}
    def response(path,payload,timeout):
        assert 'Late Service.' in payload['messages'][1]['content']
        assert payload['messages'][-1]['content']=='<think>\n</think>\n\n'
        assert 'not a workflow action' in payload['messages'][0]['content']
        assert payload['options']['num_ctx']>=16384
        assert payload['options']['num_predict']>=4096
        return {'done':True,'message':{'content':'{"service":"Late Service"}'}}
    monkeypatch.setattr(ollama,'request',response)
    assert ollama.extract('qwen3:4b',text,schema,30)=={'service':'Late Service'}


def test_oversized_local_context_rejected_before_inference(monkeypatch):
    def forbidden(*args):raise AssertionError('Must not silently truncate the document')
    monkeypatch.setattr(ollama,'request',forbidden)
    with pytest.raises(ollama.OllamaError,match='context budget'):
        ollama.extract('qwen3:4b','Synthetic '*20000,{'type':'object'},30)


def test_local_array_extraction_covers_later_chunks_and_deduplicates(monkeypatch):
    monkeypatch.setattr(providers,'settings',lambda:core.DEFAULTS|{'model_provider':'ollama'})
    schema={'type':'object','properties':{'subject':{'type':'string'},'services':{'type':'array','items':{'type':'string'},'description':'Named software services'}},'required':['subject','services']}
    names=['Early Service','Second Service','Third Service','Fourth Service','Late Service']
    sources=[{'id':str(i),'page':1,'document_id':'doc','document_name':'Synthetic','text':name+'; Copy the file'} for i,name in enumerate(names)]
    calls=[]
    def extract(text,wrapper):
        calls.append(text)
        if 'data' in wrapper['properties']:
            return {'data':{'subject':'Synthetic subject'},'evidence':[{'field':'Prose, not a pointer','chunk_id':'0','quote':'Early Service'},{'field':'/missing','chunk_id':'0','quote':'Early Service'}]}
        service=next(name for i,name in enumerate(names) if 'chunk '+str(i)+';' in text)
        return {'services':[service,service,'Invented service']}
    monkeypatch.setattr(providers,'extract',extract)
    result,evidence=providers.extract_with_evidence('All chunks',schema,sources)
    assert result=={'subject':'Synthetic subject','services':names}
    assert {item['quote'] for item in evidence}==set(names)
    assert {item['field'] for item in evidence}=={'/services/'+str(i) for i in range(5)}
    assert len(calls)==6

def test_fingerprints_preserve_existing_spaces_and_separate_ollama():
    cfg=core.DEFAULTS|{'search_provider':'local','embedding_provider':'mock'}
    assert providers.fingerprint(cfg)==hashlib.sha256(b'mock:mock-sha256-v1').hexdigest()[:16]
    cfg.update(embedding_provider='openai',embedding_model='text-embedding-3-small')
    old=providers.fingerprint(cfg)
    assert old==hashlib.sha256(b'openai:text-embedding-3-small').hexdigest()[:16]
    cfg['embedding_provider']='ollama'
    assert providers.fingerprint(cfg)!=old
    first=providers.fingerprint(cfg);cfg['embedding_model']='nomic-embed-text'
    assert providers.fingerprint(cfg)!=first
    first=providers.fingerprint(cfg);cfg['_index_namespace']='dataset:2'
    assert providers.fingerprint(cfg)!=first

def test_local_only_rejects_cloud_settings_and_pinned_execution(system,monkeypatch):
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    r=system.api.patch('/api/settings',json={'model_provider':'openai'})
    assert r.status_code==400
    r=system.api.patch('/api/settings',json={'api_key':'synthetic-not-a-key'})
    assert r.status_code==400
    with core.execution_context({'settings':core.DEFAULTS|{'model_provider':'openai'}}):
        with pytest.raises(ValueError,match='Local-only'):core.settings()

@pytest.mark.parametrize('change',[{'embedding_provider':'openai'},{'storage_provider':'oci'},{'search_provider':'qdrant'},{'queue_provider':'oci'}])
def test_local_only_blocks_other_external_services(system,monkeypatch,change):
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    assert system.api.patch('/api/settings',json=change).status_code==400

def test_unavailable_ollama_never_falls_back(monkeypatch):
    monkeypatch.setattr(providers,'settings',lambda:core.DEFAULTS|{'model_provider':'ollama','model':'qwen3:4b'})
    def unavailable(*args):raise ollama.OllamaError('Local Ollama unavailable')
    def forbidden(*args):raise AssertionError('Paid fallback must never run')
    monkeypatch.setattr(ollama,'chat',unavailable)
    monkeypatch.setattr(providers,'openai_request',forbidden)
    with pytest.raises(providers.ProviderError,match='unavailable'):
        providers.answer('Question',[{'document_name':'synthetic','text':'Synthetic fact'}])

def test_ollama_routing_upload_chat_extraction(system,monkeypatch):
    monkeypatch.setattr(ollama,'model_digest',lambda name:'a'*64)
    def response(path,payload,timeout):
        if path=='/api/embed':return {'embeddings':[[1.,0.,0.] for _ in payload['input']]}
        if 'format' in payload:return {'done':True,'message':{'content':'{"data":{"owner":"Alice"},"evidence":[]}'}}
        return {'done':True,'message':{'content':'Alice owns the project. [1]'}}
    monkeypatch.setattr(ollama,'request',response)
    run_workflow(system)

def run_workflow(s):
    r=s.api.patch('/api/settings',json={'model_provider':'ollama','model':'qwen3:4b','embedding_provider':'ollama',
        'embedding_model':'nomic-embed-text','search_provider':'local','storage_provider':'local','timeout':180,'top_k':3,'chunk_size':800,'chunk_overlap':100})
    assert r.status_code==200,r.text
    d=dataset(s,'Synthetic local Ollama test')
    r=s.api.post('/api/documents/upload',files={'files':('synthetic.txt',b'Alice owns Project Cobalt. The launch code is COBALT-420. The budget is 42 USD.','text/plain')},data={'dataset_id':d['id']})
    assert r.status_code==200,r.text
    doc=r.json()['documents'][0]
    assert worker.run_once()
    status=s.api.get('/api/documents/'+doc['id']).json();assert status['status']=='ready',status
    c=conversation(s,d,[doc['id']])
    r=s.api.post('/api/conversations/'+c['id']+'/messages',json={'text':'Who owns Project Cobalt? Cite the source.','allow_external':False})
    assert r.status_code==200,r.text
    reply=r.json()['message'];assert 'Alice' in reply['text'];assert not reply['mock'];assert reply['citations']
    assert reply['model_selection']['model_provider']=='ollama'
    stream=s.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Who owns Project Cobalt? Cite the source.','allow_external':False})
    assert stream.status_code==200 and 'event: error' not in stream.text
    assert 'event: delta' in stream.text and 'event: done' in stream.text and 'Alice' in stream.text
    schema={'type':'object','properties':{'owner':{'type':'string'}},'required':['owner'],'additionalProperties':False}
    template=post(s,'/api/templates',{'name':'Synthetic owner','schema':schema})
    ext=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':template['id'],'allow_external':False})
    assert worker.run_once()
    result=s.api.get('/api/extractions/'+ext['id']).json();assert result['status']=='ready',result
    assert result['result']['owner']=='Alice'

@pytest.mark.skipif(os.getenv('AEGIS_TEST_OLLAMA')!='true',reason='Opt-in: requires installed local qwen3:4b and nomic-embed-text')
def test_real_ollama_end_to_end(system,monkeypatch):
    monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    run_workflow(system)


def test_configured_context_allows_large_input_and_never_exceeds_non_power_of_two_limit(monkeypatch):
    messages=[{'role':'user','content':'x'*70000}]
    monkeypatch.setattr(core,'settings',lambda:{'context_limit':32768})
    with pytest.raises(ollama.OllamaError,match='32,768'):ollama.generation_options(messages,4096)
    monkeypatch.setattr(core,'settings',lambda:{'context_limit':48000})
    options=ollama.generation_options(messages,4096)
    assert options['num_ctx']==48000 and options['num_predict']==4096
    assert messages[0]['content']=='x'*70000
    monkeypatch.setattr(core,'settings',lambda:{'context_limit':65536})
    assert ollama.generation_options(messages,4096)['num_ctx']==65536


def test_context_budget_includes_output_reservation_and_keeps_legacy_default(monkeypatch):
    messages=[{'role':'user','content':'x'*8000}]
    monkeypatch.setattr(core,'settings',lambda:{'context_limit':8192})
    with pytest.raises(ollama.OllamaError,match='including the answer'):ollama.generation_options(messages,4096)
    monkeypatch.setattr(core,'settings',lambda:{})
    assert ollama.generation_options([{'role':'user','content':'Short question'}],4096)['num_ctx']==8192


def test_per_model_output_and_extra_parameters_used_for_chat_extraction_and_embeddings(monkeypatch):
    cfg={'context_limit':16384,'max_output_tokens':256,'extra_parameters':{'temperature':0.5,'top_p':0.6,'seed':7,'keep_alive':'2m'},'embedding_context_limit':32,'embedding_extra_parameters':{'keep_alive':'1m'}}
    monkeypatch.setattr(core,'settings',lambda:cfg)
    sent=[]
    def response(path,payload,timeout):
        sent.append((path,payload))
        return {'embeddings':[[1,2,3]]} if path=='/api/embed' else {'done':True,'done_reason':'stop','message':{'content':'{"status":"ready"}'}}
    monkeypatch.setattr(ollama,'request',response)
    ollama.chat('qwen3:4b','Status?',[{'document_name':'test','text':'ready'}],[],60)
    ollama.extract('qwen3:4b','ready',{'type':'object','properties':{'status':{'type':'string'}}},60)
    ollama.embed('nomic-embed-text',['test'],60)
    for _,payload in sent[:2]:
        assert payload['options']['num_predict']==256 and payload['options']['temperature']==0.5 and payload['options']['seed']==7
        assert payload['keep_alive']=='2m' and 'keep_alive' not in payload['options']
    assert sent[2][1]['keep_alive']=='1m' and sent[2][1]['truncate'] is False
    with pytest.raises(ollama.OllamaError,match='embedding input budget'):ollama.embed('nomic-embed-text',['x'*80],60)
    assert len(sent)==3
