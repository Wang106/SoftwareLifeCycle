"""Changeover/Batch correction write commands: append-only ledger, chain and idempotency."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, func

from app.models.core import Release
from app.models.production import Deployment
from app.models.production_history import (
    ChangeoverBaseline,
    ChangeoverCorrection,
    BatchBaseline,
    BatchCorrection,
)
from app.services.production import ProductionService, ProductionError
from app.services.production_history import effective_batch, effective_changeover

from test_production_catalog import production  # noqa: F401
from test_distribution_catalog import chain  # noqa: F401
from test_impact_assessments import context  # noqa: F401


def make_release(db, release, version):
    """Create a distinct release sharing the same software product."""
    row = Release(software_id=release.software_id, release_type=release.release_type,
                  version=version, status='RELEASED')
    db.add(row); db.commit()
    return row


def correct_changeover(db, co, release, **kw):
    return ProductionService(db).correct_changeover(
        changeover_no=co.changeover_no, from_release_id=release.id, **kw)


def test_changeover_correction_requires_key_and_reason(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    with pytest.raises(ProductionError, match='requires request_id'):
        correct_changeover(db, co, src)
    with pytest.raises(ProductionError, match='expected_revision'):
        correct_changeover(db, co, src, request_id=uuid.uuid4())
    with pytest.raises(ProductionError, match='correction_reason'):
        correct_changeover(db, co, src, request_id=uuid.uuid4(), expected_revision=0)


def test_changeover_correction_appends_ledger_and_keeps_target(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    changed = datetime(2026, 2, 1, tzinfo=timezone.utc)
    result = correct_changeover(
        db, co, src, request_id=uuid.uuid4(), expected_revision=0,
        changed_at=changed, note='corrected source', correction_reason='Wrong source recorded')
    assert result.from_release_id == src.id
    baseline = db.scalar(select(ChangeoverBaseline).where(
        ChangeoverBaseline.changeover_id == co.id))
    assert baseline is not None
    head = db.scalar(select(ChangeoverCorrection).where(
        ChangeoverCorrection.changeover_id == co.id).order_by(
        ChangeoverCorrection.revision.desc()).limit(1))
    assert head.revision == 1 and head.predecessor_id is None
    assert head.from_release_id == src.id and head.note == 'corrected source'
    eff = effective_changeover(db, co)
    assert eff.from_release_id == src.id
    # target release is never corrected
    assert eff.to_release_id == co.to_release_id
    assert eff.history_state.endswith('CORRECTED')


def test_changeover_correction_chain_is_sequential(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    third = make_release(db, release, '0.8.0')
    first_key = uuid.uuid4()
    r1 = correct_changeover(db, co, src, request_id=first_key, expected_revision=0,
                            correction_reason='First correction')
    r2 = correct_changeover(db, co, third, request_id=uuid.uuid4(), expected_revision=1,
                            predecessor_id=first_key, correction_reason='Second correction')
    assert r2.from_release_id == third.id
    rows = db.scalars(select(ChangeoverCorrection).where(
        ChangeoverCorrection.changeover_id == co.id).order_by(
        ChangeoverCorrection.revision)).all()
    assert [r.revision for r in rows] == [1, 2]
    assert rows[0].predecessor_id is None
    assert rows[1].predecessor_id == rows[0].id


def test_changeover_correction_rejects_version_conflict(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    correct_changeover(db, co, src, request_id=uuid.uuid4(), expected_revision=0,
                       correction_reason='First correction')
    with pytest.raises(ProductionError, match='revision conflict'):
        correct_changeover(db, co, src, request_id=uuid.uuid4(), expected_revision=0,
                           correction_reason='Stale version')


def test_changeover_correction_rejects_wrong_predecessor(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    correct_changeover(db, co, src, request_id=uuid.uuid4(), expected_revision=0,
                       correction_reason='First correction')
    with pytest.raises(ProductionError, match='predecessor_id'):
        correct_changeover(db, co, src, request_id=uuid.uuid4(), expected_revision=1,
                           predecessor_id=uuid.uuid4(), correction_reason='Wrong predecessor')


def test_changeover_correction_rejects_same_source_target(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    with pytest.raises(ProductionError, match='must differ'):
        ProductionService(db).correct_changeover(
            changeover_no=co.changeover_no, from_release_id=dep.expected_release_id,
            request_id=uuid.uuid4(), expected_revision=0,
            correction_reason='Same source target')


def test_changeover_correction_is_idempotent(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    key = uuid.uuid4()
    changed = datetime(2026, 3, 1, tzinfo=timezone.utc)
    first = correct_changeover(db, co, src, request_id=key, expected_revision=0,
                               changed_at=changed, correction_reason='Idempotent')
    replay = correct_changeover(db, co, src, request_id=key, expected_revision=0,
                                changed_at=changed, correction_reason='Idempotent')
    assert replay.changed_at == changed and replay.from_release_id == src.id
    assert db.scalar(select(func.count()).select_from(ChangeoverCorrection)) == 1


def test_changeover_correction_rejects_reused_key_with_different_content(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    src = make_release(db, release, '0.9.0')
    key = uuid.uuid4()
    correct_changeover(db, co, src, request_id=key, expected_revision=0,
                       correction_reason='Original content')
    with pytest.raises(ProductionError, match='request_id already used'):
        correct_changeover(db, co, src, request_id=key, expected_revision=0,
                           note='different', correction_reason='Original content')


def correct_batch(db, batch, **kw):
    return ProductionService(db).correct_batch(batch_no=batch.batch_no, **kw)


def test_batch_correction_appends_and_keeps_software(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    new_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    result = correct_batch(db, batch, request_id=uuid.uuid4(), expected_revision=0,
                           started_at=new_start, correction_reason='Corrected start time')
    assert result.started_at == new_start
    head = db.scalar(select(BatchCorrection).where(
        BatchCorrection.batch_id == batch.id).order_by(
        BatchCorrection.revision.desc()).limit(1))
    # SQLite drops tzinfo on DateTime(timezone=True), so normalize before compare.
    assert head.revision == 1
    assert head.started_at.replace(tzinfo=timezone.utc) == new_start
    eff = effective_batch(db, batch)
    # Software binding never corrected.
    assert eff.release_id == batch.release_id
    assert eff.snapshot_id == batch.snapshot_id
    assert eff.started_at is not None
    assert eff.history_state.endswith('CORRECTED')


def test_batch_correction_rejects_ended_before_started(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    start = datetime(2026, 5, 2, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ProductionError, match='ended_at'):
        correct_batch(db, batch, request_id=uuid.uuid4(), expected_revision=0,
                      started_at=start, ended_at=end, correction_reason='Bad end')


def test_batch_correction_rejects_wrong_changeover(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    with pytest.raises(ProductionError, match='changeover'):
        correct_batch(db, batch, request_id=uuid.uuid4(), expected_revision=0,
                      changeover_id=uuid.uuid4(), correction_reason='Wrong changeover')


def test_batch_correction_requires_key(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    with pytest.raises(ProductionError, match='requires request_id'):
        correct_batch(db, batch)


def test_batch_correction_is_idempotent(production):
    db, release, snapshot, old, auth, dep, pending, co, batches, site, line = production
    batch = batches[0]
    key = uuid.uuid4()
    new_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    correct_batch(db, batch, request_id=key, expected_revision=0,
                  started_at=new_start, correction_reason='Idempotent')
    replay = correct_batch(db, batch, request_id=key, expected_revision=0,
                           started_at=new_start, correction_reason='Idempotent')
    assert replay.started_at == new_start
    assert db.scalar(select(func.count()).select_from(BatchCorrection)) == 1
