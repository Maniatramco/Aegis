"""Documentation is sourced from the complete route registry and stays read-only."""
from fastapi.testclient import TestClient
from app import main, api_documentation


def test_catalog_covers_every_live_operation_and_has_no_stale_notes():
    spec = main.app.openapi()
    keys = {f'{method.upper()} {path}' for path, item in spec['paths'].items() for method in item}
    assert keys == set(api_documentation.NOTES)
    metadata = api_documentation.operations(main.app)
    assert set(metadata) == keys
    for path, item in spec['paths'].items():
        for method, operation in item.items():
            assert operation['description'] == api_documentation.NOTES[f'{method.upper()} {path}']
            assert operation['tags']
    assert metadata['POST /api/extractions']['csrf_required']
    assert not metadata['GET /api/documents']['csrf_required']
    assert metadata['POST /api/auth/recovery/reset']['authentication'] == 'Local recovery challenge'
    recovery = spec['paths']['/api/auth/recovery/reset']['post']['requestBody']['content']['application/json']['schema']
    assert set(recovery['required']) == {'password', 'confirmation'}
    assert 'token' in recovery['properties']  # optional legacy private-grant flow
    assert recovery['properties']['password']['minLength'] == 12


def test_documentation_requires_login_and_returns_only_contract():
    # No lifespan: this read-only contract needs neither a database nor a model.
    client = TestClient(main.app)
    assert client.get('/api/documentation').status_code == 401
    assert client.get('/api/documentation/export').status_code == 401
    main.app.dependency_overrides[main.auth] = lambda: 'documentation-reader'
    try:
        response = client.get('/api/documentation')
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {'schema', 'operations'}
        assert '/api/model-registrations' in payload['schema']['paths']
        assert payload['operations']['POST /api/documents/upload']['response_example']['jobs'][0]['status'] == 'queued'
        assert payload['operations']['GET /api/documentation']['source'].startswith('api_documentation.py')
        assert not any(key in payload for key in ('settings', 'users', 'documents', 'credentials'))
        export = client.get('/api/documentation/export')
        assert export.status_code == 200
        assert export.json() == payload['schema']
        assert export.headers['content-disposition'] == 'attachment; filename="aegis-openapi.json"'
    finally:
        main.app.dependency_overrides.pop(main.auth, None)
        client.close()
