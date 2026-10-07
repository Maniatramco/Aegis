import os
from types import SimpleNamespace
import pytest
from app import core, providers, reranker
from test_dataset_models import system, dataset, upload, conversation


def candidates(count):
    return [{'chunk_id':str(i),'document_id':'allowed','text':f'Passage {i}','score':1-i/100} for i in range(count)]


def test_reranking_promotes_candidate_outside_original_top_five(monkeypatch):
    monkeypatch.setenv('AEGIS_RERANKER','local')
    monkeypatch.setenv('AEGIS_RERANK_CANDIDATES','25')
    pool=candidates(30)
    seen=[]
    def retrieve(query,owner,docs,limit):
        seen.append(limit);return pool[:limit]
    monkeypatch.setattr(providers,'_retrieve',retrieve)
    monkeypatch.setattr(reranker,'predict',lambda query,texts:[100 if text=='Passage 20' else 0 for text in texts])
    trace={};result=providers.search('Question','alice',[object()],5,trace)
    assert seen==[25] and len(result)==5
    assert result[0]['chunk_id']=='20' and result[0]['retrieval_rank']==21
    assert result[0]['score']==.8 and result[0]['rerank_score']==100
    assert trace['candidate_count']==25 and trace['returned_count']==5
    assert trace['sorted_by']=='rerank_score'
    assert pool[20].get('rerank_score') is None # Canonical inputs are not mutated.


def test_disabled_reranker_preserves_vector_ranking(monkeypatch):
    monkeypatch.setenv('AEGIS_RERANKER','none')
    monkeypatch.setattr(reranker,'predict',lambda *args:pytest.fail('Disabled reranker was called'))
    monkeypatch.setattr(providers,'_retrieve',lambda q,o,d,k:candidates(k))
    trace={};result=providers.search('Question','alice',[object()],3,trace)
    assert [item['chunk_id'] for item in result]==['0','1','2']
    assert trace['candidate_limit']==3 and not trace['enabled']


@pytest.mark.parametrize('value',['0','101','not-an-integer'])
def test_candidate_limit_rejects_invalid_configuration(monkeypatch,value):
    monkeypatch.setenv('AEGIS_RERANK_CANDIDATES',value)
    with pytest.raises(reranker.RerankerError):reranker.candidate_limit(5)


def test_candidate_pool_never_smaller_than_requested_output(monkeypatch):
    monkeypatch.setenv('AEGIS_RERANK_CANDIDATES','3')
    assert reranker.candidate_limit(5)==5


@pytest.mark.parametrize('scores',[[float('nan')],[float('inf')],[]])
def test_invalid_scores_fail_without_silent_vector_fallback(monkeypatch,scores):
    monkeypatch.setattr(reranker,'predict',lambda *args:scores)
    with pytest.raises(reranker.RerankerError,match='invalid scores'):reranker.rank('Question',candidates(1),1)


def test_missing_and_corrupt_model_assets_are_rejected(tmp_path):
    with pytest.raises(reranker.RerankerError,match='missing'):reranker.verify_assets(tmp_path)
    (tmp_path/'onnx').mkdir();(tmp_path/'onnx/model.onnx').write_bytes(b'not the model')
    (tmp_path/'tokenizer.json').write_bytes(b'{}')
    with pytest.raises(reranker.RerankerError,match='integrity'):reranker.verify_assets(tmp_path)


def test_provider_reports_reranker_failure(monkeypatch):
    monkeypatch.setenv('AEGIS_RERANKER','local')
    monkeypatch.setattr(providers,'_retrieve',lambda *args:candidates(1))
    def fail(*args):raise reranker.RerankerError('Synthetic reranker failure')
    monkeypatch.setattr(reranker,'predict',fail)
    with pytest.raises(providers.ProviderError,match='Synthetic reranker failure'):
        providers.search('Question','alice',[object()],5)


def test_reranker_only_receives_permitted_document_text(system,monkeypatch):
    d=dataset(system);doc=upload(system,d)['documents'][0]
    system.owner='bob';other=dataset(system);foreign=upload(system,other)['documents'][0]
    system.owner='alice'
    allowed=SimpleNamespace(id=doc['id'],name='Allowed')
    forbidden=SimpleNamespace(id=foreign['id'],name='Foreign')
    received=[]
    def predict(query,texts):received.extend(texts);return [1]*len(texts)
    monkeypatch.setenv('AEGIS_RERANKER','local');monkeypatch.setattr(reranker,'predict',predict)
    snapshot=core.store.json('documents/'+doc['id']+'/index-execution.json')
    with core.execution_context(snapshot):result=providers.search('Who is the owner?','alice',[allowed,forbidden],5)
    assert received and {item['document_id'] for item in result}=={doc['id']}
    assert len(received)==len(core.store.json('documents/'+doc['id']+'/chunks.json')['chunks'])


def test_chat_and_diagnostics_use_the_reranking_stage(system,monkeypatch):
    d=dataset(system);upload(system,d);c=conversation(system,d)
    received=[]
    monkeypatch.setenv('AEGIS_RERANKER','local')
    def predict(query,texts):received.append(query);return [9]*len(texts)
    monkeypatch.setattr(reranker,'predict',predict)
    diagnostic=system.api.post('/api/index/search',json={'dataset_id':d['id'],'text':'Find the owner','allow_external':True})
    assert diagnostic.status_code==200,diagnostic.text
    data=diagnostic.json();assert data['reranking']['enabled'] and data['reranking']['candidate_count']==1
    assert data['matches'][0]['rerank_score']==9
    answer=system.api.post('/api/conversations/'+c['id']+'/messages/stream',json={'text':'Who owns it?','allow_external':True})
    assert answer.status_code==200 and 'event: done' in answer.text and 'event: error' not in answer.text
    assert received==['Find the owner','Who owns it?']
    assert 'rerank_model' in answer.text


@pytest.mark.skipif(os.getenv('AEGIS_TEST_RERANKER')!='true',reason='Opt-in: requires the pinned local ONNX reranker')
def test_real_local_model_prefers_answer_and_handles_long_questions(monkeypatch):
    import socket
    def no_network(*args,**kwargs):raise AssertionError('Inference attempted to access the network')
    monkeypatch.setattr(socket.socket,'connect',no_network)
    monkeypatch.setenv('AEGIS_RERANKER','local')
    scored=reranker.rank('Who owns Project Cobalt?',[
        {'text':'The launch code is COBALT-420.','chunk_id':'launch'},
        {'text':'Alice owns Project Cobalt.','chunk_id':'owner'},
        {'text':'Project Cobalt has a 42 USD budget.','chunk_id':'budget'}],3)
    assert scored[0]['chunk_id']=='owner'
    assert len(reranker.predict('question '*1500,['Evidence '*2000]))==1
    assert reranker.status()['ready']
