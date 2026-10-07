"""A tag changing its installed weights cannot reuse a previous vector space."""
import pytest
from app import core,providers,ollama_provider as ollama,worker
from test_dataset_models import system,dataset,upload,conversation,message

def test_digest_changes_retrieval_requires_reindex_without_deleting_original(system,monkeypatch):
    s=system;current={'digest':'a'*64}
    monkeypatch.setattr(ollama,'model_digest',lambda name:current['digest'])
    monkeypatch.setattr(ollama,'embed',lambda model,texts,timeout:[[1.,0.,0.] for _ in texts])
    r=s.api.patch('/api/settings',json={'model_provider':'ollama','model':'qwen3:4b','embedding_provider':'ollama','embedding_model':'nomic-embed-text','search_provider':'local'});assert r.status_code==200
    d=dataset(s);doc=upload(s,d)['documents'][0];did=doc['id'];original=core.store.get('documents/'+did+'/original')
    assert not s.api.get('/api/documents/'+did).json()['requires_reindex']
    old=core.store.json('documents/'+did+'/index.json');assert old['embedding_digest']=='a'*64
    current['digest']='b'*64
    assert s.api.get('/api/documents/'+did).json()['requires_reindex']
    assert message(s,conversation(s,d,[did])).status_code==409
    assert core.store.get('documents/'+did+'/original')==original
    assert s.api.post('/api/documents/'+did+'/reindex',json={}).status_code==200;assert worker.run_once()
    new=core.store.json('documents/'+did+'/index.json');assert new['fingerprint']!=old['fingerprint'] and new['embedding_digest']=='b'*64
    assert not s.api.get('/api/documents/'+did).json()['requires_reindex']

def test_mid_inference_weight_swap_is_rejected(monkeypatch):
    digests=iter(['a'*64,'b'*64]);monkeypatch.setattr(ollama,'model_digest',lambda name:next(digests));monkeypatch.setattr(ollama,'embed',lambda *args:[[1.,0.,0.]])
    with core.execution_context({'settings':core.DEFAULTS|{'embedding_provider':'ollama','embedding_model':'nomic-embed-text','_embedding_digest':'a'*64}}):
        with pytest.raises(providers.ProviderError,match='changed during'):providers.embed(['safe sample'])
