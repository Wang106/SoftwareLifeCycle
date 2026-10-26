"""The scoped HTTP child check must remain locked until command transaction ends."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.api.production import _require_correction_target
from app.models.core import Release
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from test_command_concurrency_postgres import pg  # noqa: F401


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_scoped_child_lock_blocks_attribution_change_until_transaction_ends(pg, kind):
    engine, ids = pg
    with Session(engine) as db:
        deployment = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        other = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-2'))
        if kind == 'changeover':
            release = db.get(Release, ids['release'])
            source = Release(software_id=release.software_id, release_type='STANDARD', version='lock-source')
            db.add(source); db.flush()
            model, number_column, number = SoftwareChangeover, SoftwareChangeover.changeover_no, 'LOCK-CO'
            child = SoftwareChangeover(changeover_no=number, deployment_id=deployment.id,
                authorization_id=deployment.authorization_id, from_release_id=source.id,
                to_release_id=deployment.expected_release_id, status='COMPLETED',
                changed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        else:
            model, number_column, number = ProductionBatch, ProductionBatch.batch_no, 'LOCK-BATCH'
            child = ProductionBatch(batch_no=number, deployment_id=deployment.id,
                authorization_id=deployment.authorization_id, release_id=deployment.expected_release_id,
                snapshot_id=deployment.expected_snapshot_id, started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        db.add(child); db.commit()
        child_id, original_id, other_id = child.id, deployment.id, other.id
    held, release_lock, competitor_ready = Event(), Event(), Event()
    pids = {}

    def hold_scope():
        with Session(engine) as db:
            pids['holder'] = db.scalar(text('SELECT pg_backend_pid()'))
            _require_correction_target(db, 'DEP-1', model, number_column, number)
            held.set()
            try:
                assert release_lock.wait(8), 'test did not release scoped transaction'
            finally:
                db.rollback()

    def reassign_then_rollback():
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            pids['competitor'] = db.scalar(text('SELECT pg_backend_pid()'))
            competitor_ready.set()
            try:
                result = db.execute(update(model).where(model.id == child_id).values(deployment_id=other_id))
                assert result.rowcount == 1
            finally:
                db.rollback()  # No attribution mutation retained, even on test failure.

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(hold_scope)
        competitor = None
        try:
            assert held.wait(5), 'scoped lookup did not complete'
            competitor = pool.submit(reassign_then_rollback)
            assert competitor_ready.wait(5), 'competing UPDATE did not start'
            deadline = time.monotonic() + 5
            while True:
                with engine.connect() as connection:
                    blockers = connection.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pids['competitor']})
                if pids['holder'] in blockers:
                    break
                assert time.monotonic() < deadline, 'competing attribution change was not blocked by scoped lookup'
                time.sleep(.01)
        finally:
            release_lock.set()
        holder.result(timeout=10)
        if competitor is not None:
            competitor.result(timeout=10)
    with Session(engine) as db:
        assert db.get(model, child_id).deployment_id == original_id
