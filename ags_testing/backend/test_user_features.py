"""Real authenticated feature grants: defaults, administrator control and revocation."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ags_app import core, main, relational, governance, governance_audit, user_features
from test_dataset_models import system
from test_user_management import accounts, login, OLD


@pytest.fixture
def pilot(accounts):
    with core.Session.begin() as session:
        session.add(core.User(id='pilot', username='mani', role='administrator', password_hash=core.password_hash(OLD)))
        session.add(core.User(id='case-variant', username='Mani', role='administrator', password_hash=core.password_hash(OLD)))
    return accounts


def change(client, target, enabled, version=0, **extra):
    return client.put('/api/users/' + target + '/features', json={
        'features': {'data_governance': enabled}, 'expected_version': version, 'current_password': OLD, **extra})


def test_only_exact_mani_defaults_to_enabled_and_admin_has_no_implicit_access(pilot):
    login(pilot)
    users = {user['username']: user for user in pilot.get('/api/users').json()}
    assert [name for name, user in users.items() if user['features']['data_governance']] == ['mani']
    assert pilot.get('/api/auth/me').json()['user']['features'] == {'data_governance': False}
    assert pilot.get('/api/governance/catalog').status_code == 403
    login(pilot, 'mani')
    assert pilot.get('/api/auth/me').json()['user']['features'] == {'data_governance': True}
    assert pilot.get('/api/governance/catalog').status_code == 200


def test_every_governance_route_is_denied_before_handler_work_for_disabled_admin(pilot, monkeypatch):
    login(pilot)
    def unexpected(*args, **kwargs):
        pytest.fail('Disabled governance request reached its handler')
    monkeypatch.setattr(governance, 'catalog', unexpected)
    routes = [(method, route.path.replace('{id}', 'unavailable')) for route in main.app.routes
              if getattr(route, 'path', '').startswith('/api/governance/') for method in route.methods if method in {'GET', 'PUT', 'POST'}]
    assert len(routes) >= 19
    for method, path in routes:
        response = pilot.request(method, path, json={})
        assert response.status_code == 403, (method, path, response.text)
    assert not any(path.name == 'governance' for path in core.DATA.iterdir())


def test_admin_without_governance_can_grant_and_revoke_an_existing_session(pilot):
    login(pilot)
    with TestClient(main.app) as colleague:
        login(colleague, 'Colleague')
        assert colleague.get('/api/governance/catalog').status_code == 403
        granted = change(pilot, 'colleague', True)
        assert granted.status_code == 200, granted.text
        assert granted.json()['user']['feature_access_version'] == 1
        assert colleague.get('/api/auth/me').json()['user']['features']['data_governance'] is True
        assert colleague.get('/api/governance/catalog').status_code == 200
        assert colleague.post('/api/governance/oci/publish', json={'dataset_ids': ['unassigned']}).status_code == 403
        assert change(colleague, 'colleague', True, 1).status_code == 403
        assert change(pilot, 'colleague', False, 1).status_code == 200
        assert colleague.get('/api/auth/me').json()['user']['features']['data_governance'] is False
        assert colleague.get('/api/governance/catalog').status_code == 403
        assert colleague.get('/api/datasets').status_code == 200


def test_mani_can_be_disabled_and_cannot_restore_access_without_an_admin(pilot):
    login(pilot)
    assert change(pilot, 'pilot', False).status_code == 200
    login(pilot, 'mani')
    assert pilot.get('/api/auth/me').json()['user']['features']['data_governance'] is False
    assert pilot.get('/api/governance/catalog').status_code == 403
    # The administrator control is independent of the module entitlement.
    assert change(pilot, 'pilot', True, 1).status_code == 200
    assert pilot.get('/api/governance/catalog').status_code == 200


def test_feature_changes_require_csrf_current_password_and_current_version(pilot):
    login(pilot)
    assert change(pilot, 'colleague', True, current_password='incorrect').status_code == 400
    assert change(pilot, 'colleague', True).status_code == 200
    assert change(pilot, 'colleague', False).status_code == 409
    pilot.headers.pop('X-CSRF-Token')
    assert change(pilot, 'colleague', False, 1).status_code == 403
    assert user_features.governance_enabled('colleague') is True
    with TestClient(main.app) as anonymous:
        assert change(anonymous, 'colleague', True).status_code == 401


@pytest.mark.parametrize('extra', [
    {'features': {'data_governance': 'true'}}, {'features': {'data_governance': True, 'administrator': True}},
    {'expected_version': True}, {'current_password': ''}, {'role': 'administrator'},
])
def test_invalid_feature_payload_cannot_broaden_access(pilot, extra):
    login(pilot)
    result = change(pilot, 'colleague', True, **extra)
    assert result.status_code == 422, result.text
    assert OLD not in result.text
    assert not user_features.governance_enabled('colleague')


def test_grant_does_not_assign_datasets_or_administrator_role(pilot):
    login(pilot)
    dataset = pilot.post('/api/datasets', json={'name': 'Protected existing dataset'}).json()
    assert change(pilot, 'colleague', True).status_code == 200
    login(pilot, 'Colleague')
    assert pilot.get('/api/datasets').json() == []
    assert pilot.get('/api/governance/catalog', params={'dataset_id': dataset['id']}).status_code == 404
    with core.Session.begin() as session:
        assert session.get(core.User, 'colleague').role == 'user'
        session.add(relational.UserDataset(user_id='colleague', dataset_id=dataset['id'], enabled=True))
    catalog = pilot.get('/api/governance/catalog', params={'dataset_id': dataset['id']})
    assert catalog.status_code == 200 and catalog.json()['totals']['datasets'] == 1
    assert catalog.json()['can_manage'] is False


def test_missing_anchored_feature_snapshot_fails_closed(pilot):
    login(pilot)
    dataset = pilot.post('/api/datasets', json={'name': 'Available metadata'}).json()
    assert change(pilot, 'pilot', False).status_code == 200
    with core.Session() as session:
        reference = session.get(core.Record, user_features.record_id('pilot')).ref
    path = core.local_store.path(reference)
    path.rename(path.with_suffix('.unavailable'))
    with pytest.raises(Exception, match='Feature access could not be verified'):
        user_features.governance_enabled('pilot')
    login(pilot, 'mani')
    me = pilot.get('/api/auth/me')
    assert me.status_code == 200 and me.json()['user']['feature_access_available'] is False
    assert me.json()['user']['features']['data_governance'] is False
    assert pilot.get('/api/governance/catalog').status_code == 503
    directory = pilot.get('/api/users')
    assert directory.status_code == 200
    assert next(user for user in directory.json() if user['id'] == 'pilot')['feature_access_available'] is False
    graph = pilot.get('/api/metadata-relationships', params={'dataset_id': dataset['id'], 'level': 'instances'})
    assert graph.status_code == 200
    assert all('Classification' not in node['attributes'] for node in graph.json()['nodes'])
    # It must not fall back to mani's initial enabled state.
    assert change(pilot, 'pilot', True, 1).status_code == 503


def test_grant_is_audited_without_password_and_removed_with_deleted_account(pilot):
    login(pilot)
    assert change(pilot, 'colleague', True).status_code == 200
    with core.Session() as session:
        record = session.get(core.Record, user_features.record_id('colleague'))
        assert record.created_by == record.updated_by == 'administrator'
        saved = core.local_store.get(record.ref)
        assert OLD.encode() not in saved
    assert OLD not in json.dumps(governance_audit._events())
    result = pilot.request('DELETE', '/api/users/colleague', json={'username': 'Colleague', 'current_password': OLD})
    assert result.status_code == 200, result.text
    with core.Session() as session:
        assert session.get(core.Record, user_features.record_id('colleague')) is None
    recreated = pilot.post('/api/users', json={'username': 'Colleague', 'password': OLD, 'confirmation': OLD}).json()
    assert recreated['features']['data_governance'] is False


def test_mid_request_revocation_does_not_release_governance_response(pilot, monkeypatch):
    login(pilot, 'mani')
    original = governance.catalog
    def revoke_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        user_features.save('administrator', 'pilot', {'data_governance': False}, 0)
        return result
    monkeypatch.setattr(governance, 'catalog', revoke_after_read)
    response = pilot.get('/api/governance/catalog')
    assert response.status_code == 403 and 'items' not in response.json()
    assert any(event['http_status'] == 403 for event in governance_audit._events())


def test_mid_save_revocation_prevents_policy_publication(pilot, monkeypatch):
    login(pilot, 'mani')
    dataset = pilot.post('/api/datasets', json={'name': 'Pilot dataset'}).json()
    original = core.store.put_json
    def revoke_after_snapshot(reference, value):
        original(reference, value)
        if reference.startswith('governance/'):
            user_features.save('administrator', 'pilot', {'data_governance': False}, 0)
    monkeypatch.setattr(core.store, 'put_json', revoke_after_snapshot)
    result = pilot.put('/api/governance/datasets/' + dataset['id'], json={
        'expected_version': 0, 'classification': 'confidential', 'change_reason': 'Synthetic change'})
    assert result.status_code == 403
    with core.Session() as session:
        assert session.get(core.Record, governance.policy_id(dataset['id'])) is None


def test_disabled_user_keeps_metadata_graph_without_governance_fields(pilot):
    login(pilot)
    dataset = pilot.post('/api/datasets', json={'name': 'Metadata stays available'}).json()
    response = pilot.get('/api/metadata-relationships', params={'dataset_id': dataset['id'], 'level': 'instances'})
    assert response.status_code == 200
    node = next(node for node in response.json()['nodes'] if node['type'] == 'Dataset')
    assert 'Classification' not in node['attributes'] and 'Governance version' not in node['attributes']
