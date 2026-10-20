"""Effective-value projection for Deployment actual software history.

The physical ``deployments.actual_*`` columns are a frozen recorded baseline.
The *effective* current value is the head of the correction chain if any,
otherwise the baseline. Consumers must resolve through these helpers rather
than reading the physical columns directly, so that a correction is reflected
consistently everywhere without ever mutating the baseline.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.production import Deployment
from app.models.production_history import (
    DeploymentActualBaseline,
    DeploymentActualCorrection,
)


@dataclass(frozen=True)
class EffectiveActual:
    """The current effective actual value for a Deployment plus provenance."""

    deployment_id: uuid.UUID
    actual_release_id: uuid.UUID | None
    actual_snapshot_id: uuid.UUID | None
    status: str
    # Public version = baseline.recorded_actual_version + head revision.
    actual_version: int
    deployed_at: object
    history_state: str
    correction_count: int


def _history_state(baseline, head):
    if baseline is None:
        return "NOT_RECORDED"
    if baseline.source in ("LEGACY_CURRENT", "IMPORTED_CURRENT"):
        prefix = "LEGACY" if baseline.source == "LEGACY_CURRENT" else "IMPORTED"
    else:
        prefix = "FIRST_REPORT"
    if head is not None:
        return f"{prefix}_CORRECTED"
    return prefix


def effective_actual(db: Session, deployment: Deployment) -> EffectiveActual:
    """Resolve the effective actual value for a single Deployment.

    Returns the baseline-derived value when no correction exists, otherwise the
    head of the correction chain. A missing baseline with non-null physical
    columns is tolerated for read robustness but reported as UNRESOLVED so a
    consumer never mistakes it for a verified first report.
    """
    baseline = db.scalar(
        select(DeploymentActualBaseline)
        .where(DeploymentActualBaseline.deployment_id == deployment.id)
    )
    head = db.scalar(
        select(DeploymentActualCorrection)
        .where(DeploymentActualCorrection.deployment_id == deployment.id)
        .order_by(DeploymentActualCorrection.revision.desc())
        .limit(1)
    )
    correction_count = (
        db.query(DeploymentActualCorrection)
        .filter(DeploymentActualCorrection.deployment_id == deployment.id)
        .count()
    )

    if baseline is None:
        # Physical columns may carry a legacy value without a baseline (should
        # not happen post-migration); report unresolved rather than fabricate.
        return EffectiveActual(
            deployment_id=deployment.id,
            actual_release_id=deployment.actual_release_id,
            actual_snapshot_id=deployment.actual_snapshot_id,
            status=deployment.status,
            actual_version=deployment.actual_version,
            deployed_at=deployment.deployed_at,
            history_state="UNRESOLVED" if (
                deployment.actual_release_id is not None
                or deployment.actual_snapshot_id is not None
            ) else "NOT_RECORDED",
            correction_count=0,
        )

    release_id = head.actual_release_id if head is not None else baseline.actual_release_id
    snapshot_id = head.actual_snapshot_id if head is not None else baseline.actual_snapshot_id
    status = _derive_status(deployment, release_id, snapshot_id)
    base_version = baseline.recorded_actual_version
    revision = head.revision if head is not None else 0
    deployed_at = head.recorded_at if head is not None else baseline.recorded_deployed_at
    return EffectiveActual(
        deployment_id=deployment.id,
        actual_release_id=release_id,
        actual_snapshot_id=snapshot_id,
        status=status,
        actual_version=base_version + revision,
        deployed_at=deployed_at,
        history_state=_history_state(baseline, head),
        correction_count=correction_count,
    )


def _derive_status(deployment: Deployment, release_id, snapshot_id) -> str:
    if release_id is None and snapshot_id is None:
        return "PENDING"
    if release_id is None or snapshot_id is None:
        return "MISMATCH"
    if (release_id, snapshot_id) == (
        deployment.expected_release_id,
        deployment.expected_snapshot_id,
    ):
        return "MATCH"
    return "MISMATCH"


def effective_actual_map(db: Session, deployments) -> dict:
    """Batch-resolve effective actual values for a list of Deployments.

    Uses a single set of bounded queries so catalogs do not issue per-row
    subqueries. Returns a mapping keyed by deployment id.
    """
    if not deployments:
        return {}
    ids = [d.id for d in deployments]
    baselines = {
        b.deployment_id: b
        for b in db.scalars(
            select(DeploymentActualBaseline)
            .where(DeploymentActualBaseline.deployment_id.in_(ids))
        ).all()
    }
    corrections = db.scalars(
        select(DeploymentActualCorrection)
        .where(DeploymentActualCorrection.deployment_id.in_(ids))
        .order_by(DeploymentActualCorrection.revision)
    ).all()
    head_by_deployment = {}
    counts = {}
    for c in corrections:
        head_by_deployment[c.deployment_id] = c
        counts[c.deployment_id] = counts.get(c.deployment_id, 0) + 1
    result = {}
    for d in deployments:
        baseline = baselines.get(d.id)
        head = head_by_deployment.get(d.id)
        if baseline is None:
            result[d.id] = EffectiveActual(
                deployment_id=d.id,
                actual_release_id=d.actual_release_id,
                actual_snapshot_id=d.actual_snapshot_id,
                status=d.status,
                actual_version=d.actual_version,
                deployed_at=d.deployed_at,
                history_state="UNRESOLVED" if (
                    d.actual_release_id is not None or d.actual_snapshot_id is not None
                ) else "NOT_RECORDED",
                correction_count=0,
            )
            continue
        release_id = head.actual_release_id if head is not None else baseline.actual_release_id
        snapshot_id = head.actual_snapshot_id if head is not None else baseline.actual_snapshot_id
        base_version = baseline.recorded_actual_version
        revision = head.revision if head is not None else 0
        result[d.id] = EffectiveActual(
            deployment_id=d.id,
            actual_release_id=release_id,
            actual_snapshot_id=snapshot_id,
            status=_derive_status(d, release_id, snapshot_id),
            actual_version=base_version + revision,
            deployed_at=head.recorded_at if head is not None else baseline.recorded_deployed_at,
            history_state=_history_state(baseline, head),
            correction_count=counts.get(d.id, 0),
        )
    return result
