"""HTTP retirement must not resolve DB graphs or intercept active consumers."""
from urllib.parse import quote
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.api.compatibility_reads import RETIRED_READS
from app.api import organizations, production
from app.core.db import get_db
from app.main import app


@pytest.mark.parametrize('path,replacements,pin', RETIRED_READS)
@pytest.mark.parametrize('query', ['', '?limit=not-a-number&offset=-1'])
def test_reviewed_legacy_reads_return_410_without_db_or_graphs(monkeypatch, path, replacements, pin, query):
    identifier = 'Missing_% name?&汉字'
    concrete = path
    for key in ('code', 'identifier', 'site_code'):
        concrete = concrete.replace('{'+key+'}', quote(identifier, safe=''))
    db = Mock(side_effect=AssertionError('retirement must not request a database'))
    helpers = []
    for module, names in ((organizations, ('_suppliers', '_customers', '_projects')),
                          (production, ('_deployment_detail',))):
        for name in names:
            helper = Mock(side_effect=AssertionError('retirement must not serialize a graph'))
            monkeypatch.setattr(module, name, helper); helpers.append(helper)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = db
    try:
        response = TestClient(app).get(concrete+query)
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    assert response.status_code == 410
    body = response.json()
    urls = [url.replace('{identifier}', quote(identifier, safe='')) for url in replacements]
    assert body['detail'] == 'legacy_read_retired'
    assert body['retired_route'] == path
    assert body['replacements'] == urls
    assert body['required_collection_pin'] == pin
    assert response.headers['link'] == f'<{urls[0]}>; rel="successor-version"'
    assert response.headers['cache-control'] == 'no-store'
    db.assert_not_called()
    for helper in helpers: helper.assert_not_called()


def test_registry_has_exact_retirement_scope_and_retains_commands_and_replacements():
    retired = {path for path, _, _ in RETIRED_READS}
    assert len(retired) == 8
    for path in retired:
        routes = [r for r in app.routes if r.path == path and 'GET' in (getattr(r, 'methods', None) or set())]
        assert len(routes) == 1
        assert routes[0].deprecated
        assert routes[0].dependant.dependencies == []
    paths = {(r.path, method) for r in app.routes for method in (getattr(r, 'methods', None) or set())}
    assert ('/api/v1/organizations/release-matrix', 'GET') in paths
    assert ('/api/v1/manufacturing-views/sites', 'GET') in paths
    assert ('/api/v1/deployments', 'POST') in paths
    assert ('/api/v1/deployments/{deployment_no}/actual', 'POST') in paths
    assert ('/api/v1/deployments/{deployment_no}/batches', 'POST') in paths
    assert len([1 for _, method in paths if method == 'POST']) == 14
    schema = app.openapi()
    for path in retired:
        operation = schema['paths'][path]['get']
        assert operation['deprecated'] is True
        assert '410' in operation['responses']
        assert '200' not in operation['responses']
