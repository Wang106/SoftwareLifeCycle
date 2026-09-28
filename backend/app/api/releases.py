import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models.core import Release
from app.services.snapshot import SnapshotError, SnapshotService

router = APIRouter(prefix="/releases", tags=["releases"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.get("")
def list_releases(db: Session = Depends(get_db)):
    rows = db.scalars(select(Release).order_by(Release.created_at.desc())).all()
    return [{"id": str(x.id), "type": x.release_type, "version": x.version, "status": x.status} for x in rows]

@router.post("/{release_id}/create-snapshot", status_code=201)
def create_snapshot(release_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        s = SnapshotService().create(db, release_id)
        return {"id": str(s.id), "snapshot_no": s.snapshot_no, "content_hash": s.content_hash, "status": s.status}
    except SnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
