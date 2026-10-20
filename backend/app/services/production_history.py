"""Effective-value projection for immutable Deployment actual history."""
import uuid
from dataclasses import dataclass
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from app.models.audit import AuditEvent
from app.models.production import Deployment
from app.models.production_history import DeploymentActualBaseline, DeploymentActualCorrection

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
        proof_time if head is not None else baseline.recorded_deployed_at,
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
            proof_time if head is not None else baseline.recorded_deployed_at,
            _history_state(baseline, head, proof_time), count)
    return result
