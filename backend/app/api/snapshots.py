"""Exact frozen snapshot lookup, including historical manifests and policies."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.snapshot_comparison import SnapshotComparisonError, compare_manifests

router = APIRouter(prefix="/api/v1/snapshots", tags=["snapshots"])


@router.get("/{snapshot_no}")
def snapshot_detail(snapshot_no: str, db: Session = Depends(get_db)):
    snapshot = db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.snapshot_no == snapshot_no)).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    release = db.get(Release, snapshot.release_id)
    current = db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.release_id == snapshot.release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    return {
        "id": str(snapshot.id), "snapshot_no": snapshot.snapshot_no,
        "snapshot_number": snapshot.snapshot_number, "status": snapshot.status,
        "content_hash": snapshot.content_hash, "created_at": snapshot.created_at,
        "is_current_snapshot": bool(current and current.id == snapshot.id),
        "release": {"id": str(release.id), "type": release.release_type,
                    "version": release.version} if release else None,
        "artifacts": _manifest(db, snapshot.id),
    }


def _manifest(db: Session, snapshot_id):
    artifacts = db.scalars(select(SnapshotArtifact).where(
        SnapshotArtifact.snapshot_id == snapshot_id)
        .order_by(SnapshotArtifact.component_code, SnapshotArtifact.filename, SnapshotArtifact.id)).all()
    ids = [row.id for row in artifacts]
    rules = db.scalars(select(SnapshotArtifactDistributionRule).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id.in_(ids))
        .order_by(SnapshotArtifactDistributionRule.recipient_type,
                  SnapshotArtifactDistributionRule.purpose,
                  SnapshotArtifactDistributionRule.id)).all() if ids else []
    grouped = {}
    for rule in rules:
        grouped.setdefault(rule.snapshot_artifact_id, []).append(rule)
    return [{
            "id": str(row.id), "filename": row.filename, "artifact_type": row.artifact_type,
            "component_code": row.component_code, "component_version": row.component_version,
            "sha256": row.sha256, "classification": row.classification,
            "distribution_level": row.distribution_level, "ai_access_policy": row.ai_access_policy,
            "policy_rules": [{"recipient_type": rule.recipient_type, "purpose": rule.purpose,
                              "recipient_code": rule.recipient_code, "decision": rule.decision}
                             for rule in grouped.get(row.id, [])],
        } for row in artifacts]


@router.get("/{snapshot_no}/compare/{target_no}")
def compare_snapshots(snapshot_no: str, target_no: str, db: Session = Depends(get_db)):
    source = db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.snapshot_no == snapshot_no)).first()
    target = source if target_no == snapshot_no else db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.snapshot_no == target_no)).first()
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    if source.release_id != target.release_id:
        raise HTTPException(status_code=409, detail="snapshots must belong to the same release")
    before = _manifest(db, source.id)
    after = before if source.id == target.id else _manifest(db, target.id)
    try:
        result = compare_manifests(before, after)
    except SnapshotComparisonError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    metadata_fields = ('version', 'release_type')
    old_metadata, new_metadata = source.release_metadata_json or {}, target.release_metadata_json or {}
    def identity(snapshot):
        return {"snapshot_no": snapshot.snapshot_no, "snapshot_number": snapshot.snapshot_number,
                "content_hash": snapshot.content_hash, "created_at": snapshot.created_at,
                "status": snapshot.status}
    return {"release_id": str(source.release_id), "source": identity(source), "target": identity(target),
            "content_hash_matches": source.content_hash == target.content_hash,
            "metadata_changes": [{"field": field, "before": old_metadata.get(field),
                                  "after": new_metadata.get(field)} for field in metadata_fields
                                 if old_metadata.get(field) != new_metadata.get(field)], **result}
