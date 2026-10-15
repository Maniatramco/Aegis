"""Cloud-only knowledge retrieval must use the selected dataset's embedding space."""
import copy
import pytest
from ags_app import core, knowledge, relational, dataset_models as routing
from test_dataset_models import system, dataset


@pytest.mark.parametrize('provider', ['registered', 'openai'])
def test_cloud_embedding_indexes_and_searches_without_local_fallback(system, monkeypatch, provider):
    s = system
    selected = dataset(s, 'Cloud knowledge')
    dataset(s, 'Local models unavailable')
    real_snapshot = routing.embedding_snapshot
    secret_refs = {'connection': 'secrets/profiles/cloud/connection.enc'}

    def snapshot(record):
        assert record.id == selected['id'], 'Must not fall back to another dataset or local model'
        value = copy.deepcopy(real_snapshot(record))
        value['settings'].update(embedding_provider=provider, embedding_model='cloud-embedding')
        value['secret_refs'] = secret_refs
        return value

    monkeypatch.setattr(routing, 'embedding_snapshot', snapshot)
    calls = []
    def embed(texts, query=False):
        cfg = core.settings()
        assert cfg['embedding_provider'] == provider
        assert cfg['embedding_model'] == 'cloud-embedding'
        assert cfg['_index_namespace'] == 'unified-knowledge-v1'
        calls.append(query)
        return [[1.0, 0.0, 0.0] for _ in texts]
    monkeypatch.setattr(knowledge.providers, 'embed', embed)
    result = knowledge.search('Cloud knowledge', s.owner, selected['id'], source_types=['dataset'])
    assert result['matches'] and {m['dataset_id'] for m in result['matches']} == {selected['id']}
    assert False in calls and True in calls  # Both index publication and query use cloud.
    assert knowledge.embedding_snapshot(s.owner, selected['id'])['secret_refs'] == secret_refs


def test_managed_retrieval_is_not_silently_treated_as_client_embeddings(system, monkeypatch):
    s = system
    selected = dataset(s)
    real_snapshot = routing.embedding_snapshot
    def snapshot(record):
        value = real_snapshot(record)
        value['settings'].update(embedding_provider='registered', search_provider='oci')
        return value
    monkeypatch.setattr(routing, 'embedding_snapshot', snapshot)
    with pytest.raises(knowledge.HTTPException) as error:
        knowledge.embedding_snapshot(s.owner, selected['id'])
    assert error.value.status_code == 409


def test_background_publication_uses_each_dataset_mapping_and_isolates_failures(system, monkeypatch):
    s = system
    one, two = dataset(s, 'Unavailable local'), dataset(s, 'Available cloud')
    with core.Session.begin() as db:
        if not db.get(core.User, s.owner):
            db.add(core.User(id=s.owner, username='test-owner', password_hash='unused'))
        for item in (one, two):
            db.add(relational.UserDataset(user_id=s.owner, dataset_id=item['id'], enabled=True))
    calls = []
    def sync(actor, dataset_id='', **kwargs):
        assert actor == s.owner and dataset_id
        calls.append(dataset_id)
        if dataset_id == one['id']:
            raise knowledge.providers.ProviderError('Local model unavailable')
    monkeypatch.setattr(knowledge, 'sync', sync)
    knowledge.reconcile()
    assert set(calls) == {one['id'], two['id']}


def test_unavailable_selected_embedding_never_borrows_another_dataset_provider(system, monkeypatch):
    s = system
    selected = dataset(s, 'Unavailable model')
    dataset(s, 'Other cloud provider')
    calls = []
    def snapshot(record):
        calls.append(record.id)
        raise knowledge.HTTPException(409, 'Selected model unavailable')
    monkeypatch.setattr(routing, 'embedding_snapshot', snapshot)
    with pytest.raises(knowledge.HTTPException):
        knowledge.embedding_snapshot(s.owner, selected['id'])
    assert calls == [selected['id']]
