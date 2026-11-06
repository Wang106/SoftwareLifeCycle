"""Bounded release directories and exact legacy ASR resolution; read-only."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select
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


def catalog_statement(kind: Literal['application', 'standard'], filters: Filters):
    """Shared filtering/join semantics for the directory and its child batch."""
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
    return stmt


def catalog_page(stmt, filters):
    return stmt.order_by(Release.created_at.desc().nulls_last(), Release.id.desc()).limit(
        filters.limit).offset(filters.offset)


APPLICATION_BATCH_MAX_BYTES = 2 * 1024 * 1024
APPLICATION_PAGE_SIZE = 10


class ApplicationBatchFilters(Filters):
    applications_for: uuid.UUID | None = None
    application_offset: int = Field(0, ge=0, le=100000)


@router.get('/standard/applications')
def standard_applications_batch(filters: Annotated[ApplicationBatchFilters, Query()],
                                db: Session = Depends(get_db)):
    # Recompute the bounded parent page instead of accepting an arbitrary ID list.
    parents = db.scalars(catalog_page(catalog_statement('standard', filters).with_only_columns(
        Release.id), filters)).all()
    pages = []
    if parents:
        r, d = Release, ApplicationReleaseDetail
        association = select(d.standard_base_release_id.label('parent_id'), r.id,
            r.version, r.status, r.created_at).join(d, d.release_id == r.id).where(
            d.standard_base_release_id.in_(parents))
        # Preserve the legacy stored association, including its missing-Release
        # exclusion and absence of inferred child type/software/status filters.
        counts = dict(db.execute(select(d.standard_base_release_id, func.count()).select_from(r).join(
            d, d.release_id == r.id).where(d.standard_base_release_id.in_(parents)).group_by(
            d.standard_base_release_id)).all())
        ranked = association.add_columns(func.row_number().over(
            partition_by=d.standard_base_release_id,
            order_by=(r.created_at.desc().nulls_last(), r.id.desc())).label('position')).subquery()
        selected_offset = case((ranked.c.parent_id == filters.applications_for,
                               filters.application_offset), else_=0)
        rows = db.execute(select(ranked.c.parent_id, ranked.c.id, ranked.c.version, ranked.c.status).where(
            ranked.c.position > selected_offset,
            ranked.c.position <= selected_offset + APPLICATION_PAGE_SIZE).order_by(
            ranked.c.parent_id, ranked.c.position)).mappings()
        children = {parent: [] for parent in parents}
        for row in rows:
            children[row['parent_id']].append({'id': str(row['id']),
                'version': row['version'], 'status': row['status']})
        for parent in parents:
            offset = filters.application_offset if parent == filters.applications_for else 0
            count = counts.get(parent, 0)
            pages.append({'release_id': str(parent), 'total': count,
                'limit': APPLICATION_PAGE_SIZE, 'offset': offset,
                'next_offset': offset + APPLICATION_PAGE_SIZE if offset + APPLICATION_PAGE_SIZE < count else None,
                'items': children[parent]})
    # Measure the actual UTF-8 bytes sent, not Python character count. A too-large
    # response fails explicitly; it must never masquerade as a truncated page.
    response = JSONResponse({'limit': filters.limit, 'offset': filters.offset, 'items': pages},
                            headers={'Cache-Control': 'no-store'})
    if len(response.body) > APPLICATION_BATCH_MAX_BYTES:
        raise HTTPException(503, 'application_batch_response_too_large', headers={'Cache-Control': 'no-store'})
    return response


@router.get('/{kind}')
def release_catalog(kind: Literal['application', 'standard'], filters: Annotated[Filters, Query()],
                    db: Session = Depends(get_db)):
    stmt = catalog_statement(kind, filters)
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(catalog_page(stmt, filters)).mappings()
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
