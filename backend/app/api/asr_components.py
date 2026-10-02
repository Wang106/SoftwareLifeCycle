"""Bounded ASR declarations and baselines without a valid stored ASR link."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, false, func, select
from sqlalchemy.orm import Session, aliased

from app.core.db import get_db
from app.models.core import ApplicationReleaseDetail, ComponentDefinition, Release, ReleaseComponent

router = APIRouter(prefix='/api/v1/releases/application/id', tags=['application components'])


class SummarySelection(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ComponentPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def context(db, release_id):
    release = db.get(Release, release_id)
    if release is None or release.release_type != 'APPLICATION':
        raise HTTPException(404, 'application release not found')
    detail = db.get(ApplicationReleaseDetail, release_id)
    base = db.get(Release, detail.standard_base_release_id) if detail else None
    return release, base


def declarations(release_id, base_id):
    c, d, b = ReleaseComponent, ComponentDefinition, aliased(ReleaseComponent)
    valid_link = and_(b.id == c.base_component_id, b.release_id == base_id,
                      b.component_definition_id == c.component_definition_id) if base_id else false()
    return select(c.id, d.code, d.name, c.version.label('asr_version'),
        c.delta_type.label('declared_delta_type'), b.version.label('base_component_version'),
        case((b.id.is_not(None), 'VALID'), (c.base_component_id.is_not(None), 'INVALID'),
             else_='NOT_RECORDED').label('base_link_status'))\
        .select_from(c).outerjoin(b, valid_link).outerjoin(d, d.id == c.component_definition_id)\
        .where(c.release_id == release_id)


def unlinked_bases(release_id, base_id):
    b, a, d = ReleaseComponent, aliased(ReleaseComponent), ComponentDefinition
    valid_asr_link = select(a.id).where(a.release_id == release_id,
        a.base_component_id == b.id, a.component_definition_id == b.component_definition_id).exists()
    # NOT EXISTS considers every declaration, not just the current page. Invalid
    # links never hide a base row; duplicate valid links hide it exactly once.
    return select(b.id, d.code, d.name, b.version).select_from(b).outerjoin(d, d.id == b.component_definition_id)\
        .where(b.release_id == base_id if base_id else false(), ~valid_asr_link)


def count(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


def envelope(release_id, base_id, filters, total, items):
    return {'release_id': str(release_id), 'base_release_id': str(base_id) if base_id else None,
        'total': total, 'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': items}


@router.get('/{release_id}/components/summary')
def component_summary(release_id: uuid.UUID, filters: Annotated[SummarySelection, Query()], db: Session = Depends(get_db)):
    release, base = context(db, release_id)
    base_id = base.id if base else None
    return {'release_id': str(release_id), 'version': release.version,
        'base_release': {'id': str(base.id), 'version': base.version} if base else None,
        'component_count': count(db, declarations(release_id, base_id)),
        'unlinked_base_count': count(db, unlinked_bases(release_id, base_id))}


@router.get('/{release_id}/components/declarations')
def component_declarations(release_id: uuid.UUID, filters: Annotated[ComponentPage, Query()], db: Session = Depends(get_db)):
    _, base = context(db, release_id)
    base_id = base.id if base else None
    stmt = declarations(release_id, base_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(ReleaseComponent.id).limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, base_id, filters, total, [dict(row, id=str(row['id'])) for row in rows])


@router.get('/{release_id}/components/unlinked-base')
def unlinked_base_components(release_id: uuid.UUID, filters: Annotated[ComponentPage, Query()], db: Session = Depends(get_db)):
    _, base = context(db, release_id)
    base_id = base.id if base else None
    stmt = unlinked_bases(release_id, base_id)
    total = count(db, stmt)
    rows = db.execute(stmt.order_by(ReleaseComponent.id).limit(filters.limit).offset(filters.offset)).mappings()
    return envelope(release_id, base_id, filters, total, [dict(row, id=str(row['id'])) for row in rows])
