"""HTTP retirement must not resolve DB graphs or intercept active consumers."""
from urllib.parse import quote
from unittest.mock import Mock
import re

import pytest
from fastapi.testclient import TestClient
from app.api.compatibility_reads import RETIRED_READS, MIGRATION_INSTRUCTIONS
from app.api import organizations, production, distribution, dashboard, change_coverage, impact, snapshots, activity, releases
from app.core.db import get_db
from app.main import app


@pytest.mark.parametrize('path,replacements,pin', RETIRED_READS)
@pytest.mark.parametrize('query', ['', '?limit=not-a-number&offset=-1'])
def test_reviewed_legacy_reads_return_410_without_db_or_graphs(monkeypatch, path, replacements, pin, query):
    identifier = 'Missing_% name?&汉字'
    concrete = path
    parameters = {key: ('7' if key == 'revision' else identifier)
                  for key in re.findall(r'\{([^}]+)\}', path)}
    for key, value in parameters.items():
        concrete = concrete.replace('{'+key+'}', quote(value, safe=''))
    db = Mock(side_effect=AssertionError('retirement must not request a database'))
    helpers = []
    for module, names in ((organizations, ('_suppliers', '_customers', '_projects')),
                          (production, ('_deployment_detail', '_deployment_provenance')),
                          (distribution, ('_delivery_detail', '_distribution_detail', '_authorization_detail')),
                          (dashboard, ('change_detail', 'get_issue', 'list_dvp', 'dvp_item_detail', 'list_approvals', 'get_approval', 'list_standard_releases', 'list_application_releases', 'standard_release_profile', 'application_release_decision', 'application_release_decisions', 'application_release_components', 'application_release_evidence', 'application_snapshot_policy', 'application_release_downstream', 'release_overview', 'release_verification', 'release_artifacts', 'release_readiness', 'application_release_readiness', 'get_release_decision')),
                          (change_coverage, ('report_coverage',)),
                          (snapshots, ('_manifest', 'compare_manifests')),
                          (activity, ('_release_links', '_event_detail')),
                          (releases, ('list_releases',)),
                          (impact, ('_contexts', '_assessment'))):
        for name in names:
            helper = Mock(side_effect=AssertionError('retirement must not serialize a graph'))
            monkeypatch.setattr(module, name, helper); helpers.append(helper)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[releases.get_db] = db
    try:
        response = TestClient(app).get(concrete+query)
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    assert response.status_code == 410
    body = response.json()
    urls = list(replacements)
    for key, value in {'identifier': identifier, **parameters}.items():
        urls = [url.replace('{'+key+'}', quote(value, safe='')) for url in urls]
    assert body['detail'] == 'legacy_read_retired'
    assert body['retired_route'] == path
    assert body['replacements'] == urls
    assert body['required_collection_pin'] == pin
    if path in MIGRATION_INSTRUCTIONS:
        assert body['instructions'] == MIGRATION_INSTRUCTIONS[path]
    assert response.headers['link'] == f'<{urls[0]}>; rel="successor-version"'
    assert response.headers['cache-control'] == 'no-store'
    db.assert_not_called()
    for helper in helpers: helper.assert_not_called()


