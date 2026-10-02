"""Bounded frozen policy observations pinned to an exact application Snapshot."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.asr_evidence import EvidencePage, EvidenceSelection, envelope, select_snapshot
from app.core.db import get_db
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule

router = APIRouter(prefix='/api/v1/releases/application/id', tags=['application frozen policy'])


class RulePage(EvidencePage):
    snapshot_artifact_id: uuid.UUID | None = None


def rule_exists():
    return select(SnapshotArtifactDistributionRule.id).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id == SnapshotArtifact.id).exists()


def artifacts(snapshot_id):
    a = SnapshotArtifact
    rule_count = select(func.count()).select_from(SnapshotArtifactDistributionRule).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id == a.id).scalar_subquery()
    return select(a.id, a.component_code, a.component_version, a.filename, a.artifact_type,
        a.sha256, a.classification, a.distribution_level, a.ai_access_policy,
        rule_count.label('rule_count')).where(a.snapshot_id == snapshot_id)


def rules(snapshot_id, artifact_id=None):
    a, r = SnapshotArtifact, SnapshotArtifactDistributionRule
    stmt = select(r.id, r.snapshot_artifact_id, a.filename, a.component_code,
        a.distribution_level, r.recipient_type, r.purpose, r.recipient_code, r.decision)\
        .select_from(r).join(a, a.id == r.snapshot_artifact_id).where(a.snapshot_id == snapshot_id)
    return stmt.where(a.id == artifact_id) if artifact_id is not None else stmt


def count(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


@router.get('/{release_id}/snapshot-policy/summary')
def policy_summary(release_id: uuid.UUID, filters: Annotated[EvidenceSelection, Query()], db: Session = Depends(get_db)):
    snapshot = select_snapshot(db, release_id, filters.snapshot_id)
    if snapshot is None:
        return {'release_id': str(release_id), 'snapshot': None, 'artifact_count': 0,
                'sha_recorded_count': 0, 'policy_recorded_count': 0, 'rule_count': 0}
    a = SnapshotArtifact
    # Match the old page: non-empty SHA; INTERNAL_ONLY or any stored rule. These
    # are recording indicators, not hash verification or policy authorization.
    counts = db.execute(select(func.count().label('total'),
        func.coalesce(func.sum(case((a.sha256 != '', 1), else_=0)), 0).label('sha'),
        func.coalesce(func.sum(case((or_(a.distribution_level == 'INTERNAL_ONLY', rule_exists()), 1), else_=0)), 0).label('policy'))
        .where(a.snapshot_id == snapshot.id)).one()
    latest_id = db.scalar(select(ReleaseSnapshot.id).where(ReleaseSnapshot.release_id == release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1))
    return {'release_id': str(release_id), 'snapshot': {'id': str(snapshot.id),
        'snapshot_no': snapshot.snapshot_no, 'status': snapshot.status,
        'content_hash': snapshot.content_hash, 'is_current_snapshot': snapshot.id == latest_id},
        'artifact_count': counts.total, 'sha_recorded_count': counts.sha,
        'policy_recorded_count': counts.policy, 'rule_count': count(db, rules(snapshot.id))}


@router.get('/{release_id}/snapshot-policy/artifacts')
def policy_artifacts(release_id: uuid.UUID, filters: Annotated[EvidencePage, Query()], db: Session = Depends(get_db)):
    select_snapshot(db, release_id, filters.snapshot_id)
    a = SnapshotArtifact
    stmt = artifacts(filters.snapshot_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(a.component_code, a.filename, a.id)
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, filters, total, [dict(row, id=str(row['id'])) for row in rows])


@router.get('/{release_id}/snapshot-policy/rules')
def policy_rules(release_id: uuid.UUID, filters: Annotated[RulePage, Query()], db: Session = Depends(get_db)):
    select_snapshot(db, release_id, filters.snapshot_id)
    if filters.snapshot_artifact_id is not None:
        artifact = db.scalar(select(SnapshotArtifact.id).where(
            SnapshotArtifact.id == filters.snapshot_artifact_id, SnapshotArtifact.snapshot_id == filters.snapshot_id))
        if artifact is None:
            raise HTTPException(404, 'artifact not found for snapshot')
    a, r = SnapshotArtifact, SnapshotArtifactDistributionRule
    stmt = rules(filters.snapshot_id, filters.snapshot_artifact_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(a.component_code, a.filename, a.id,
        r.recipient_type, r.purpose, func.coalesce(r.recipient_code, ''), r.decision, r.id)
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, filters, total, [dict(row, id=str(row['id']),
        snapshot_artifact_id=str(row['snapshot_artifact_id'])) for row in rows]) | {
            'snapshot_artifact_id': str(filters.snapshot_artifact_id) if filters.snapshot_artifact_id else None}
