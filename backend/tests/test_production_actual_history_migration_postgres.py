"""Real PostgreSQL migration round-trip and downgrade guards for actual history."""
import uuid
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from app.models.production import Deployment
from app.models.production_history import DeploymentActualBaseline, DeploymentActualCorrection
from app.services.production import ProductionService


def report(db, dep, release_id, snapshot_id, key):
    return ProductionService(db).report_actual(
        deployment_no=dep.deployment_no, actual_release_id=release_id,
        actual_snapshot_id=snapshot_id, request_id=key, expected_version=0)


def test_upgrade_captures_existing_reported_deployments(pg):
    engine, ids = pg
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        dep.actual_release_id = ids['release']
        dep.actual_snapshot_id = dep.expected_snapshot_id
        dep.status = 'MATCH'
        db.commit()
    config = Config('alembic.ini')
    command.downgrade(config, '0026_release_chain_revocation')
    command.upgrade(config, 'head')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        baseline = db.scalar(select(DeploymentActualBaseline).where(
            DeploymentActualBaseline.deployment_id == dep.id))
        assert baseline is not None and baseline.source == 'LEGACY_CURRENT'


def test_downgrade_blocks_with_correction_history(pg):
    engine, ids = pg
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        report(db, dep, ids['release'], dep.expected_snapshot_id, uuid.uuid4())
        report(db, dep, ids['release'], dep.expected_snapshot_id, uuid.uuid4(),
               expected_version=1, correction_reason='Correct')
    config = Config('alembic.ini')
    with pytest.raises(Exception, match='corrections'):
        command.downgrade(config, '0026_release_chain_revocation')


def test_downgrade_allows_pure_import_baseline(pg):
    engine, ids = pg
    config = Config('alembic.ini')
    # With no corrections and no FIRST_REPORT baseline, downgrade is permitted.
    command.downgrade(config, '0026_release_chain_revocation')
    command.upgrade(config, 'head')
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        assert db.scalar(select(DeploymentActualBaseline).where(
            DeploymentActualBaseline.deployment_id == dep.id)) is None


def test_first_report_baseline_blocks_downgrade(pg):
    engine, ids = pg
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP-1'))
        report(db, dep, ids['release'], dep.expected_snapshot_id, uuid.uuid4())
    config = Config('alembic.ini')
    with pytest.raises(Exception, match='first-report'):
        command.downgrade(config, '0026_release_chain_revocation')
