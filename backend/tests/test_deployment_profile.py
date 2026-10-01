"""Bounded reads must not materialize deployment histories or decision payloads."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_production_catalog import production
from test_distribution_catalog import chain
from test_impact_assessments import context
from app.api.production import deployment_profile, get_deployment, get_deployment_provenance
from app.core.db import get_db
from app.main import app
from app.models.production import ProductionBatch, SoftwareChangeover


def test_exact_profile_keeps_identity_counts_and_parent_chain(production):
    db, release, _, old, auth, dep, pending, co, batches, site, line = production
    dep.actual_version = 4
    db.commit()
    result = deployment_profile(dep.deployment_no, db)
    assert result['id'] == str(dep.id)
    assert result['authorization']['id'] == str(auth[0].id)
    assert result['line']['id'] == str(line.id)
    assert result['actual_version'] == 4
    assert result['expected']['snapshot_id'] == str(old.id)
    assert result['actual']['release_id'] == str(release.id)
    assert result['history_counts'] == {'changeovers': 1, 'batches': 2}
    assert result['software_observation'] == 'MATCH'
    assert result['provenance']['delivery']['revision'] == 1
    assert result['provenance']['delivery']['snapshot_id'] == str(old.id)
    assert 'changeovers' not in result and 'batches' not in result
    assert 'release_decisions' not in result['provenance']
    empty = deployment_profile(pending.deployment_no, db)
    assert empty['history_counts'] == {'changeovers': 0, 'batches': 0}
    assert empty['software_observation'] == 'NOT_RECORDED'


@pytest.mark.parametrize('state,observation', [('partial', 'PARTIAL'), ('mismatch', 'MISMATCH'), ('empty', 'NOT_RECORDED')])
def test_observation_is_not_inferred_from_stored_status(production, state, observation):
    db, _, snapshot, _, _, dep, *_ = production
    if state == 'partial':
        dep.actual_snapshot_id = None
    elif state == 'mismatch':
        dep.actual_snapshot_id = snapshot.id
    else:
        dep.actual_release_id = dep.actual_snapshot_id = None
    db.commit()
    result = deployment_profile(dep.deployment_no, db)
    assert result['status'] == 'MATCH'
    assert result['software_observation'] == observation


def test_history_growth_does_not_load_rows_or_increase_query_count(production):
    db, release, _, old, auth, dep, _, _, _, _, _ = production
    calls = []
    def capture(_conn, _cursor, statement, *_args):
        calls.append(statement.lower())
    def read():
        db.expire_all()
        calls.clear()
        result = deployment_profile('DEP', db)
        return result, list(calls)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        _, initial = read()
        db.add_all([ProductionBatch(batch_no=f'GROW-{n}', deployment_id=dep.id, authorization_id=auth[0].id,
            release_id=release.id, snapshot_id=old.id, note='large history note' * 1000) for n in range(105)])
        db.add_all([SoftwareChangeover(changeover_no=f'GROW-CO-{n}', deployment_id=dep.id,
            authorization_id=auth[0].id, from_release_id=release.id, to_release_id=release.id,
            note='large history note' * 1000) for n in range(105)])
        db.commit()
        result, grown = read()
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert result['history_counts'] == {'changeovers': 106, 'batches': 107}
    assert len(initial) == len(grown) and len(grown) < 20
    history_queries = [sql for sql in grown if 'from software_changeovers' in sql or 'from production_batches' in sql]
    assert len(history_queries) == 2 and all('count(' in sql for sql in history_queries)
    assert not any('from release_decisions' in sql or 'from approval_requests' in sql for sql in grown)
    assert not any('large history note' in str(value) for value in result.values())


@pytest.mark.parametrize('broken', ['authorization', 'line', 'distribution'])
def test_missing_chain_reference_does_not_invent_context(production, broken):
    db, _, _, _, auth, dep, *_ = production
    if broken == 'authorization':
        dep.authorization_id = uuid.uuid4()
    elif broken == 'line':
        dep.production_line_id = uuid.uuid4()
    else:
        auth[0].distribution_id = uuid.uuid4()
    db.commit()
    result = deployment_profile(dep.deployment_no, db)
    if broken == 'line':
        assert result['line'] is None and result['site'] is None
    else:
        assert result['provenance']['delivery'] is None
        assert result['provenance']['distribution'] is None
    assert result['history_counts']['batches'] == 2


def test_legacy_detail_and_provenance_retain_history_shape(production):
    db, *_ = production
    legacy = get_deployment('DEP', db)
    assert len(legacy['batches']) == 2 and len(legacy['changeovers']) == 1
    assert 'release_decisions' in get_deployment_provenance('DEP', db)


def test_profile_route_exact_number_and_read_only_access(production, monkeypatch):
    from app import main
    db, _, _, _, _, dep, *_ = production
    dep.deployment_no = 'DEP-%_'
    db.commit()
    # TestClient uses a worker thread; copy fixture data into a shared SQLite connection.
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.connect() as connection:
        db.connection().connection.driver_connection.backup(connection.connection.driver_connection)
    route_db = Session(engine)
    app.dependency_overrides[get_db] = lambda: route_db
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/deployments/DEP-%25_/profile')
            assert response.status_code == 200, response.text
            assert response.json()['id'] == str(dep.id)
            assert client.get('/api/v1/deployments/DEP/profile').status_code == 404
            assert client.post('/api/v1/deployments', json={}).json() == {'detail': 'read_only_mode'}
    finally:
        app.dependency_overrides.pop(get_db, None)
        route_db.close()
        engine.dispose()


def test_missing_profile_is_404(production):
    db, *_ = production
    with pytest.raises(HTTPException) as error:
        deployment_profile('MISSING', db)
    assert error.value.status_code == 404
