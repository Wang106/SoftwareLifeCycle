import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.services.snapshot import SnapshotError, SnapshotService
from app.authorization import authorize_release
from app.actor import resolve_actor

router = APIRouter(prefix="/releases", tags=["releases"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def list_releases(db: Session = Depends(get_db)):
    rows = db.scalars(select(Release).order_by(Release.created_at.desc())).all()
    return [{"id": str(x.id), "type": x.release_type, "version": x.version, "status": x.status} for x in rows]


@router.get("/{release_id}/snapshots")
def list_snapshots(release_id: uuid.UUID, limit: int = Query(20, ge=1, le=100),
                   before_number: int | None = Query(None, ge=1),
                   db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="release not found")
    total, latest_number = db.execute(select(func.count(ReleaseSnapshot.id),
        func.max(ReleaseSnapshot.snapshot_number)).where(
        ReleaseSnapshot.release_id == release_id)).one()
    statement = select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release_id)
    if before_number is not None:
        statement = statement.where(ReleaseSnapshot.snapshot_number < before_number)
    rows = db.scalars(statement.order_by(ReleaseSnapshot.snapshot_number.desc())
        .limit(limit + 1)).all()
    page = rows[:limit]
    return {
        "release": {"id": str(release.id), "type": release.release_type, "version": release.version},
        "total": total,
        "next_before_number": page[-1].snapshot_number if len(rows) > limit else None,
        "items": [{"id": str(row.id), "snapshot_no": row.snapshot_no,
                   "snapshot_number": row.snapshot_number, "status": row.status,
                   "created_at": row.created_at, "content_hash": row.content_hash,
                   "is_current_snapshot": row.snapshot_number == latest_number} for row in page],
    }

class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID | None = None


@router.post("/{release_id}/create-snapshot", status_code=201)
def create_snapshot(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    request: Request = None,
    payload: Annotated[SnapshotCreate | None, Body()] = None,
):
    authorize_release(
        request,
        db,
        release_id,
        project_roles=frozenset({"CONTRIBUTOR"}),
        software_roles=frozenset({"SOFTWARE_MAINTAINER"}),
    )
    actor = resolve_actor(request)
    try:
        s = SnapshotService().create(db, release_id, actor_context=actor,
            request_id=payload.request_id if payload else None)
        return {"id": str(s.id), "snapshot_no": s.snapshot_no, "content_hash": s.content_hash, "status": s.status}
    except SnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
