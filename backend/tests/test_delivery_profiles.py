"""Exact revision reads remain bounded without losing recorded item evidence."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_impact_assessments import context
from test_distribution_catalog import chain
from app.api.distribution import DeliveryArtifactPage, delivery_artifacts, delivery_profile, get_delivery_revision
from app.core.db import get_db
from app.main import app
from app.models.distribution import DeliveryPackageItem, Distribution
from app.models.snapshot import SnapshotArtifact


def add_items(db, package, count):
    for _ in range(count):
        artifact = SnapshotArtifact(snapshot_id=package.snapshot_id, source_artifact_id=uuid.uuid4(),
            component_code='APP', filename='duplicate.hex', artifact_type='HEX', sha256='a'*64,
            classification='PUBLIC', distribution_level='EXTERNAL', ai_access_policy='DENY',
            storage_reference='private location must not escape')
        db.add(artifact); db.flush()
        db.add(DeliveryPackageItem(delivery_package_id=package.id, snapshot_artifact_id=artifact.id,
            policy_decision='APPROVAL_REQUIRED', exception_reference='CONTROL-1'))
    db.commit()


def test_profile_exact_revision_complete_counts_and_legacy_shape(chain):
    db, release, snapshot, old, packages, *_ = chain
    result = delivery_profile('DP-%_', 1, db)
    assert result['id'] == str(packages[0].id)
    assert result['release']['id'] == str(release.id) and result['snapshot']['id'] == str(old.id)
    assert result['recipient']['name'] == 'Customer'
    assert result['history_counts'] == {'artifacts': 3, 'distributions': 2}
    assert result['policy_counts'] == {'ALLOW': 3, 'APPROVAL_REQUIRED': 0, 'OTHER': 0} and result['control_reference_count'] == 0
    assert 'items' not in result and 'distributions' not in result
    sibling = delivery_profile('DP-%_', 2, db)
    assert sibling['id'] == str(packages[1].id) and sibling['snapshot']['id'] == str(snapshot.id)
    assert sibling['history_counts'] == {'artifacts': 0, 'distributions': 0}
    assert sibling['policy_counts'] == {'ALLOW': 0, 'APPROVAL_REQUIRED': 0, 'OTHER': 0}
    legacy = get_delivery_revision('DP-%_', 1, db)
    assert 'items' in legacy and len(legacy['distributions']) == 2


def test_pagination_stable_duplicate_names_and_missing_metadata(chain):
    db, _, _, _, packages, *_ = chain
    add_items(db, packages[0], 5)
    seen = []; offset = 0
    while True:
        page = delivery_artifacts('DP-%_', 1, DeliveryArtifactPage(limit=2, offset=offset), db)
        assert page['total'] == 8 and len(page['items']) <= 2
        assert page['delivery_package_id'] == str(packages[0].id) and page['revision'] == 1
        seen += page['items']
        if page['next_offset'] is None: break
        offset = page['next_offset']
    assert len({row['id'] for row in seen}) == 8
    assert sum(row['filename'] is None for row in seen) == 3
    assert all(row['snapshot_artifact_id'] for row in seen)
    assert all('storage_reference' not in row for row in seen)
    assert [r['id'] for r in delivery_artifacts('DP-%_', 1, DeliveryArtifactPage(limit=100), db)['items']] == [r['id'] for r in seen]
    assert delivery_artifacts('DP-%_', 2, DeliveryArtifactPage(), db)['total'] == 0
    beyond = delivery_artifacts('DP-%_', 1, DeliveryArtifactPage(offset=99), db)
    assert beyond['total'] == 8 and beyond['items'] == [] and beyond['next_offset'] is None
    profile = delivery_profile('DP-%_', 1, db)
    assert profile['policy_counts'] == {'ALLOW': 3, 'APPROVAL_REQUIRED': 5, 'OTHER': 0}
    assert profile['control_reference_count'] == 1
    assert len(get_delivery_revision('DP-%_', 1, db)['items']) == 5


def test_growth_uses_aggregates_and_limits_child_loading(chain):
    db, _, _, _, packages, *_ = chain
    statements = []
    def capture(_conn, _cursor, sql, *_args): statements.append(sql.lower())
    def read_profile():
        db.expire_all(); statements.clear()
        result = delivery_profile('DP-%_', 1, db)
        return result, list(statements)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        _, initial = read_profile()
        add_items(db, packages[0], 105)
        db.add_all([Distribution(distribution_no=f'GROW-{n}', delivery_package_id=packages[0].id,
            recipient_type='CUSTOMER', recipient_code='CUS-A', status='CANCELLED', note='child history' * 1000) for n in range(105)])
        db.commit()
        profile, grown = read_profile()
        assert len(initial) == len(grown) < 10
        child = [sql for sql in grown if 'from delivery_package_items' in sql or 'from distributions' in sql]
        assert len(child) == 3 and all('count(' in sql for sql in child)
        assert profile['history_counts'] == {'artifacts': 108, 'distributions': 107}
        statements.clear()
        page = delivery_artifacts('DP-%_', 1, DeliveryArtifactPage(limit=2), db)
        assert len(page['items']) == 2 and page['total'] == 108
        assert len(statements) == 3 and 'limit' in statements[-1] and 'offset' in statements[-1]
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert 'child history' not in str(profile) and 'private location' not in str(page)


@pytest.mark.parametrize('parent', ['release', 'snapshot'])
def test_missing_parent_remains_null(chain, parent):
    db, _, _, _, packages, *_ = chain
    setattr(packages[0], parent+'_id', uuid.uuid4()); db.commit()
    result = delivery_profile('DP-%_', 1, db)
    assert result[parent] is None and result['history_counts']['artifacts'] == 3


def test_unknown_policy_values_remain_in_bounded_summary(chain):
    db, _, _, _, packages, *_ = chain
    db.add_all([DeliveryPackageItem(delivery_package_id=packages[0].id,
        snapshot_artifact_id=uuid.uuid4(), policy_decision=f'LEGACY-{n}',
        exception_reference='CONTROL-OTHER') for n in range(105)])
    db.commit()
    result = delivery_profile('DP-%_', 1, db)
    assert result['policy_counts'] == {'ALLOW': 3, 'APPROVAL_REQUIRED': 0, 'OTHER': 105}
    assert result['history_counts']['artifacts'] == 108 and result['control_reference_count'] == 1


@pytest.mark.parametrize('revision,status', [(0, 422), (-1, 422), (3, 404)])
@pytest.mark.parametrize('route', ['profile', 'artifacts'])
def test_invalid_or_missing_revision(chain, revision, status, route):
    db, *_ = chain
    with pytest.raises(HTTPException) as exc:
        if route == 'profile': delivery_profile('DP-%_', revision, db)
        else: delivery_artifacts('DP-%_', revision, DeliveryArtifactPage(), db)
    assert exc.value.status_code == status


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'offset=-1', 'offset=100001', 'limit=abc', 'unexpected=yes'])
def test_http_invalid_artifact_query(query):
    with TestClient(app) as client:
        response = client.get('/api/v1/deliveries/DP/revisions/1/artifacts?'+query)
    assert response.status_code == 422, response.text


def test_http_literal_number_and_read_only(chain, monkeypatch):
    from app import main
    db, _, _, _, packages, *_ = chain
    expected_id = str(packages[0].id)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.connect() as connection:
        db.connection().connection.driver_connection.backup(connection.connection.driver_connection)
    route_db = Session(engine)
    app.dependency_overrides[get_db] = lambda: route_db
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    try:
        with TestClient(app) as client:
            for suffix in ['profile', 'artifacts']:
                response = client.get(f'/api/v1/deliveries/DP-%25_/revisions/1/{suffix}')
                assert response.status_code == 200, response.text
                result = response.json()
                assert result.get('id', result.get('delivery_package_id')) == expected_id
                assert client.get(f'/api/v1/deliveries/DP/revisions/1/{suffix}').status_code == 404
            rejected = client.post('/api/v1/deliveries', json={})
            assert rejected.status_code == 403 and rejected.json() == {'detail': 'read_only_mode'}
    finally:
        app.dependency_overrides.pop(get_db, None); route_db.close(); engine.dispose()
