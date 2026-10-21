"""Changeover/Batch append-only history: baseline, correction ledger and projection."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.models.production_history import (
    BatchBaseline,
    BatchCorrection,
    ChangeoverBaseline,
    ChangeoverCorrection,
)
from app.services.production_history import effective_batch, effective_changeover

from test_production_catalog import production  # noqa: F401
from test_distribution_catalog import chain  # noqa: F401
from test_impact_assessments import context  # noqa: F401


def test_changeover_projection_reads_baseline_when_no_correction(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    # Without a baseline the projection is NOT_RECORDED and falls back to
    # the physical recorded columns.
    eff = effective_changeover(db, co)
    assert eff.history_state == 'NOT_RECORDED'
    assert eff.from_release_id == co.from_release_id
    assert eff.to_release_id == co.to_release_id
    assert eff.correction_count == 0


def test_changeover_correction_overrides_effective_value(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    baseline = ChangeoverBaseline(
        changeover_id=co.id, from_release_id=co.from_release_id,
        to_release_id=co.to_release_id, recorded_status=co.status,
        recorded_changed_at=co.changed_at, recorded_note=co.note,
        source='IMPORTED_CURRENT')
    db.add(baseline); db.flush()
    changed = datetime.now(timezone.utc)
    db.add(ChangeoverCorrection(
        id=uuid.uuid4(), changeover_id=co.id, baseline_id=baseline.id,
        predecessor_id=None, revision=1, from_release_id=old.id,
        changed_at=changed, note='corrected note',
        correction_reason='Correct the changeover source', actor_name='tester',
        request_json={}, audit_event_no='EVT-CC-test'))
    db.commit()
    eff = effective_changeover(db, co)
    assert eff.history_state == 'IMPORTED_CORRECTED'
    assert eff.from_release_id == old.id
    assert eff.to_release_id == co.to_release_id  # target never corrected
    assert eff.correction_count == 1
    assert eff.note == 'corrected note'


def test_batch_projection_keeps_software_and_overrides_time(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    baseline = BatchBaseline(
        batch_id=batch.id, release_id=batch.release_id, snapshot_id=batch.snapshot_id,
        changeover_id=batch.changeover_id, recorded_status=batch.status,
        recorded_started_at=batch.started_at, recorded_ended_at=batch.ended_at,
        recorded_note=batch.note, source='IMPORTED_CURRENT')
    db.add(baseline); db.flush()
    new_start = datetime.now(timezone.utc)
    db.add(BatchCorrection(
        id=uuid.uuid4(), batch_id=batch.id, baseline_id=baseline.id,
        predecessor_id=None, revision=1, started_at=new_start, ended_at=None,
        note='corrected start', correction_reason='Correct batch start time',
        actor_name='tester', request_json={}, audit_event_no='EVT-BC-test'))
    db.commit()
    eff = effective_batch(db, batch)
    assert eff.history_state == 'IMPORTED_CORRECTED'
    # Software binding (release/snapshot) is the recorded value, never corrected.
    assert eff.release_id == batch.release_id
    assert eff.snapshot_id == batch.snapshot_id
    assert eff.started_at is not None
    assert eff.note == 'corrected start'
    assert eff.correction_count == 1


def test_map_projections_are_bounded(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    from app.services.production_history import effective_batch_map, effective_changeover_map
    co_map = effective_changeover_map(db, [co])
    batch_map = effective_batch_map(db, batches)
    assert co_map[co.id].history_state == 'NOT_RECORDED'
    for b in batches:
        assert batch_map[b.id].history_state == 'NOT_RECORDED'
