"""Bounded SSR child batch: parity, row isolation and constant SQL work."""
import json
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api import release_catalog as catalog_api
from app.api.standard_release_views import CollectionPage, standard_applications
from app.core.db import get_db
from app.main import app
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release
from app.models.audit import AuditEvent


def seed(db, base, parents=3, children=23):
    customer = Customer(code=str(uuid.uuid4()), name='Customer'); db.add(customer); db.flush()
    project = Project(customer_id=customer.id, project_code='P', name='Project'); db.add(project); db.flush()
    bases = [base]
    for index in range(1, parents):
        row = Release(software_id=base.software_id, release_type='STANDARD', version=f'Base-{index}')
        db.add(row); db.flush(); bases.append(row)
    for index, parent in enumerate(bases):
        for number in range(children):
            row = Release(software_id=base.software_id, release_type='APPLICATION', version=f'应用_{index}_{number}', created_at=datetime(2026, 1, 1))
            db.add(row); db.flush()
            db.add(ApplicationReleaseDetail(release_id=row.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=parent.id))
    db.commit()
    return [row.id for row in bases]


def batch(db, **kwargs):
    return json.loads(catalog_api.standard_applications_batch(catalog_api.ApplicationBatchFilters(**kwargs), db).body)


def test_batch_matches_legacy_order_pagination_and_projection(context):
    db, _, base, *_ = context; ids = seed(db, base)
    for offset in (0, 10, 20, 100000):
        result = batch(db, applications_for=ids[0], application_offset=offset)
        assert set(result) == {'limit', 'offset', 'items'}
        for page in result['items']:
            expected = offset if page['release_id'] == str(ids[0]) else 0
            assert page == standard_applications(uuid.UUID(page['release_id']), CollectionPage(limit=10, offset=expected), db)
            assert all(set(row) == {'id', 'version', 'status'} for row in page['items'])


def test_batch_filters_current_page_only_and_three_queries(context):
    db, _, base, *_ = context; ids = seed(db, base, parents=101, children=11)
    calls = []
    def capture(_c, _cur, sql, *_): calls.append(sql)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        db.expunge_all()
        result = batch(db, limit=50)
        assert len(calls) == 3 and len(result['items']) == 50
        assert sum(len(page['items']) for page in result['items']) == 500
        assert 'row_number() OVER (PARTITION BY' in calls[2]
        assert 'DESC NULLS LAST' in calls[2]
        assert not db.identity_map
        calls.clear()
        maximum = batch(db, limit=100)
        assert len(calls) == 3 and len(maximum['items']) == 100
        assert sum(len(page['items']) for page in maximum['items']) == 1000
        calls.clear()
        directory = catalog_api.release_catalog('standard', catalog_api.Filters(limit=2, offset=3), db)
        result = batch(db, limit=2, offset=3, applications_for=uuid.uuid4(), application_offset=10)
        assert len(calls) == 5
        assert [x['release_id'] for x in result['items']] == [x['id'] for x in directory['items']]
        assert all(x['offset'] == 0 for x in result['items'])
        for filters in ({'q': 'Base-1'}, {'q': '_%'}, {'status': 'RELEASED'}, {'software_id': uuid.uuid4()}, {'offset': 100000}):
            directory = catalog_api.release_catalog('standard', catalog_api.Filters(**filters), db)
            assert [x['release_id'] for x in batch(db, **filters)['items']] == [x['id'] for x in directory['items']]
    finally: event.remove(db.bind, 'before_cursor_execute', capture)


def test_batch_preserves_legacy_associations_and_missing_release_exclusion(context):
    db, _, base, *_ = context; ids = seed(db, base, parents=2, children=2)
    children = db.scalars(select(Release).where(Release.release_type == 'APPLICATION')).all()
    children[0].release_type = 'STANDARD'  # Legacy association is not an inferred type filter.
    children[0].software_id = uuid.uuid4()
    db.delete(children[1]); db.commit()
    result = batch(db)
    for page in result['items']:
        assert page == standard_applications(uuid.UUID(page['release_id']), CollectionPage(limit=10), db)


def test_batch_size_guard_counts_utf8_bytes_and_never_truncates(context, monkeypatch):
    db, _, base, *_ = context; seed(db, base, parents=1, children=1)
    assert catalog_api.APPLICATION_BATCH_MAX_BYTES == 2 * 1024 * 1024
    result = catalog_api.standard_applications_batch(catalog_api.ApplicationBatchFilters(), db)
    assert '应用'.encode() in result.body
    monkeypatch.setattr(catalog_api, 'APPLICATION_BATCH_MAX_BYTES', len(result.body))
    assert catalog_api.standard_applications_batch(catalog_api.ApplicationBatchFilters(), db).body == result.body
    monkeypatch.setattr(catalog_api, 'APPLICATION_BATCH_MAX_BYTES', len(result.body) - 1)
    with pytest.raises(HTTPException) as error: batch(db)
    assert error.value.status_code == 503 and error.value.detail == 'application_batch_response_too_large'


