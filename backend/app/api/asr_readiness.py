"""Current readiness summary and exact Snapshot approved-exception pages."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.api.dashboard import _readiness_for_release
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.governance import PolicyException

router = APIRouter(prefix='/api/v1/releases/application/id', tags=['application readiness'])

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: uuid.UUID | Literal['none'] | None = None

class ExceptionPage(Selection):
    snapshot_id: uuid.UUID | Literal['none']
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def release(db, release_id):
    row = db.get(Release, release_id)
    if row is None or row.release_type != 'APPLICATION':
        raise HTTPException(404, 'application release not found')
    return row

@router.get('/{release_id}/readiness/summary')
def summary(release_id: uuid.UUID, filters: Annotated[Selection, Query()], db: Session = Depends(get_db)):
    row = release(db, release_id)
    if isinstance(filters.snapshot_id, uuid.UUID):
        pinned = db.get(ReleaseSnapshot, filters.snapshot_id)
        if pinned is None or pinned.release_id != release_id:
            raise HTTPException(404, 'snapshot not found for application release')
    result = _readiness_for_release(row, db, bounded=True)
    snapshot_id = result['coverage']['snapshot_id']
    selected = snapshot_id or 'none'
    if filters.snapshot_id is not None and str(filters.snapshot_id) != selected:
        raise HTTPException(409, 'readiness snapshot changed; read latest summary')
    snapshot = db.get(ReleaseSnapshot, uuid.UUID(snapshot_id)) if snapshot_id else None
    return {'release_id': str(release_id), 'snapshot_id': selected,
        'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no,
            'status': snapshot.status, 'content_hash': snapshot.content_hash} if snapshot else None, **result}

@router.get('/{release_id}/readiness/exceptions')
def exceptions(release_id: uuid.UUID, filters: Annotated[ExceptionPage, Query()], db: Session = Depends(get_db)):
    release(db, release_id)
    snapshot = None
    if filters.snapshot_id != 'none':
        snapshot = db.get(ReleaseSnapshot, filters.snapshot_id)
        if snapshot is None or snapshot.release_id != release_id:
            raise HTTPException(404, 'snapshot not found for application release')
    total, items = 0, []
    if snapshot:
        p = PolicyException
        scope = [p.snapshot_id == snapshot.id, p.status == 'APPROVED']
        total = db.scalar(select(func.count()).select_from(p).where(*scope))
        stmt = select(p.id, p.exception_no, p.status, p.scope, p.reason,
            p.compensating_control, p.rule_code).where(*scope)
        for row in db.execute(stmt.order_by(p.exception_no, p.id).limit(filters.limit).offset(filters.offset)).mappings():
            items.append(dict(row, id=str(row['id']), snapshot_no=snapshot.snapshot_no))
    return {'release_id': str(release_id), 'snapshot_id': str(filters.snapshot_id),
        'total': total, 'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None, 'items': items}
