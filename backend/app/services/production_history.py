"""Effective-value projection for immutable production trace history."""
import uuid
from dataclasses import dataclass
from datetime import timezone
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from app.models.audit import AuditEvent
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from app.models.production_history import (
    BatchBaseline,
    BatchCorrection,
    ChangeoverBaseline,
    ChangeoverCorrection,
    DeploymentActualBaseline,
    DeploymentActualCorrection,
)

@dataclass(frozen=True)
class EffectiveActual:
    deployment_id: uuid.UUID
    actual_release_id: uuid.UUID | None
    actual_snapshot_id: uuid.UUID | None
    status: str
    actual_version: int
    deployed_at: object
    history_state: str
    correction_count: int

def _history_state(baseline, head, proof_time):
    if baseline is None:
        return "NOT_RECORDED"
    if head is not None and proof_time is None:
        return "UNRESOLVED"
    prefix = ("LEGACY" if baseline.source == "LEGACY_CURRENT" else
              "IMPORTED" if baseline.source == "IMPORTED_CURRENT" else "FIRST_REPORT")
    return f"{prefix}_CORRECTED" if head is not None else prefix

def _utc(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc) if value is not None else None

def _derive_status(deployment, release_id, snapshot_id):
    if release_id is None and snapshot_id is None:
        return "PENDING"
    if release_id is None or snapshot_id is None:
        return "MISMATCH"
    return ("MATCH" if (release_id, snapshot_id) ==
            (deployment.expected_release_id, deployment.expected_snapshot_id)
            else "MISMATCH")

def effective_actual(db: Session, deployment: Deployment) -> EffectiveActual:
    baseline = db.scalar(select(DeploymentActualBaseline).where(
        DeploymentActualBaseline.deployment_id == deployment.id))
    head = db.scalar(select(DeploymentActualCorrection).where(
        DeploymentActualCorrection.deployment_id == deployment.id
    ).order_by(DeploymentActualCorrection.revision.desc()).limit(1))
    correction_count = db.scalar(select(func.count()).select_from(
        DeploymentActualCorrection).where(
        DeploymentActualCorrection.deployment_id == deployment.id)) or 0
    proof_time = db.scalar(select(AuditEvent.occurred_at).where(
        AuditEvent.event_no == head.audit_event_no,
        AuditEvent.entity_type == "DEPLOYMENT",
        AuditEvent.entity_id == deployment.id,
        AuditEvent.action == "ACTUAL_CORRECTED",
    )) if head is not None else None
    if baseline is None:
        return EffectiveActual(
            deployment.id, deployment.actual_release_id, deployment.actual_snapshot_id,
            deployment.status, deployment.actual_version, deployment.deployed_at,
            "UNRESOLVED" if (deployment.actual_release_id is not None
                             or deployment.actual_snapshot_id is not None)
            else "NOT_RECORDED", 0)
    release_id = head.actual_release_id if head is not None else baseline.actual_release_id
    snapshot_id = head.actual_snapshot_id if head is not None else baseline.actual_snapshot_id
    revision = head.revision if head is not None else 0
    return EffectiveActual(
        deployment.id, release_id, snapshot_id,
        _derive_status(deployment, release_id, snapshot_id),
        baseline.recorded_actual_version + revision,
        _utc(proof_time) if head is not None else _utc(baseline.recorded_deployed_at),
        _history_state(baseline, head, proof_time), correction_count)

