"""Fixed SSR parent summary and bounded stored-child projections.

Keep the compatibility profile in dashboard.py unchanged. These reads observe
stored associations; they do not imply approval, frozen evidence or permission.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import (
    ApplicationReleaseDetail, ComponentDefinition, Release, ReleaseComponent,
    SoftwareProduct, StandardReleaseDetail, Supplier,
)

router = APIRouter(prefix='/api/v1/releases/standard/id', tags=['standard release views'])


class SummarySelection(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CollectionPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def standard_release(db: Session, release_id: uuid.UUID) -> Release:
    release = db.get(Release, release_id)
    if release is None or release.release_type != 'STANDARD':
        raise HTTPException(404, 'standard release not found')
    return release


def applications(release_id):
    # As in the old profile, missing referenced Release rows are excluded. Do not
    # infer associations from version strings or add software/status filters.
    return select(Release.id, Release.version, Release.status, Release.created_at).join(
        ApplicationReleaseDetail, ApplicationReleaseDetail.release_id == Release.id
    ).where(ApplicationReleaseDetail.standard_base_release_id == release_id)


def total(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


def envelope(release_id, filters, count, items):
    return {'release_id': str(release_id), 'total': count, 'limit': filters.limit,
            'offset': filters.offset,
            'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < count else None,
            'items': items}


@router.get('/{release_id}/summary')
def standard_summary(release_id: uuid.UUID, filters: Annotated[SummarySelection, Query()], db: Session = Depends(get_db)):
    release = standard_release(db, release_id)
    detail = db.get(StandardReleaseDetail, release_id)
    product = db.get(SoftwareProduct, release.software_id)
    supplier = db.get(Supplier, product.supplier_id) if product else None
    previous = db.get(Release, detail.previous_release_id) if detail and detail.previous_release_id else None
    return {'id': str(release.id), 'version': release.version, 'status': release.status,
            'release_notes': release.release_notes,
            'software': {'code': product.code, 'name': product.name} if product else None,
            'supplier': {'code': supplier.code, 'name': supplier.name} if supplier else None,
            'previous_release': {'id': str(previous.id), 'version': previous.version}
            if previous and previous.release_type == 'STANDARD' else None,
            'source': {'branch': detail.git_branch, 'commit': detail.git_commit} if detail else None,
            'component_count': total(db, select(ReleaseComponent.id).where(ReleaseComponent.release_id == release_id)),
            'application_count': total(db, applications(release_id))}


@router.get('/{release_id}/components')
def standard_components(release_id: uuid.UUID, filters: Annotated[CollectionPage, Query()], db: Session = Depends(get_db)):
    standard_release(db, release_id)
    c, d = ReleaseComponent, ComponentDefinition
    stmt = select(c.id, d.code, d.name, c.version).outerjoin(
        d, d.id == c.component_definition_id
    ).where(c.release_id == release_id)
    count = total(db, stmt)
    rows = db.execute(stmt.order_by(c.id).limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, filters, count, [dict(row, id=str(row['id'])) for row in rows])


@router.get('/{release_id}/applications')
def standard_applications(release_id: uuid.UUID, filters: Annotated[CollectionPage, Query()], db: Session = Depends(get_db)):
    standard_release(db, release_id)
    stmt = applications(release_id)
    count = total(db, stmt)
    rows = db.execute(stmt.order_by(Release.created_at.desc().nulls_last(), Release.id.desc())
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, filters, count, [
        {'id': str(row['id']), 'version': row['version'], 'status': row['status']} for row in rows
    ])
