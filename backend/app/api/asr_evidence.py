"""Bounded evidence selected by exact application release and frozen snapshot."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpExecution, DvpItem

router = APIRouter(prefix='/api/v1/releases/application/id', tags=['application evidence'])


class EvidenceSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: uuid.UUID | None = None


class EvidencePage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: uuid.UUID
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def select_snapshot(db, release_id, snapshot_id=None):
    release = db.get(Release, release_id)
    if release is None or release.release_type != 'APPLICATION':
        raise HTTPException(404, 'application release not found')
    if snapshot_id is not None:
        snapshot = db.get(ReleaseSnapshot, snapshot_id)
        if snapshot is None or snapshot.release_id != release_id:
            raise HTTPException(404, 'snapshot not found for application release')
        return snapshot
    return db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()


def latest_executions(release_id, snapshot_id):
    e = DvpExecution
    ranked = select(e.id, func.row_number().over(partition_by=e.dvp_item_id,
        order_by=(e.execution_no.desc(), e.executed_at.desc(), e.id.desc())).label('position'))\
        .where(e.release_id == release_id, e.snapshot_id == snapshot_id).subquery()
    return select(ranked.c.id).where(ranked.c.position == 1)


@router.get('/{release_id}/evidence-summary')
def evidence_summary(release_id: uuid.UUID, filters: Annotated[EvidenceSelection, Query()], db: Session = Depends(get_db)):
    snapshot = select_snapshot(db, release_id, filters.snapshot_id)
    if snapshot is None:
        return {'release_id': str(release_id), 'snapshot': None, 'artifact_count': 0,
                'latest_execution_count': 0, 'other_snapshot_executions': 0}
    latest_id = db.scalar(select(ReleaseSnapshot.id).where(ReleaseSnapshot.release_id == release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1))
    return {'release_id': str(release_id), 'snapshot': {'id': str(snapshot.id),
        'snapshot_no': snapshot.snapshot_no, 'is_current_snapshot': snapshot.id == latest_id},
        'artifact_count': db.scalar(select(func.count()).select_from(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot.id)),
        'latest_execution_count': db.scalar(select(func.count()).select_from(latest_executions(release_id, snapshot.id).subquery())),
        'other_snapshot_executions': db.scalar(select(func.count()).select_from(DvpExecution).where(
            DvpExecution.release_id == release_id, or_(DvpExecution.snapshot_id != snapshot.id, DvpExecution.snapshot_id.is_(None))))}


def envelope(release_id, filters, total, items):
    return {'release_id': str(release_id), 'snapshot_id': str(filters.snapshot_id),
        'total': total, 'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': items}


@router.get('/{release_id}/evidence/artifacts')
def evidence_artifacts(release_id: uuid.UUID, filters: Annotated[EvidencePage, Query()], db: Session = Depends(get_db)):
    select_snapshot(db, release_id, filters.snapshot_id)
    a = SnapshotArtifact
    stmt = select(a.id, a.component_code, a.component_version, a.filename, a.artifact_type,
        a.sha256, a.classification, a.distribution_level, a.ai_access_policy).where(a.snapshot_id == filters.snapshot_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(a.component_code, a.filename, a.id).limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, filters, total, [dict(row, id=str(row['id'])) for row in rows])


@router.get('/{release_id}/evidence/executions')
def evidence_executions(release_id: uuid.UUID, filters: Annotated[EvidencePage, Query()], db: Session = Depends(get_db)):
    select_snapshot(db, release_id, filters.snapshot_id)
    e, i = DvpExecution, DvpItem
    ids = latest_executions(release_id, filters.snapshot_id)
    total = db.scalar(select(func.count()).select_from(ids.subquery()))
    stmt = select(e.id, e.dvp_item_id, i.item_no, i.title, e.execution_no, e.result, e.executed_at)\
        .outerjoin(i, i.id == e.dvp_item_id).where(e.id.in_(ids))\
        .order_by(i.item_no.asc().nulls_last(), e.dvp_item_id, e.id).limit(filters.limit).offset(filters.offset)
    rows = db.execute(stmt).mappings()
    return envelope(release_id, filters, total, [dict(row, id=str(row['id']), dvp_item_id=str(row['dvp_item_id']),
        item_metadata_available=row['item_no'] is not None) for row in rows])
