from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import SoftwareChangeRequest
from app.models.testing import DvpItem, DvpExecution
from app.models.core import Release
from app.services.traceability import TraceabilityService

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/changes")
def list_changes(db: Session = Depends(get_db)):
    rows = db.scalars(select(SoftwareChangeRequest)).all()
    return [
        {
            "id": str(row.id),
            "request_no": row.request_no,
            "title": row.title,
            "source": row.source,
            "scope": row.scope,
            "change_type": row.change_type,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/testing/dvp")
def list_dvp(db: Session = Depends(get_db)):
    items = db.scalars(select(DvpItem)).all()
    executions = db.scalars(select(DvpExecution)).all()
    latest = {}
    for execution in executions:
        key = str(execution.dvp_item_id)
        prev = latest.get(key)
        if prev is None or execution.execution_no > prev.execution_no:
            latest[key] = execution

    return [
        {
            "id": str(item.id),
            "item_no": item.item_no,
            "title": item.title,
            "scope": item.scope,
            "status": item.status,
            "latest_result": getattr(latest.get(str(item.id)), "result", None),
            "latest_execution_no": getattr(latest.get(str(item.id)), "execution_no", None),
            "snapshot_id": str(getattr(latest.get(str(item.id)), "snapshot_id", "")) or None,
        }
        for item in items
    ]


@router.get("/releases/{release_id}/coverage")
def release_coverage(release_id: str, db: Session = Depends(get_db)):
    release = db.scalars(select(Release).where(Release.id == release_id)).first()
    if not release:
        raise HTTPException(status_code=404, detail="release not found")
    return TraceabilityService(db).release_coverage(release.id).as_dict()
