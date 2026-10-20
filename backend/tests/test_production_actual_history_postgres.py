"""Real PostgreSQL: append-only actual history concurrency, triggers and migration."""
import uuid
from datetime import datetime
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg, count, overlapping_commands
from app.models.production import Deployment
from app.models.production_history import DeploymentActualBaseline, DeploymentActualCorrection
from app.models.audit import AuditEvent
from app.services.production import ProductionService, ProductionError


@pytest.fixture
def actual(pg):
    engine, ids = pg
    config = Config('alembic.ini')
    command.downgrade(config, '0026_release_chain_revocation')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        ids = {**ids, 'snapshot': dep.expected_snapshot_id}
        for dep in db.scalars(select(Deployment)):
            dep.actual_release_id = dep.actual_snapshot_id = dep.deployed_at = None
            dep.status = 'PENDING'
            dep.actual_version = 0
        db.commit()
    command.upgrade(config, 'head')
    return engine, ids


def report(db, ids, key, **changes):
    return ProductionService(db).report_actual(**{
        **dict(deployment_no='DEP-1', actual_release_id=ids['release'],
               actual_snapshot_id=ids['snapshot'], request_id=key, expected_version=0),
        **changes})


def test_concurrent_corrections_serialize_to_sequential_revisions(actual, monkeypatch):
    engine, ids = actual
    with Session(engine) as db:
        report(db, ids, uuid.uuid4())
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: report(db, ids, uuid.uuid4(), expected_version=1, correction_reason='First'),
        lambda db: report(db, ids, uuid.uuid4(), expected_version=1, correction_reason='Second'))
    assert first[0] == 'ok' and second[0] == 'conflict'
    with Session(engine) as db:
        rows = db.scalars(select(DeploymentActualCorrection).where(
            DeploymentActualCorrection.deployment_id == db.scalar(
                select(Deployment).where(Deployment.deployment_no == 'DEP-1')).id
        ).order_by(DeploymentActualCorrection.revision)).all()
        assert [r.revision for r in rows] == [1]


def test_correction_does_not_mutate_baseline(actual):
    engine, ids = actual
    key = uuid.uuid4()
    with Session(engine) as db:
        report(db, ids, key)
        baseline = db.scalar(select(DeploymentActualBaseline))
        baseline_snapshot = baseline.actual_snapshot_id
        baseline_version = baseline.recorded_actual_version
        report(db, ids, uuid.uuid4(), expected_version=1, correction_reason='Correct')
        db.expire_all()
        baseline_after = db.scalar(select(DeploymentActualBaseline))
        assert baseline_after.actual_snapshot_id == baseline_snapshot
        assert baseline_after.recorded_actual_version == baseline_version
        assert db.scalar(select(DeploymentActualCorrection)).revision == 1


def test_append_only_trigger_rejects_mutation(actual):
    engine, ids = actual
    with Session(engine) as db:
        report(db, ids, uuid.uuid4())
        baseline = db.scalar(select(DeploymentActualBaseline))
        baseline_id = baseline.id
        db.commit()
    with Session(engine) as db:
        # Append-only triggers raise an ObjectNotInPrerequisiteState (ERRCODE 55000),
        # surfaced by psycopg/SQLAlchemy as OperationalError.
        with pytest.raises(OperationalError):
            db.execute(text(
                "UPDATE deployment_actual_baselines SET source='FIRST_REPORT' "
                "WHERE id=:id"), {'id': baseline_id})
        db.rollback()
        # DELETE is also rejected by the append-only trigger.
        with pytest.raises(OperationalError):
            db.execute(text("DELETE FROM deployment_actual_baselines WHERE id=:id"),
                       {'id': baseline_id})
        db.rollback()
        assert db.scalar(select(DeploymentActualBaseline)) is not None



def test_deployment_old_writer_guard_rejects_overwrite_and_delete(actual):
    engine, ids = actual
    with Session(engine) as db:
        report(db, ids, uuid.uuid4())
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        dep_id = dep.id
        db.commit()
    with Session(engine) as db:
        with pytest.raises(OperationalError):
            db.execute(text("UPDATE deployments SET status='PENDING' WHERE id=:id"),
                       {'id': dep_id})
            db.commit()
        db.rollback()
        # A genuine no-op remains safe for legacy code paths that persist a loaded row.
        db.execute(text("UPDATE deployments SET status=status WHERE id=:id"),
                   {'id': dep_id})
        db.commit()
        with pytest.raises(OperationalError):
            db.execute(text("DELETE FROM deployments WHERE id=:id"), {'id': dep_id})
            db.commit()
        db.rollback()


def test_deferred_guard_requires_matching_baseline_for_first_report(actual):
    engine, ids = actual
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-2'))
        with pytest.raises(OperationalError):
            db.execute(text("""UPDATE deployments
                SET actual_release_id=:release_id,
                    actual_snapshot_id=:snapshot_id,
                    status='MATCH', actual_version=1, deployed_at=now()
                WHERE id=:id"""), {
                    'release_id': ids['release'], 'snapshot_id': dep.expected_snapshot_id,
                    'id': dep.id,
                })
            db.commit()
        db.rollback()
        unchanged = db.get(Deployment, dep.id)
        assert unchanged.actual_release_id is None
        assert unchanged.actual_snapshot_id is None


def test_legacy_reported_deployment_captured_as_legacy_current(pg):
    """Migration captures a pre-existing reported value as LEGACY_CURRENT."""
    engine, ids = pg
    config = Config('alembic.ini')
    command.downgrade(config, '0026_release_chain_revocation')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        dep.actual_release_id = ids['release']
        dep.actual_snapshot_id = dep.expected_snapshot_id
        dep.status = 'MATCH'
        db.commit()
    command.upgrade(config, 'head')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        baseline = db.scalar(select(DeploymentActualBaseline).where(
            DeploymentActualBaseline.deployment_id == dep.id))
        assert baseline is not None
        assert baseline.source == 'LEGACY_CURRENT'
        assert baseline.actual_release_id == ids['release']
        assert baseline.recorded_actual_version == dep.actual_version
