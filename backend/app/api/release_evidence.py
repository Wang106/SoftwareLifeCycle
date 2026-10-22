"""Bounded read-only evidence summary for one standard or application release.

This read pins the current frozen Snapshot, Readiness gates, bound Approval and
effective Release Decision into one projection. It performs no state transitions
and never infers a formal release from record status or stage counts.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import Release
from app.services.release_evidence import release_evidence_summary

router = APIRouter(prefix="/api/v1/releases", tags=["release evidence summary"])


@router.get("/{release_id}/evidence-summary")
def evidence_summary(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type not in ("STANDARD", "APPLICATION"):
        raise HTTPException(404, "standard or application release not found")
    return release_evidence_summary(db, release)