def effective_actual_map(db: Session, deployments) -> dict:
    """Resolve page targets with bounded baseline, head/count and audit queries."""
    if not deployments:
        return {}
    ids = [row.id for row in deployments]
    baselines = {row.deployment_id: row for row in db.scalars(
        select(DeploymentActualBaseline).where(
            DeploymentActualBaseline.deployment_id.in_(ids))).all()}
    stats = select(
        DeploymentActualCorrection.deployment_id.label("deployment_id"),
        func.max(DeploymentActualCorrection.revision).label("head_revision"),
        func.count().label("correction_count"),
    ).where(DeploymentActualCorrection.deployment_id.in_(ids)).group_by(
        DeploymentActualCorrection.deployment_id).subquery()
    packed = {}
    for head, count, proof_time in db.execute(select(
        DeploymentActualCorrection, stats.c.correction_count, AuditEvent.occurred_at
    ).join(stats, and_(
        stats.c.deployment_id == DeploymentActualCorrection.deployment_id,
        stats.c.head_revision == DeploymentActualCorrection.revision,
    )).outerjoin(AuditEvent, and_(
        AuditEvent.event_no == DeploymentActualCorrection.audit_event_no,
        AuditEvent.entity_type == "DEPLOYMENT",
        AuditEvent.entity_id == DeploymentActualCorrection.deployment_id,
        AuditEvent.action == "ACTUAL_CORRECTED",
    ))).all():
        packed[head.deployment_id] = (head, int(count), proof_time)
    result = {}
    for deployment in deployments:
        baseline = baselines.get(deployment.id)
        item = packed.get(deployment.id)
        head, count, proof_time = item if item else (None, 0, None)
        if baseline is None:
            result[deployment.id] = EffectiveActual(
                deployment.id, deployment.actual_release_id, deployment.actual_snapshot_id,
                deployment.status, deployment.actual_version, deployment.deployed_at,
                "UNRESOLVED" if (deployment.actual_release_id is not None
                                 or deployment.actual_snapshot_id is not None)
                else "NOT_RECORDED", 0)
            continue
        release_id = head.actual_release_id if head is not None else baseline.actual_release_id
        snapshot_id = head.actual_snapshot_id if head is not None else baseline.actual_snapshot_id
        revision = head.revision if head is not None else 0
        result[deployment.id] = EffectiveActual(
            deployment.id, release_id, snapshot_id,
            _derive_status(deployment, release_id, snapshot_id),
            baseline.recorded_actual_version + revision,
            _utc(proof_time) if head is not None else _utc(baseline.recorded_deployed_at),
            _history_state(baseline, head, proof_time), count)
    return result


@dataclass(frozen=True)
class EffectiveChangeover:
    changeover_id: uuid.UUID
    from_release_id: uuid.UUID
    to_release_id: uuid.UUID
    changed_at: object
    note: str | None
    history_state: str
    correction_count: int


def _changeover_state(baseline, head):
    if baseline is None:
        return "NOT_RECORDED"
    prefix = ("LEGACY" if baseline.source == "LEGACY_CURRENT" else
              "IMPORTED" if baseline.source == "IMPORTED_CURRENT" else "FIRST_RECORD")
    return f"{prefix}_CORRECTED" if head is not None else prefix


def effective_changeover(db: Session, changeover: SoftwareChangeover) -> EffectiveChangeover:
    """Resolve the effective recorded facts for one Changeover.

    The physical columns preserve the recorded baseline; corrections are
    appended and never overwrite it. The effective value is the head correction
    when present, else the immutable baseline.
    """
    baseline = db.scalar(select(ChangeoverBaseline).where(
        ChangeoverBaseline.changeover_id == changeover.id))
    head = db.scalar(select(ChangeoverCorrection).where(
        ChangeoverCorrection.changeover_id == changeover.id
    ).order_by(ChangeoverCorrection.revision.desc()).limit(1))
    correction_count = db.scalar(select(func.count()).select_from(
        ChangeoverCorrection).where(
        ChangeoverCorrection.changeover_id == changeover.id)) or 0
    if baseline is None:
        return EffectiveChangeover(
            changeover.id, changeover.from_release_id, changeover.to_release_id,
            changeover.changed_at, changeover.note,
            "NOT_RECORDED", 0)
    from_release_id = head.from_release_id if head is not None else baseline.from_release_id
    changed_at = head.changed_at if head is not None else baseline.recorded_changed_at
    note = head.note if head is not None else baseline.recorded_note
    return EffectiveChangeover(
        changeover.id, from_release_id, baseline.to_release_id,
        _utc(changed_at), note,
        _changeover_state(baseline, head), correction_count)


@dataclass(frozen=True)
class EffectiveBatch:
    batch_id: uuid.UUID
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    changeover_id: uuid.UUID | None
    started_at: object
    ended_at: object
    note: str | None
    history_state: str
    correction_count: int


def _batch_state(baseline, head):
    if baseline is None:
        return "NOT_RECORDED"
    prefix = ("LEGACY" if baseline.source == "LEGACY_CURRENT" else
              "IMPORTED" if baseline.source == "IMPORTED_CURRENT" else "FIRST_RECORD")
    return f"{prefix}_CORRECTED" if head is not None else prefix


