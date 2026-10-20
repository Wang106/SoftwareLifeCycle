"""Append-only Deployment actual history: baseline, correction ledger and projection."""
import uuid
from datetime import datetime
import pytest
from sqlalchemy import select, func
from test_production_retry import production, counts
from test_distribution_catalog import chain
from test_impact_assessments import context
from test_command_audit import trusted_actor
from app.models.production import Deployment
from app.models.production_history import DeploymentActualBaseline, DeploymentActualCorrection
from app.models.audit import AuditEvent
from app.services.production import ProductionService, ProductionError
from app.services.production_history import effective_actual


def report(db, dep, release, snapshot, **kw):
    return ProductionService(db).report_actual(
        deployment_no='DEP', actual_release_id=release.id,
        actual_snapshot_id=snapshot.id, **kw)


def test_first_report_creates_first_report_baseline(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    result = report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0)
    assert result.actual_version == 1
    baseline = db.scalar(select(DeploymentActualBaseline).where(
        DeploymentActualBaseline.deployment_id == dep.id))
    assert baseline is not None and baseline.source == 'FIRST_REPORT'
    assert baseline.actual_release_id == release.id
    assert baseline.recorded_actual_version == 1
    # No correction rows on first report.
    assert db.scalar(select(func.count()).select_from(DeploymentActualCorrection)) == 0


def test_keyed_correction_appends_ledger_and_keeps_baseline(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0)
    first_baseline = db.scalar(select(DeploymentActualBaseline).where(
        DeploymentActualBaseline.deployment_id == dep.id))
    # A correction to a different (valid) snapshot.
    other = db.scalar(select(snapshot.__class__).where(snapshot.__class__.id != snapshot.id).limit(1))
    if other is None:
        # Create a second frozen snapshot on the same release for correction.
        from app.models.snapshot import ReleaseSnapshot
        other = ReleaseSnapshot(release_id=release.id, snapshot_no='SNAP-B',
                                snapshot_number=2, content_hash='b' * 64, status='FROZEN')
        db.add(other); db.commit()
    result = report(db, dep, release, other, request_id=uuid.uuid4(),
                    expected_version=1, correction_reason='Corrected snapshot')
    assert result.actual_version == 2
    baseline = db.scalar(select(DeploymentActualBaseline).where(
        DeploymentActualBaseline.deployment_id == dep.id))
    # Baseline is unchanged (still first reported value).
    assert baseline.id == first_baseline.id
    assert baseline.actual_snapshot_id == snapshot.id
    corrections = db.scalars(select(DeploymentActualCorrection).where(
        DeploymentActualCorrection.deployment_id == dep.id).order_by(
        DeploymentActualCorrection.revision)).all()
    assert [c.revision for c in corrections] == [1]
    assert corrections[0].actual_snapshot_id == other.id
    assert corrections[0].correction_reason == 'Corrected snapshot'
    assert corrections[0].predecessor_id is None


def test_correction_chain_is_sequential_with_predecessors(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0)
    from app.models.snapshot import ReleaseSnapshot
    snap_b = ReleaseSnapshot(release_id=release.id, snapshot_no='SNAP-B',
                             snapshot_number=2, content_hash='b' * 64, status='FROZEN')
    snap_c = ReleaseSnapshot(release_id=release.id, snapshot_no='SNAP-C',
                             snapshot_number=3, content_hash='c' * 64, status='FROZEN')
    db.add_all([snap_b, snap_c]); db.commit()
    report(db, dep, release, snap_b, request_id=uuid.uuid4(), expected_version=1,
           correction_reason='First correction')
    report(db, dep, release, snap_c, request_id=uuid.uuid4(), expected_version=2,
           correction_reason='Second correction')
    rows = db.scalars(select(DeploymentActualCorrection).where(
        DeploymentActualCorrection.deployment_id == dep.id).order_by(
        DeploymentActualCorrection.revision)).all()
    assert [r.revision for r in rows] == [1, 2]
    assert rows[0].predecessor_id is None
    assert rows[1].predecessor_id == rows[0].id
    # Effective value reflects the head correction.
    eff = effective_actual(db, db.get(Deployment, dep.id))
    assert eff.actual_version == 3
    assert eff.actual_snapshot_id == snap_c.id
    assert eff.history_state == 'FIRST_REPORT_CORRECTED'
    assert eff.correction_count == 2


def test_legacy_no_key_overwrite_does_not_create_correction(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    # Legacy no-key first report then a second no-key overwrite (behavior preserved).
    assert report(db, dep, release, snapshot, request_id=None, expected_version=None).actual_version == 1
    assert report(db, dep, release, snapshot, request_id=None, expected_version=None).actual_version == 2
    # No correction rows: legacy no-key overwrite is not a keyed correction.
    assert db.scalar(select(func.count()).select_from(DeploymentActualCorrection)) == 0
    baseline = db.scalar(select(DeploymentActualBaseline).where(
        DeploymentActualBaseline.deployment_id == dep.id))
    assert baseline is not None and baseline.source == 'FIRST_REPORT'


def test_seeded_imported_value_is_not_first_report(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    # Simulate a pre-existing reported value (imported sample) with version 0.
    dep.actual_release_id = release.id
    dep.actual_snapshot_id = snapshot.id
    dep.status = 'MATCH'; dep.actual_version = 0
    db.commit()
    from app.models.production_history import DeploymentActualBaseline as B
    db.add(B(deployment_id=dep.id, actual_release_id=release.id, actual_snapshot_id=snapshot.id,
             recorded_status='MATCH', recorded_actual_version=0, source='IMPORTED_CURRENT'))
    db.commit()
    eff = effective_actual(db, db.get(Deployment, dep.id))
    assert eff.history_state == 'IMPORTED' or eff.history_state == 'IMPORTED_CORRECTED'
    assert eff.actual_version == 0


def test_unreported_deployment_is_not_recorded(production):
    db = production[0]; dep = production[5]
    dep.actual_release_id = None; dep.actual_snapshot_id = None; dep.status = 'PENDING'
    db.commit()
    eff = effective_actual(db, db.get(Deployment, dep.id))
    assert eff.history_state == 'NOT_RECORDED'
    assert eff.actual_release_id is None and eff.correction_count == 0


def test_baseline_and_correction_are_append_only(production, monkeypatch):
    # Append-only is enforced by the database trigger (PostgreSQL) and by the
    # append-only write path here. Unit-level: corrections are never mutated
    # in place; a correction always creates a new row.
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0)
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=1,
           correction_reason='First correction')
    before = db.scalar(select(func.count()).select_from(DeploymentActualCorrection))
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=2,
           correction_reason='Second correction')
    assert db.scalar(select(func.count()).select_from(DeploymentActualCorrection)) == before + 1


def test_correction_requires_reason_and_matches_expected_version(production):
    db = production[0]; dep = production[5]; release = production[6]; snapshot = production[7]
    report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0)
    with pytest.raises(ProductionError, match='actual_version'):
        report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=0,
               correction_reason='Wrong version')
    with pytest.raises(ProductionError, match='correction_reason'):
        report(db, dep, release, snapshot, request_id=uuid.uuid4(), expected_version=1,
               correction_reason=None)
