"""Real PostgreSQL command concurrency tests, on a disposable migrated schema.

Set TEST_POSTGRES_URL to a development PostgreSQL database whose user may create
schemas. Never point this at company data or public staging. Each test creates
and drops only its uniquely named schema; SQLite is explicitly rejected.
"""
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.core import Customer, Project, Release, SoftwareProduct, Supplier
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment, ManufacturingSite, ProductionBatch, ProductionLine
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.services.approval import ApprovalError
from app.services.distribution import DistributionError
from app.services.audit import AuditEventService
from app.services.production import ProductionError, ProductionService
from app.services.snapshot import SnapshotError, SnapshotService
from test_command_audit import prepare_snapshot_source


@pytest.fixture
def pg(monkeypatch):
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TEST_POSTGRES_URL required for real PostgreSQL lock tests')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql':
        pytest.fail('Concurrency tests require real PostgreSQL, not SQLite')
    parsed = parsed.set(drivername='postgresql+psycopg')
    admin = create_engine(parsed)
    schema = 'command_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = parsed.update_query_dict({'options': f'-csearch_path={schema} -cstatement_timeout=10000'})
    engine = create_engine(scoped, pool_size=5)
    try:
        monkeypatch.setattr(settings, 'database_url', scoped.render_as_string(hide_password=False))
        command.upgrade(Config('alembic.ini'), 'head')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == settings.required_db_revision
            assert connection.scalar(text('SHOW transaction_isolation')) == 'read committed'
        with Session(engine, expire_on_commit=False) as db:
            supplier = Supplier(code='S', name='Supplier'); db.add(supplier); db.flush()
            product = SoftwareProduct(supplier_id=supplier.id, code='SW', name='Software')
            customer = Customer(code='C', name='Customer'); db.add_all([product, customer]); db.flush()
            project = Project(customer_id=customer.id, project_code='P', name='Project')
            release = Release(software_id=product.id, release_type='STANDARD', version='1')
            db.add_all([project, release]); db.commit()
            prepare_snapshot_source(db, release)
            snapshot = SnapshotService().create(db, release.id)
            authorization = SoftwareAuthorization(authorization_no='AUTH', release_id=release.id,
                snapshot_id=snapshot.id, customer_id=customer.id, project_id=project.id,
                site_code='SITE', line_code='LINE', purpose='PRODUCTION', status='APPROVED', batch_limit=1)
            site = ManufacturingSite(site_code='SITE', customer_id=customer.id, project_id=project.id,
                                     name='Site', status='ACTIVE')
            db.add_all([authorization, site]); db.flush()
            line = ProductionLine(site_id=site.id, line_code='LINE', name='Line', status='ACTIVE')
            db.add(line); db.flush()
            deployments = [Deployment(deployment_no=f'DEP-{n}', authorization_id=authorization.id,
                production_line_id=line.id, expected_release_id=release.id, expected_snapshot_id=snapshot.id,
                actual_release_id=release.id, actual_snapshot_id=snapshot.id, status='MATCH') for n in (1, 2)]
            db.add_all(deployments); db.commit()
            ids = {'release': release.id, 'authorization': authorization.id}
        yield engine, ids
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def overlapping_commands(engine, monkeypatch, first, second):
    """Hold the first write before audit/commit and prove the second is DB-blocked."""
    reached, release = Event(), Event()
    mutex = Lock()
    original = AuditEventService.record
    first_record = True
    def hold(service, **kwargs):
        nonlocal first_record
        with mutex:
            hold_this = first_record
            first_record = False
        if hold_this:
            reached.set()
            assert release.wait(8), 'test did not release first transaction'
        return original(service, **kwargs)
    monkeypatch.setattr(AuditEventService, 'record', hold)
    def execute(fn):
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            try:
                row = fn(db)
                return ('ok', row.id, getattr(row, 'snapshot_number', None))
            except (ProductionError, SnapshotError, ApprovalError, DistributionError) as exc:
                assert not db.in_transaction(), 'failure must release the transaction'
                return ('conflict', str(exc), None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(execute, first)
        try:
            assert reached.wait(5), 'first command never reached audit'
            two = pool.submit(execute, second)
            deadline = time.monotonic() + 5
            while True:
                with engine.connect() as connection:
                    waiting = connection.scalar(text("""SELECT count(*) FROM pg_stat_activity
                        WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid)) > 0"""))
                if waiting:
                    break
                assert time.monotonic() < deadline, 'second command did not wait on PostgreSQL lock'
                time.sleep(0.01)
        finally:
            release.set()
        return one.result(timeout=10), two.result(timeout=10)


def count(db, model, **filters):
    return db.scalar(select(func.count()).select_from(model).filter_by(**filters))


@pytest.mark.parametrize('same_key', [False, True])
def test_snapshot_number_allocation_and_identical_concurrent_retry(pg, monkeypatch, same_key):
    engine, ids = pg
    key1 = uuid.uuid4(); key2 = key1 if same_key else uuid.uuid4()
    before = None
    with Session(engine) as db: before = count(db, AuditEvent)
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: SnapshotService().create(db, ids['release'], request_id=key1),
        lambda db: SnapshotService().create(db, ids['release'], request_id=key2))
    assert first[0] == second[0] == 'ok'
    assert (first[1] == second[1]) == same_key
    assert (first[2], second[2]) == ((2, 2) if same_key else (2, 3))
    with Session(engine) as db:
        added = 1 if same_key else 2
        assert count(db, ReleaseSnapshot) == 1 + added
        assert count(db, SnapshotArtifact) == 1 + added
        assert count(db, AuditEvent) == before + added