def test_registry_has_exact_retirement_scope_and_retains_commands_and_replacements():
    retired = {path for path, _, _ in RETIRED_READS}
    assert len(retired) == 50
    for path in retired:
        routes = [r for r in app.routes if r.path == path and 'GET' in (getattr(r, 'methods', None) or set())]
        assert len(routes) == 1
        assert routes[0].deprecated
        assert routes[0].dependant.dependencies == []
    paths = {(r.path, method) for r in app.routes for method in (getattr(r, 'methods', None) or set())}
    assert ('/api/v1/organizations/release-matrix', 'GET') in paths
    assert ('/api/v1/manufacturing-views/sites', 'GET') in paths
    for path in ['/api/v1/governance/approvals',
                 '/api/v1/governance/approvals/{approval_no}/summary',
                 '/api/v1/governance/approvals/{approval_no}/steps',
                 '/api/v1/governance/approvals/{approval_no}/actions',
                 '/api/v1/audit/events',
                 '/api/v1/activity/{event_no}',
                 '/api/v1/testing/dvp/catalog',
                 '/api/v1/testing/dvp/id/{item_id}/profile',
                 '/api/v1/testing/dvp/id/{item_id}/relations/{kind}',
                 '/api/v1/testing/dvp/id/{item_id}/executions',
                 '/api/v1/snapshots/{snapshot_no}/summary',
                 '/api/v1/snapshots/{snapshot_no}/artifacts',
                 '/api/v1/snapshots/{snapshot_no}/rules',
                 '/api/v1/snapshots/{source_no}/comparison/{target_no}/summary',
                 '/api/v1/snapshots/{source_no}/comparison/{target_no}/files',
                 '/api/v1/change-views/{request_no}/summary',
                 '/api/v1/change-coverage-views/{request_no}/summary',
                 '/api/v1/issue-views/{issue_no}/summary',
                 '/api/v1/issue-views/{issue_no}/impact/{release_id}/summary',
                 '/api/v1/change-catalog/requests',
                 '/api/v1/change-catalog/issues',
                 '/api/v1/deployments/{deployment_no}/profile',
                 '/api/v1/batches/{batch_no}',
                 '/api/v1/deliveries/{package_no}/revisions/{revision}/profile',
                 '/api/v1/deliveries/{package_no}/revisions/{revision}/artifacts',
                 '/api/v1/distributions/{distribution_no}/profile',
                 '/api/v1/authorizations/{authorization_no}/profile',
                 '/api/v1/distribution/catalog/deliveries',
                 '/api/v1/distribution/catalog/distributions',
                 '/api/v1/distribution/catalog/authorizations',
                 '/api/v1/production/catalog/{kind}']:
        assert (path, 'GET') in paths
    assert ('/api/v1/deployments', 'POST') in paths
    assert ('/api/v1/deployments/{deployment_no}/actual', 'POST') in paths
    assert ('/api/v1/deployments/{deployment_no}/batches', 'POST') in paths
    from app.write_contracts import WRITE_CONTRACTS, SESSION_CONTROL_CONTRACTS, ADMIN_CONTROL_CONTRACTS
    writes = {(method, path) for path, method in paths if method == 'POST'}
    assert len(WRITE_CONTRACTS) == 14
    assert writes == set(WRITE_CONTRACTS) | set(SESSION_CONTROL_CONTRACTS) | set(ADMIN_CONTROL_CONTRACTS)
    schema = app.openapi()
    for path in retired:
        operation = schema['paths'][path]['get']
        assert operation['deprecated'] is True
        assert '410' in operation['responses']
        assert '200' not in operation['responses']


@pytest.mark.parametrize('revision', ['0', 'bogus'])
def test_retired_delivery_revision_does_not_resolve_or_validate_old_identity(revision):
    response = TestClient(app).get('/api/v1/deliveries/NOT-FOUND/revisions/'+revision)
    assert response.status_code == 410
    assert response.json()['replacements'][0].endswith('/revisions/'+revision+'/profile')


def test_provenance_instructions_pin_delivered_snapshot_and_do_not_infer_actual_scope():
    response = TestClient(app).get('/api/v1/deployments/UNKNOWN/provenance')
    assert response.status_code == 410
    instructions = response.json()['instructions']
    assert 'both its release_id and snapshot_id' in instructions
    assert 'otherwise no decision scope is inferred' in instructions
    assert "current actual software" in instructions


@pytest.mark.parametrize('path,selection', [
    ('/api/v1/changes/SCR/coverage', 'release_id=invalid&snapshot_no=HIST'),
    ('/api/v1/issues/ISSUE/impact/not-a-uuid', 'snapshot_id=HIST'),
])
def test_retirement_preserves_explicit_historical_selection_instructions(path, selection):
    response = TestClient(app).get(path+'?'+selection)
    assert response.status_code == 410
    instructions = response.json()['instructions']
    assert 'historical' in instructions and 'latest' in instructions
    assert 'snapshot_id' in instructions and 'none sentinels' in instructions


def test_snapshot_comparison_migration_requires_both_exact_identities():
    response = TestClient(app).get('/api/v1/snapshots/HIST/compare/OTHER')
    assert response.status_code == 410
    body = response.json()
    assert body['required_collection_pin'] is None
    assert 'source.id as source_id' in body['instructions']
    assert 'target.id as target_id' in body['instructions']
    assert 'same-release' in body['instructions']
    assert 'latest' in body['instructions']
