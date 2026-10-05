"""Scalar organization context and bounded directories/owned collections."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import ApplicationReleaseDetail as D, Customer, Project, Release, SoftwareProduct, Supplier
from app.models.production import ManufacturingSite

router = APIRouter(prefix='/api/v1/organization-views', tags=['organization views'])


class Page(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


class Filters(Page):
    q: str | None = Field(None, max_length=200)
    status: str | None = Field(None, max_length=30)


class SupplierFilters(Filters):
    country: str | None = Field(None, max_length=100)


class CustomerFilters(Filters):
    region: Literal['', 'APAC', 'EUROPE', 'AMERICAS', 'OTHER', 'UNASSIGNED'] | None = None


class ProjectFilters(Filters):
    customer_id: uuid.UUID | None = None


class OwnedPage(Page):
    organization_id: uuid.UUID


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


def count(stmt):
    return select(func.count()).select_from(stmt.subquery()).scalar_subquery()


def latest_release(project_id, customer_id=None):
    stmt = select(Release.id).join(D, D.release_id == Release.id).where(D.project_id == project_id)
    if customer_id is not None:
        stmt = stmt.where(D.customer_id == customer_id)
    return stmt.order_by(Release.created_at.desc().nulls_last(), Release.id.desc()).limit(1).correlate_except(Release, D).scalar_subquery()


def suppliers(profile=False):
    m = Supplier
    fields = [m.id, m.code, m.name, m.country, m.status,
        count(select(SoftwareProduct.id).where(SoftwareProduct.supplier_id == m.id).correlate(m)).label('software_count')]
    if profile:
        fields += [m.website, m.description]
    return select(*fields)


def customers():
    m = Customer
    projects = select(Project.id).where(Project.customer_id == m.id).correlate(m)
    with_release = projects.where(select(Release.id).join(D, D.release_id == Release.id)
        .where(D.project_id == Project.id, D.customer_id == m.id).correlate(Project, m).exists())
    return select(m.id, m.code, m.name, m.region, m.status,
        count(projects).label('project_count'), count(with_release).label('released_project_count'))


def projects():
    m = Project
    newest = latest_release(m.id)
    return select(m.id, m.project_code.label('code'), m.name, m.status, m.vehicle_platform,
        m.customer_id, Customer.code.label('customer_code'), Customer.name.label('customer_name'),
        newest.label('release_id'),
        select(Release.version).where(Release.id == newest).correlate(m).scalar_subquery().label('release_version'),
        select(Release.status).where(Release.id == newest).correlate(m).scalar_subquery().label('release_status'),
        count(select(ManufacturingSite.id).where(ManufacturingSite.project_id == m.id).correlate(m)).label('site_count'))\
        .outerjoin(Customer, Customer.id == m.customer_id)


def rows(db, stmt):
    return [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}
            for row in db.execute(stmt).mappings()]


def page(db, stmt, filters, kind, order, **context):
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'kind': kind, **context, 'total': total, 'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': rows(db, stmt.order_by(*order).limit(filters.limit).offset(filters.offset))}


def filter_rows(stmt, model, filters, code, extra=None):
    if filters.q and filters.q.strip():
        stmt = stmt.where(or_(code.contains(filters.q.strip(), autoescape=True), model.name.contains(filters.q.strip(), autoescape=True)))
    if filters.status:
        stmt = stmt.where(model.status == filters.status)
    if extra is not None:
        column, value = extra
        if value is not None and value != '':
            stmt = stmt.where(column.is_(None) if column.key == 'region' and value == 'UNASSIGNED' else column == value)
    return stmt


@router.get('/suppliers')
def supplier_catalog(filters: Annotated[SupplierFilters, Query()], db: Session = Depends(get_db)):
    stmt = filter_rows(suppliers(), Supplier, filters, Supplier.code, (Supplier.country, filters.country))
    return page(db, stmt, filters, 'suppliers', [Supplier.code, Supplier.id])


@router.get('/customers')
def customer_catalog(filters: Annotated[CustomerFilters, Query()], db: Session = Depends(get_db)):
    stmt = filter_rows(customers(), Customer, filters, Customer.code, (Customer.region, filters.region))
    return page(db, stmt, filters, 'customers', [Customer.code, Customer.id])


@router.get('/projects')
def project_catalog(filters: Annotated[ProjectFilters, Query()], db: Session = Depends(get_db)):
    stmt = filter_rows(projects(), Project, filters, Project.project_code, (Project.customer_id, filters.customer_id))
    return page(db, stmt, filters, 'projects', [Project.project_code, Project.id])


def parent(kind, identifier, db):
    model = {'suppliers': Supplier, 'customers': Customer, 'projects': Project}.get(kind)
    if model is None:
        raise HTTPException(404, 'organization kind not found')
    stmt = {'suppliers': lambda: suppliers(True), 'customers': customers, 'projects': projects}[kind]()
    if kind == 'projects':
        try:
            key = uuid.UUID(identifier)
        except ValueError:
            key = None
        stmt = stmt.where(Project.id == key) if key else stmt.where(Project.project_code == identifier)
    else:
        stmt = stmt.where(model.code == identifier)
    matches = rows(db, stmt.limit(2))
    if len(matches) > 1:
        raise HTTPException(409, 'project code is ambiguous; use project ID')
    if not matches:
        raise HTTPException(404, 'organization not found')
    return {'kind': kind, **matches[0]}


@router.get('/{kind}/{identifier}/summary')
def summary(kind: str, identifier: str, filters: Annotated[Empty, Query()], db: Session = Depends(get_db)):
    return parent(kind, identifier, db)


@router.get('/{kind}/{identifier}/items')
def items(kind: str, identifier: str, filters: Annotated[OwnedPage, Query()], db: Session = Depends(get_db)):
    owner = parent(kind, identifier, db)
    if owner['id'] != str(filters.organization_id):
        raise HTTPException(404, 'organization selection changed')
    key = filters.organization_id
    if kind == 'suppliers':
        m = SoftwareProduct
        latest = select(Release.id).where(Release.software_id == m.id, Release.release_type == 'STANDARD')\
            .order_by(Release.created_at.desc().nulls_last(), Release.id.desc()).limit(1).correlate(m).scalar_subquery()
        stmt = select(m.id, m.code, m.name, m.software_type.label('type'), m.status, latest.label('release_id'),
            select(Release.version).where(Release.id == latest).correlate(m).scalar_subquery().label('release_version'))\
            .where(m.supplier_id == key)
        order = [m.code, m.id]
    elif kind == 'customers':
        m = Project
        latest = latest_release(m.id, key)
        stmt = select(m.id, m.project_code.label('code'), m.name, m.status, latest.label('release_id'),
            select(Release.version).where(Release.id == latest).correlate(m).scalar_subquery().label('release_version'),
            select(Release.status).where(Release.id == latest).correlate(m).scalar_subquery().label('release_status'))\
            .where(m.customer_id == key)
        order = [m.project_code, m.id]
    else:
        m = ManufacturingSite
        stmt = select(m.id, m.site_code.label('code'), m.name, m.status).where(m.project_id == key)
        order = [m.site_code, m.id]
    return page(db, stmt, filters, kind, order, organization_id=owner['id'])