def effective_batch(db: Session, batch: ProductionBatch) -> EffectiveBatch:
    """Resolve the effective recorded facts for one ProductionBatch.

    ``release_id``/``snapshot_id`` are the recorded software binding and stay on
    the physical columns; only time/changeover/note are corrected. This mirrors
    the design rule that batch software attribution is never corrected.
    """
    baseline = db.scalar(select(BatchBaseline).where(
        BatchBaseline.batch_id == batch.id))
    head = db.scalar(select(BatchCorrection).where(
        BatchCorrection.batch_id == batch.id
    ).order_by(BatchCorrection.revision.desc()).limit(1))
    correction_count = db.scalar(select(func.count()).select_from(
        BatchCorrection).where(BatchCorrection.batch_id == batch.id)) or 0
    if baseline is None:
        return EffectiveBatch(
            batch.id, batch.release_id, batch.snapshot_id, batch.changeover_id,
            batch.started_at, batch.ended_at, batch.note, "NOT_RECORDED", 0)
    started_at = head.started_at if head is not None else baseline.recorded_started_at
    ended_at = head.ended_at if head is not None else baseline.recorded_ended_at
    changeover_id = head.changeover_id if head is not None else baseline.changeover_id
    note = head.note if head is not None else baseline.recorded_note
    return EffectiveBatch(
        batch.id, baseline.release_id, baseline.snapshot_id, changeover_id,
        _utc(started_at), _utc(ended_at), note,
        _batch_state(baseline, head), correction_count)


def effective_changeover_map(db: Session, changeovers) -> dict:
    """Resolve a page of Changeovers with bounded baseline, head/count queries."""
    if not changeovers:
        return {}
    ids = [row.id for row in changeovers]
    baselines = {row.changeover_id: row for row in db.scalars(
        select(ChangeoverBaseline).where(
            ChangeoverBaseline.changeover_id.in_(ids))).all()}
    stats = select(
        ChangeoverCorrection.changeover_id.label("changeover_id"),
        func.max(ChangeoverCorrection.revision).label("head_revision"),
        func.count().label("correction_count"),
    ).where(ChangeoverCorrection.changeover_id.in_(ids)).group_by(
        ChangeoverCorrection.changeover_id).subquery()
    packed = {}
    for head, count in db.execute(select(
        ChangeoverCorrection, stats.c.correction_count
    ).join(stats, and_(
        stats.c.changeover_id == ChangeoverCorrection.changeover_id,
        stats.c.head_revision == ChangeoverCorrection.revision,
    ))).all():
        packed[head.changeover_id] = (head, int(count))
    result = {}
    for changeover in changeovers:
        baseline = baselines.get(changeover.id)
        head, count = packed.get(changeover.id, (None, 0))
        if baseline is None:
            result[changeover.id] = EffectiveChangeover(
                changeover.id, changeover.from_release_id, changeover.to_release_id,
                changeover.changed_at, changeover.note, "NOT_RECORDED", 0)
            continue
        result[changeover.id] = EffectiveChangeover(
            changeover.id,
            head.from_release_id if head is not None else baseline.from_release_id,
            baseline.to_release_id,
            _utc(head.changed_at) if head is not None else _utc(baseline.recorded_changed_at),
            head.note if head is not None else baseline.recorded_note,
            _changeover_state(baseline, head), count)
    return result


def effective_batch_map(db: Session, batches) -> dict:
    """Resolve a page of Batches with bounded baseline, head/count queries."""
    if not batches:
        return {}
    ids = [row.id for row in batches]
    baselines = {row.batch_id: row for row in db.scalars(
        select(BatchBaseline).where(BatchBaseline.batch_id.in_(ids))).all()}
    stats = select(
        BatchCorrection.batch_id.label("batch_id"),
        func.max(BatchCorrection.revision).label("head_revision"),
        func.count().label("correction_count"),
    ).where(BatchCorrection.batch_id.in_(ids)).group_by(
        BatchCorrection.batch_id).subquery()
    packed = {}
    for head, count in db.execute(select(
        BatchCorrection, stats.c.correction_count
    ).join(stats, and_(
        stats.c.batch_id == BatchCorrection.batch_id,
        stats.c.head_revision == BatchCorrection.revision,
    ))).all():
        packed[head.batch_id] = (head, int(count))
    result = {}
    for batch in batches:
        baseline = baselines.get(batch.id)
        head, count = packed.get(batch.id, (None, 0))
        if baseline is None:
            result[batch.id] = EffectiveBatch(
                batch.id, batch.release_id, batch.snapshot_id, batch.changeover_id,
                batch.started_at, batch.ended_at, batch.note, "NOT_RECORDED", 0)
            continue
        result[batch.id] = EffectiveBatch(
            batch.id, baseline.release_id, baseline.snapshot_id,
            head.changeover_id if head is not None else baseline.changeover_id,
            _utc(head.started_at) if head is not None else _utc(baseline.recorded_started_at),
            _utc(head.ended_at) if head is not None else _utc(baseline.recorded_ended_at),
            head.note if head is not None else baseline.recorded_note,
            _batch_state(baseline, head), count)
    return result