@pytest.mark.parametrize('different_deployment', [False, True])
def test_finite_batch_limit_is_serialized_across_shared_authorization(pg, monkeypatch, different_deployment):
    engine, _ = pg
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: ProductionService(db).create_batch('DEP-1', 'B1', request_id=uuid.uuid4()),
        lambda db: ProductionService(db).create_batch('DEP-2' if different_deployment else 'DEP-1',
                                                     'B2', request_id=uuid.uuid4()))
    assert first[0] == 'ok' and second[0] == 'conflict' and 'batch limit' in second[1]
    with Session(engine) as db:
        assert count(db, ProductionBatch) == 1
        assert count(db, AuditEvent, entity_type='PRODUCTION_BATCH') == 1


@pytest.mark.parametrize('changed', [False, True])
def test_concurrent_batch_retry_or_payload_conflict_does_not_consume_second_quota(pg, monkeypatch, changed):
    engine, _ = pg; key = uuid.uuid4()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: ProductionService(db).create_batch('DEP-1', 'B', request_id=key),
        lambda db: ProductionService(db).create_batch('DEP-1', 'B', request_id=key,
                                                      note='changed' if changed else None))
    assert first[0] == 'ok'
    assert second[0] == ('conflict' if changed else 'ok')
    if changed: assert 'request_id' in second[1]
    else: assert second[1] == first[1]
    with Session(engine) as db:
        assert count(db, ProductionBatch) == 1
        assert count(db, AuditEvent, entity_type='PRODUCTION_BATCH') == 1


def test_unlimited_authorization_allows_both_batches(pg, monkeypatch):
    engine, ids = pg
    with Session(engine) as db:
        authorization = db.get(SoftwareAuthorization, ids['authorization'])
        authorization.batch_limit = None; db.commit()
    results = overlapping_commands(engine, monkeypatch,
        lambda db: ProductionService(db).create_batch('DEP-1', 'B1'),
        lambda db: ProductionService(db).create_batch('DEP-2', 'B2'))
    assert all(result[0] == 'ok' for result in results)
    with Session(engine) as db:
        assert count(db, ProductionBatch) == 2
        assert count(db, AuditEvent, entity_type='PRODUCTION_BATCH') == 2


@pytest.mark.parametrize('kind', ['snapshot', 'batch'])
def test_postgres_audit_failure_rolls_back_and_releases_locks(pg, monkeypatch, kind):
    engine, ids = pg; key = uuid.uuid4()
    def run(db):
        if kind == 'snapshot': return SnapshotService().create(db, ids['release'], request_id=key)
        return ProductionService(db).create_batch('DEP-1', 'B', request_id=key)
    with Session(engine) as db:
        before = {model: count(db, model) for model in (ReleaseSnapshot, SnapshotArtifact, ProductionBatch, AuditEvent)}
        original = AuditEventService.record
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('audit failure')
        monkeypatch.setattr(AuditEventService, 'record', fail)
        with pytest.raises(RuntimeError): run(db)
        assert not db.in_transaction()
        assert {model: count(db, model) for model in before} == before
        db.rollback()
        monkeypatch.setattr(AuditEventService, 'record', original)
    with Session(engine) as db:
        db.execute(text("SET LOCAL lock_timeout = '1s'"))
        assert run(db).id == key


def test_concurrent_same_snapshot_key_different_release_conflicts_atomically(pg, monkeypatch):
    engine, ids = pg; key = uuid.uuid4()
    with Session(engine) as db:
        source = db.get(Release, ids['release'])
        other = Release(software_id=source.software_id, release_type='STANDARD', version='2')
        db.add(other); db.commit(); other_id = other.id
        prepare_snapshot_source(db, other)
    results = overlapping_commands(engine, monkeypatch,
        lambda db: SnapshotService().create(db, ids['release'], request_id=key),
        lambda db: SnapshotService().create(db, other_id, request_id=key))
    assert results[0][0] == 'ok' and results[1][0] == 'conflict'
    with Session(engine) as db:
        assert count(db, ReleaseSnapshot, release_id=other_id) == 0
        assert count(db, ReleaseSnapshot) == count(db, SnapshotArtifact) == 2
        assert count(db, AuditEvent, entity_type='RELEASE_SNAPSHOT') == 2


@pytest.mark.parametrize('stale', ['deployment', 'authorization'])
def test_batch_refreshes_scope_state_loaded_before_lock(pg, stale):
    engine, ids = pg
    with Session(engine, expire_on_commit=False) as db:
        deployment = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        authorization = db.get(SoftwareAuthorization, ids['authorization'])
        db.commit()  # identity map deliberately retains the original values
        with Session(engine) as writer:
            if stale == 'deployment':
                row = writer.get(Deployment, deployment.id); row.status = 'MISMATCH'
            else:
                row = writer.get(SoftwareAuthorization, authorization.id); row.batch_limit = 0
            writer.commit()
        with pytest.raises(ProductionError):
            ProductionService(db).create_batch('DEP-1', 'B')
        assert not db.in_transaction()
        assert count(db, ProductionBatch) == 0
        assert count(db, AuditEvent, entity_type='PRODUCTION_BATCH') == 0


def test_batch_naive_timestamp_is_stored_as_utc_and_replays(pg):
    from datetime import datetime, timezone
    engine, _ = pg; key = uuid.uuid4()
    with Session(engine) as db:
        row = ProductionService(db).create_batch('DEP-1', 'B', request_id=key,
                                                  started_at=datetime(2026, 1, 1))
        assert row.started_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        row = ProductionService(db).create_batch('DEP-1', 'B', request_id=key,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert row.id == key
        assert count(db, AuditEvent, entity_type='PRODUCTION_BATCH') == 1
