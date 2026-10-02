"""Exact frozen Snapshot summary and bounded public metadata; no latest fallback."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.asr_policy import RulePage
from app.api.asr_evidence import envelope
from app.core.db import get_db
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.frozen_policy_reads import artifacts, rules, count

router = APIRouter(prefix='/api/v1/snapshots', tags=['exact snapshot pages'])

class SummarySelection(BaseModel):
    model_config = ConfigDict(extra='forbid')


def exact_snapshot(db, snapshot_no, snapshot_id=None, artifact_id=None):
    snapshot = db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.snapshot_no == snapshot_no))
    if snapshot is None or (snapshot_id is not None and snapshot.id != snapshot_id):
        raise HTTPException(404, 'snapshot not found')
    if artifact_id is not None and db.scalar(select(SnapshotArtifact.id).where(
        SnapshotArtifact.id == artifact_id, SnapshotArtifact.snapshot_id == snapshot.id)) is None:
        raise HTTPException(404, 'artifact not found for snapshot')
    return snapshot


@router.get('/{snapshot_no}/summary')
def snapshot_summary(snapshot_no: str, filters: Annotated[SummarySelection, Query()], db: Session = Depends(get_db)):
    snapshot = exact_snapshot(db, snapshot_no)
    release = db.get(Release, snapshot.release_id)
    current_id = db.scalar(select(ReleaseSnapshot.id).where(ReleaseSnapshot.release_id == snapshot.release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1))
    return {'id': str(snapshot.id), 'release_id': str(snapshot.release_id), 'snapshot_no': snapshot.snapshot_no,
        'snapshot_number': snapshot.snapshot_number, 'status': snapshot.status,
        'content_hash': snapshot.content_hash, 'created_at': snapshot.created_at,
        'is_current_snapshot': snapshot.id == current_id,
        'release': {'id': str(release.id), 'type': release.release_type, 'version': release.version} if release else None,
        'artifact_count': count(db, artifacts(snapshot.id)), 'rule_count': count(db, rules(snapshot.id))}


@router.get('/{snapshot_no}/artifacts')
def snapshot_artifacts(snapshot_no: str, filters: Annotated[RulePage, Query()], db: Session = Depends(get_db)):
    snapshot = exact_snapshot(db, snapshot_no, filters.snapshot_id, filters.snapshot_artifact_id)
    a = SnapshotArtifact
    stmt = artifacts(snapshot.id)
    if filters.snapshot_artifact_id is not None:
        stmt = stmt.where(a.id == filters.snapshot_artifact_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(a.component_code, a.filename, a.id)
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(snapshot.release_id, filters, total, [dict(row, id=str(row['id'])) for row in rows]) | {
        'snapshot_no': snapshot.snapshot_no,
        'snapshot_artifact_id': str(filters.snapshot_artifact_id) if filters.snapshot_artifact_id else None}


@router.get('/{snapshot_no}/rules')
def snapshot_rules(snapshot_no: str, filters: Annotated[RulePage, Query()], db: Session = Depends(get_db)):
    snapshot = exact_snapshot(db, snapshot_no, filters.snapshot_id, filters.snapshot_artifact_id)
    a, rule = SnapshotArtifact, SnapshotArtifactDistributionRule
    stmt = rules(snapshot.id, filters.snapshot_artifact_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(a.component_code, a.filename, a.id,
        rule.recipient_type, rule.purpose, func.coalesce(rule.recipient_code, ''), rule.decision, rule.id)
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(snapshot.release_id, filters, total, [dict(row, id=str(row['id']),
        snapshot_artifact_id=str(row['snapshot_artifact_id'])) for row in rows]) | {
        'snapshot_no': snapshot.snapshot_no,
        'snapshot_artifact_id': str(filters.snapshot_artifact_id) if filters.snapshot_artifact_id else None}
