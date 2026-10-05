"""Bounded release directories and exact legacy ASR resolution; read-only."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased
from app.core.db import get_db
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct, Supplier
from app.models.snapshot import ReleaseSnapshot

router = APIRouter(prefix='/api/v1/release-catalog', tags=['release catalogs'])


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str | None = Field(None, max_length=200)
    status: str | None = Field(None, max_length=30)
    software_id: uuid.UUID | None = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


class Resolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identifier: str = Field(min_length=1, max_length=100)


@router.get('/application/resolve')
def resolve_application(filters: Annotated[Resolution, Query()], db: Session = Depends(get_db)):
    # Preserve the old exact-string OR semantics: even a UUID may also be another
    # ASR's version. Never choose an arbitrary result, or load the directory.
    terms = [Release.version == filters.identifier]
    try:
        parsed = uuid.UUID(filters.identifier)
        if str(parsed) == filters.identifier:
            terms.append(Release.id == parsed)
    except ValueError:
        pass
    rows = db.execute(select(Release.id, Release.version).where(
        Release.release_type == 'APPLICATION', or_(*terms)).order_by(Release.id).limit(2)).all()
    return {'state': 'unique' if len(rows) == 1 else 'ambiguous' if rows else 'missing',
            'release': {'id': str(rows[0].id), 'version': rows[0].version} if len(rows) == 1 else None}


@router.get('/{kind}')
def release_catalog(kind: Literal['application', 'standard'], filters: Annotated[Filters, Query()],
                    db: Session = Depends(get_db)):
    r, p, s = Release, SoftwareProduct, Supplier
    stmt = select(r.id, r.version, r.status, r.created_at,
        p.code.label('software_code'), p.name.label('software_name'),
        s.code.label('supplier_code'), s.name.label('supplier_name')).outerjoin(
        p, p.id == r.software_id).outerjoin(s, s.id == p.supplier_id).where(
        r.release_type == ('APPLICATION' if kind == 'application' else 'STANDARD'))
    search = [r.version, p.code, p.name, s.code, s.name]
    if kind == 'application':
        d, c, project, base = ApplicationReleaseDetail, Customer, Project, aliased(Release)
        latest = select(ReleaseSnapshot.snapshot_no).where(ReleaseSnapshot.release_id == r.id).order_by(
            ReleaseSnapshot.snapshot_number.desc(), ReleaseSnapshot.id.desc()).limit(1).correlate(r).scalar_subquery()
        stmt = stmt.add_columns(c.name.label('customer'), project.name.label('project'),
            d.standard_base_release_id.label('base_id'), base.version.label('base_version'),
            latest.label('snapshot_no')).outerjoin(d, d.release_id == r.id).outerjoin(
            c, c.id == d.customer_id).outerjoin(project, project.id == d.project_id).outerjoin(
            base, base.id == d.standard_base_release_id)
        search += [c.name, project.name, base.version]
    if filters.status:
        stmt = stmt.where(r.status == filters.status)
    if filters.software_id:
        stmt = stmt.where(r.software_id == filters.software_id)
    if filters.q and filters.q.strip():
        stmt = stmt.where(or_(*[col.contains(filters.q.strip(), autoescape=True) for col in search]))
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(r.created_at.desc().nulls_last(), r.id.desc()).limit(
        filters.limit).offset(filters.offset)).mappings()
    items = []
    for row in rows:
        item = {'id': str(row['id']), 'version': row['version'], 'status': row['status']}
        if kind == 'standard':
            item.update(software={'code': row['software_code'], 'name': row['software_name']}
                if row['software_code'] is not None else None,
                supplier={'code': row['supplier_code'], 'name': row['supplier_name']}
                if row['supplier_code'] is not None else None)
        else:
            item.update(customer=row['customer'], project=row['project'],
                base_id=str(row['base_id']) if row['base_id'] else None,
                base_version=row['base_version'], snapshot_no=row['snapshot_no'])
        items.append(item)
    return {'kind': kind, 'total': count, 'limit': filters.limit, 'offset': filters.offset,
            'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < count else None,
            'items': items}