@pytest.mark.parametrize('query', ['limit=0','limit=101','offset=-1','offset=100001','unknown=1','software_id=bad','applications_for=bad','application_offset=-1','application_offset=100001','q='+('x'*201),'status='+('x'*31)])
def test_batch_http_rejects_invalid_filters(context, query):
    db, *_ = context
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    with engine.connect() as conn: db.connection().connection.driver_connection.backup(conn.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db] = lambda: route_db
        try:
            with TestClient(app) as client:
                assert client.get('/api/v1/release-catalog/standard/applications?'+query).status_code == 422
                assert client.get('/api/v1/release-catalog/standard/applications').status_code == 200
        finally: app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_batch_migrated_postgresql_large_sample_plan_and_no_audit(pg, record_property):
    engine, ids = pg
    with Session(engine) as db:
        base = db.get(Release, ids['release']); parent_ids = seed(db, base, parents=101, children=12)
        # Include one high-fanout parent and exclude another from the current page.
        # No wall-clock threshold: retain actual rows, sorts and buffers in plans.
        db.execute(update(Release).where(Release.id == parent_ids[0]).values(created_at=datetime(2099, 1, 1)))
        db.execute(update(Release).where(Release.id == parent_ids[-1]).values(created_at=datetime(2000, 1, 1)))
        detail = db.scalars(select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.standard_base_release_id == base.id)).first()
        for parent in (parent_ids[0], parent_ids[-1]):
            releases = [{'id': uuid.uuid4(), 'software_id': base.software_id, 'release_type': 'APPLICATION',
                         'version': f'fanout-{parent}-{index}', 'created_at': datetime(2026, 1, 1)} for index in range(5001)]
            db.execute(insert(Release), releases)
            db.execute(insert(ApplicationReleaseDetail), [{'release_id': row['id'], 'customer_id': detail.customer_id,
                'project_id': detail.project_id, 'standard_base_release_id': parent} for row in releases])
        # Migrated PostgreSQL allows legacy NULL timestamps, unlike the current
        # ORM-created SQLite fixture. SQL UPDATE avoids Python default insertion.
        null_child = db.scalar(select(Release.id).join(ApplicationReleaseDetail, ApplicationReleaseDetail.release_id == Release.id)
            .where(ApplicationReleaseDetail.standard_base_release_id == base.id).order_by(Release.id).limit(1))
        db.execute(update(Release).where(Release.id == null_child).values(created_at=None))
        db.commit()
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        captured = []
        def capture(_c, _cur, sql, params, *_): captured.append((sql, params))
        event.listen(engine, 'before_cursor_execute', capture)
        try:
            db.expunge_all(); result = batch(db, limit=100)
        finally: event.remove(engine, 'before_cursor_execute', capture)
        assert len(captured) == 3 and len(result['items']) == 100
        assert sum(len(row['items']) for row in result['items']) == 1000
        assert result['items'][0]['release_id'] == str(parent_ids[0])
        assert result['items'][0]['total'] == 5013
        assert str(parent_ids[-1]) not in {row['release_id'] for row in result['items']}
        assert not db.identity_map
        with engine.connect() as conn:
            plans = [conn.exec_driver_sql('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql, params).scalar() for sql, params in captured]
        record_property('standard_applications_batch_plans', json.dumps(plans))
        assert 'WindowAgg' in json.dumps(plans[2])
        assert 'Actual Rows' in json.dumps(plans[2]) and 'Sort' in json.dumps(plans[2])
        last = batch(db, applications_for=parent_ids[0], application_offset=5010)['items'][0]
        assert last == standard_applications(parent_ids[0], CollectionPage(limit=10, offset=5010), db)
        assert last['items'][-1]['id'] == str(null_child)
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_empty_parent_page_uses_one_query_and_no_children(context):
    db, _, base, *_ = context; seed(db, base, parents=1, children=0)
    calls = []
    def capture(_c, _cur, sql, *_): calls.append(sql)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        assert batch(db, q='absent')['items'] == []
        assert len(calls) == 1
        calls.clear()
        result = batch(db)
        assert len(calls) == 3 and result['items'][0]['items'] == []
        assert result['items'][0]['total'] == 0
    finally: event.remove(db.bind, 'before_cursor_execute', capture)


def test_http_batch_readonly_and_explicit_oversize_failure(context, monkeypatch):
    from app import main
    db, _, base, *_ = context; seed(db, base, parents=1, children=1)
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    with engine.connect() as conn: db.connection().connection.driver_connection.backup(conn.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db] = lambda: route_db
        monkeypatch.setattr(main.settings, 'read_only_mode', True)
        try:
            with TestClient(app) as client:
                response = client.get('/api/v1/release-catalog/standard/applications')
                assert response.status_code == 200 and response.json()['items'][0]['total'] == 1
                assert response.headers['cache-control'] == 'no-store'
                monkeypatch.setattr(catalog_api, 'APPLICATION_BATCH_MAX_BYTES', 1)
                response = client.get('/api/v1/release-catalog/standard/applications')
                assert response.status_code == 503
                assert response.headers['cache-control'] == 'no-store'
                assert response.json() == {'detail':'application_batch_response_too_large'}
        finally: app.dependency_overrides.pop(get_db, None)
    engine.dispose()
