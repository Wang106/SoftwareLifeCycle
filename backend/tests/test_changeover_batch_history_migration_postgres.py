"""Real PostgreSQL migration round-trip and guards for Changeover/Batch history."""
import uuid
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from app.models.production_history import (
    BatchBaseline,
    BatchCorrection,
    ChangeoverBaseline,
    ChangeoverCorrection,
)


@pytest.fixture
def with_changeover_batch(pg):
    """Downgrade to 0028, create a changeover and batch, then re-upgrade."""
    engine, ids = pg
    config = Config('alembic.ini')
    command.downgrade(config, '0028_deployment_actual_guard')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        other_release = db.scalar(select(Deployment).where(
            Deployment.deployment_no == 'DEP-2'))
        # A distinct "from" release id; reuse the release of DEP-2 for a
        # different source, which is valid as long as it differs from target.
        from_release_id = ids['release']
        changeover = SoftwareChangeover(
            changeover_no='CO-MIG', deployment_id=dep.id,
            authorization_id=dep.authorization_id,
            from_release_id=from_release_id, to_release_id=dep.expected_release_id,
            status='COMPLETED')
        db.add(changeover); db.flush()
        batch = ProductionBatch(
            batch_no='PB-MIG', deployment_id=dep.id, changeover_id=changeover.id,
            authorization_id=dep.authorization_id, release_id=dep.expected_release_id,
            snapshot_id=dep.expected_snapshot_id, status='ACTIVE')
        db.add(batch); db.commit()
        changeover_id = changeover.id
        batch_id = batch.id
    command.upgrade(config, 'head')
    return engine, ids, changeover_id, batch_id


def test_upgrade_captures_legacy_changeover_and_batch_baselines(with_changeover_batch):
    engine, ids, changeover_id, batch_id = with_changeover_batch
    with Session(engine) as db:
        co_baseline = db.scalar(select(ChangeoverBaseline).where(
            ChangeoverBaseline.changeover_id == changeover_id))
        assert co_baseline is not None and co_baseline.source == 'LEGACY_CURRENT'
        assert co_baseline.to_release_id == db.scalar(select(Deployment).where(
            Deployment.deployment_no == 'DEP-1')).expected_release_id
        b_baseline = db.scalar(select(BatchBaseline).where(
            BatchBaseline.batch_id == batch_id))
        assert b_baseline is not None and b_baseline.source == 'LEGACY_CURRENT'
        assert b_baseline.release_id == db.scalar(select(Deployment).where(
            Deployment.deployment_no == 'DEP-1')).expected_release_id


def test_frozen_physical_columns_reject_in_place_update(with_changeover_batch):
    engine, ids, changeover_id, batch_id = with_changeover_batch
    with Session(engine) as db:
        changeover = db.scalar(select(SoftwareChangeover).where(
            SoftwareChangeover.id == changeover_id))
        # Attempt to overwrite a frozen recorded fact (note) in place.
        changeover.note = 'mutated'
        from sqlalchemy.exc import OperationalError
        with pytest.raises(OperationalError):
            db.flush()
        db.rollback()
        # No-op transition is allowed.
        changeover = db.scalar(select(SoftwareChangeover).where(
            SoftwareChangeover.id == changeover_id))
        changeover.note = changeover.note
        db.flush()
        db.rollback()


def test_batch_correction_ended_before_started_rejected(with_changeover_batch):
    from datetime import datetime, timedelta, timezone
    engine, ids, changeover_id, batch_id = with_changeover_batch
    with Session(engine) as db:
        baseline = db.scalar(select(BatchBaseline).where(
            BatchBaseline.batch_id == batch_id))
        now = datetime.now(timezone.utc)
        bad = BatchCorrection(
            id=uuid.uuid4(), batch_id=batch_id, baseline_id=baseline.id,
            predecessor_id=None, revision=1,
            started_at=now, ended_at=now - timedelta(days=1),
            correction_reason='test ended before started', actor_name='test',
            request_json={}, audit_event_no='EVT-BC-x',
        )
        db.add(bad)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_downgrade_blocks_with_correction_history(with_changeover_batch):
    from datetime import datetime, timezone
    engine, ids, changeover_id, batch_id = with_changeover_batch
    with Session(engine) as db:
        baseline = db.scalar(select(ChangeoverBaseline).where(
            ChangeoverBaseline.changeover_id == changeover_id))
        db.add(ChangeoverCorrection(
            id=uuid.uuid4(), changeover_id=changeover_id, baseline_id=baseline.id,
            predecessor_id=None, revision=1,
            from_release_id=ids['release'], changed_at=datetime.now(timezone.utc),
            note='corrected', correction_reason='Correct the source',
            actor_name='test', request_json={}, audit_event_no='EVT-CC-x',
        ))
        db.commit()
    config = Config('alembic.ini')
    with pytest.raises(Exception, match='corrections'):
        command.downgrade(config, '0028_deployment_actual_guard')


def test_downgrade_allows_pure_legacy_baselines(with_changeover_batch):
    engine, ids, changeover_id, batch_id = with_changeover_batch
    config = Config('alembic.ini')
    # Pure LEGACY_CURRENT baselines (no corrections, no FIRST_RECORD) permit downgrade.
    command.downgrade(config, '0028_deployment_actual_guard')
    command.upgrade(config, 'head')
    with Session(engine) as db:
        assert db.scalar(select(ChangeoverBaseline).where(
            ChangeoverBaseline.changeover_id == changeover_id)) is not None
        assert db.scalar(select(BatchBaseline).where(
            BatchBaseline.batch_id == batch_id)) is not None
