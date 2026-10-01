"""Exact distribution/authorization profiles omit unbounded child histories."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_distribution_catalog import chain
from test_impact_assessments import context
from app.api.distribution import authorization_profile, distribution_profile, get_authorization, get_distribution
from app.core.db import get_db
from app.main import app
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch


def test_authorization_exact_scope_quota_and_complete_counts(chain):
    db, release, _, old, packages, records, auth, customer, project = chain
    row = authorization_profile('PA-1', db)
    assert row['id'] == str(auth[0].id) and row['release']['id'] == str(release.id)
    assert row['snapshot']['id'] == str(old.id)
    assert row['customer']['id'] == str(customer.id) and row['project']['id'] == str(project.id)
    assert row['distribution']['id'] == str(records[0].id) and row['distribution']['package_revision'] == 1
    assert row['batch_limit'] == 2 and row['history_counts'] == {'deployments': 1, 'batches': 2}
    assert 'batches' not in row and 'deployments' not in row
    unlimited = authorization_profile('PA-2', db)
    assert unlimited['batch_limit'] is None and unlimited['history_counts'] == {'deployments': 0, 'batches': 0}


def test_distribution_exact_revision_and_sibling_isolation(chain):
    db, _, _, _, packages, records, auth, *_ = chain
    row = distribution_profile('DIST-1', db)
    assert row['id'] == str(records[0].id) and row['delivery']['id'] == str(packages[0].id)
    assert row['delivery']['revision'] == 1 and row['snapshot_no'] == 'OLD'
    assert row['history_counts'] == {'authorizations': 2} and 'authorizations' not in row
    assert distribution_profile('DIST-2', db)['history_counts'] == {'authorizations': 0}


@pytest.mark.parametrize('kind', ['authorization', 'distribution'])
def test_history_growth_keeps_queries_fixed_and_omits_payloads(chain, kind):
    db, release, _, old, _, records, auth, customer, project = chain
    profile, number = (authorization_profile, 'PA-1') if kind == 'authorization' else (distribution_profile, 'DIST-1')
    statements = []
    def capture(_conn, _cursor, sql, *_args): statements.append(sql.lower())
    def read():
        db.expire_all(); statements.clear()
        result = profile(number, db)
        return result, list(statements)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        _, initial = read()
        if kind == 'authorization':
            db.add_all([Deployment(deployment_no=f'GROW-D-{n}', authorization_id=auth[0].id,
                production_line_id=uuid.uuid4(), expected_release_id=release.id, expected_snapshot_id=old.id) for n in range(105)])
            db.add_all([ProductionBatch(batch_no=f'GROW-B-{n}', deployment_id=uuid.uuid4(), authorization_id=auth[0].id,
                release_id=release.id, snapshot_id=old.id, status='CANCELLED', note='history payload' * 1000) for n in range(105)])
        else:
            db.add_all([SoftwareAuthorization(authorization_no=f'GROW-A-{n}', distribution_id=records[0].id,
                release_id=release.id, snapshot_id=old.id, customer_id=customer.id, project_id=project.id,
                site_code='SITE', line_code='LINE', purpose='PRODUCTION', status='REVOKED',
                restriction_note='history payload' * 1000) for n in range(105)])
        db.commit()
        result, grown = read()
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert len(initial) == len(grown) and len(grown) < 12
    assert 'history payload' not in str(result)
    tables = ['deployments', 'production_batches'] if kind == 'authorization' else ['software_authorizations']
    child_queries = [sql for sql in grown if any('from '+table in sql for table in tables)]
    assert len(child_queries) == len(tables) and all('count(' in sql for sql in child_queries)
    assert result['history_counts'] == ({'deployments': 106, 'batches': 107} if kind == 'authorization' else {'authorizations': 107})


@pytest.mark.parametrize('reference', ['release', 'snapshot', 'customer', 'project', 'distribution'])
def test_missing_authorization_parent_stays_null(chain, reference):
    db, *_, auth, customer, project = chain
    setattr(auth[0], reference+'_id', uuid.uuid4()); db.commit()
    row = authorization_profile('PA-1', db)
    assert row[reference] is None and row['history_counts']['batches'] == 2


def test_missing_delivery_does_not_infer_distribution_context(chain):
    db, _, _, _, _, records, *_ = chain
    records[0].delivery_package_id = uuid.uuid4(); db.commit()
    row = distribution_profile('DIST-1', db)
    assert row['delivery'] is None and row['release_version'] is None and row['snapshot_no'] is None
    assert row['history_counts']['authorizations'] == 2


def test_legacy_details_keep_embedded_histories(chain):
    db, *_ = chain
    assert len(get_authorization('PA-1', db)['batches']) == 2
    assert len(get_authorization('PA-1', db)['deployments']) == 1
    assert len(get_distribution('DIST-1', db)['authorizations']) == 2


@pytest.mark.parametrize('profile', [authorization_profile, distribution_profile])
def test_missing_exact_profile_is_404(chain, profile):
    db, *_ = chain
    with pytest.raises(HTTPException) as error: profile('MISSING', db)
    assert error.value.status_code == 404


@pytest.mark.parametrize('kind', ['authorizations', 'distributions'])
def test_http_exact_special_number_and_read_only(chain, monkeypatch, kind):
    from app import main
    db, _, _, _, _, records, auth, *_ = chain
    row = auth[0] if kind == 'authorizations' else records[0]
    field = 'authorization_no' if kind == 'authorizations' else 'distribution_no'
    setattr(row, field, 'EXACT-%_'); db.commit(); expected_id = str(row.id)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.connect() as connection:
        db.connection().connection.driver_connection.backup(connection.connection.driver_connection)
    route_db = Session(engine)
    app.dependency_overrides[get_db] = lambda: route_db
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    try:
        with TestClient(app) as client:
            response = client.get(f'/api/v1/{kind}/EXACT-%25_/profile')
            assert response.status_code == 200, response.text
            assert response.json()['id'] == expected_id
            assert client.get(f'/api/v1/{kind}/EXACT/profile').status_code == 404
            rejected = client.post(f'/api/v1/{kind}', json={})
            assert rejected.status_code == 403 and rejected.json() == {'detail': 'read_only_mode'}
    finally:
        app.dependency_overrides.pop(get_db, None); route_db.close(); engine.dispose()
