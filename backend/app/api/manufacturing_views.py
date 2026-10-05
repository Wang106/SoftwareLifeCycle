"""Bounded manufacturing observations; stored states do not authorize production."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased
from app.core.db import get_db
from app.models.core import Customer, Project, Release
from app.models.distribution import SoftwareAuthorization as Authorization
from app.models.production import Deployment, ManufacturingSite as Site, ProductionLine as Line, ProductionBatch as Batch, SoftwareChangeover as Changeover
from app.models.snapshot import ReleaseSnapshot as Snapshot

router = APIRouter(prefix='/api/v1/manufacturing-views/sites', tags=['manufacturing views'])


class Page(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


class Filters(Page):
    q: str | None = Field(None, max_length=200)
    status: str | None = Field(None, max_length=30)
    region: str | None = Field(None, max_length=100)
    customer_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class OwnedPage(Page):
    site_id: uuid.UUID


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


def line_rows():
    d = Deployment
    ranked = select(d.id, d.production_line_id,
        func.row_number().over(partition_by=d.production_line_id,
            order_by=[d.created_at.desc().nulls_last(), d.id.desc()]).label('rank')).subquery()
    er, ar, es, ac = aliased(Release), aliased(Release), aliased(Snapshot), aliased(Snapshot)
    return select(Line.id, Line.site_id, Line.line_code, Line.name, Line.status,
        d.id.label('deployment_id'), d.deployment_no, d.status.label('deployment_status'), d.actual_version, d.deployed_at,
        d.authorization_id, Authorization.authorization_no, Authorization.status.label('authorization_status'),
        d.expected_release_id, er.version.label('expected_version'), er.release_type.label('expected_type'),
        d.expected_snapshot_id, es.snapshot_no.label('expected_snapshot_no'),
        d.actual_release_id, ar.version.label('actual_release_version'), ar.release_type.label('actual_type'),
        d.actual_snapshot_id, ac.snapshot_no.label('actual_snapshot_no'))\
        .outerjoin(ranked, (ranked.c.production_line_id == Line.id) & (ranked.c.rank == 1))\
        .outerjoin(d, d.id == ranked.c.id).outerjoin(Authorization, Authorization.id == d.authorization_id)\
        .outerjoin(er, er.id == d.expected_release_id).outerjoin(es, es.id == d.expected_snapshot_id)\
        .outerjoin(ar, ar.id == d.actual_release_id).outerjoin(ac, ac.id == d.actual_snapshot_id)


def sites(profile=False):
    lv = line_rows().cte('manufacturing_lines')
    def count(condition=None):
        stmt = select(func.count()).select_from(lv).where(lv.c.site_id == Site.id)
        if condition is not None:
            stmt = stmt.where(condition)
        return stmt.correlate(Site).scalar_subquery()
    fields = [Site.id, Site.site_code, Site.name, Site.region, Site.status, Site.customer_id, Site.project_id,
        Customer.code.label('customer_code'), Customer.name.label('customer_name'),
        Project.project_code.label('project_code'), Project.name.label('project_name'),
        count().label('line_count'), count(lv.c.deployment_id.is_not(None)).label('deployed_line_count'),
        count(lv.c.deployment_status == 'MATCH').label('matching_line_count'),
        count(lv.c.deployment_status != 'MATCH').label('attention_line_count')]
    if profile:
        fields += [count(lv.c.authorization_status == 'APPROVED').label('approved_authorization_line_count')]
        def first(column):
            return select(lv.c[column]).where(lv.c.site_id == Site.id)\
                .order_by(lv.c.name, lv.c.id).limit(1).correlate(Site).scalar_subquery()
        for column in ['deployment_id', 'deployment_no', 'authorization_id', 'authorization_no', 'authorization_status',
                       'expected_release_id', 'expected_version', 'expected_type', 'expected_snapshot_id', 'expected_snapshot_no']:
            fields.append(first(column).label('first_' + column))
        for column in ['id', 'changeover_no', 'status']:
            fields.append(select(getattr(Changeover, column)).where(Changeover.deployment_id == first('deployment_id'))
                .order_by(Changeover.changed_at.asc().nulls_last(), Changeover.id).limit(1).correlate(Site)
                .scalar_subquery().label('first_changeover_' + column))
        # Legacy context chooses the first batch on the first name-ordered line
        # with a batch on its newest deployment. It is not an active-batch claim.
        for column in ['id', 'batch_no', 'status', 'note']:
            fields.append(select(getattr(Batch, column)).join(lv, lv.c.deployment_id == Batch.deployment_id)
                .where(lv.c.site_id == Site.id).order_by(lv.c.name, lv.c.id, Batch.started_at.asc().nulls_last(), Batch.id)
                .limit(1).correlate(Site).scalar_subquery().label('context_batch_' + column))
    return select(*fields).outerjoin(Customer, Customer.id == Site.customer_id).outerjoin(Project, Project.id == Site.project_id)


def rows(db, stmt):
    return [{key: str(value) if isinstance(value, uuid.UUID) else value for key, value in row.items()}
        for row in db.execute(stmt).mappings()]


def page(db, stmt, filters, order, **pins):
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {**pins, 'total': total, 'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': rows(db, stmt.order_by(*order).limit(filters.limit).offset(filters.offset))}


@router.get('')
def catalog(filters: Annotated[Filters, Query()], db: Session = Depends(get_db)):
    stmt = sites()
    for field in ['status', 'region', 'customer_id', 'project_id']:
        value = getattr(filters, field)
        if value is not None and value != '':
            stmt = stmt.where(getattr(Site, field) == value)
    if filters.q and filters.q.strip():
        stmt = stmt.where(or_(Site.site_code.contains(filters.q.strip(), autoescape=True), Site.name.contains(filters.q.strip(), autoescape=True)))
    return page(db, stmt, filters, [Site.name, Site.id], kind='manufacturing-sites')


def parent(identifier, db):
    try:
        key = uuid.UUID(identifier)
    except ValueError:
        key = None
    selection = or_(Site.id == key, Site.site_code == identifier) if key else Site.site_code == identifier
    matches = rows(db, sites(True).where(selection).limit(2))
    if len(matches) > 1:
        raise HTTPException(409, 'site identifier is ambiguous')
    if not matches:
        raise HTTPException(404, 'manufacturing site not found')
    return {'kind': 'manufacturing-site', **matches[0]}


@router.get('/{identifier:path}/summary')
def summary(identifier: str, filters: Annotated[Empty, Query()], db: Session = Depends(get_db)):
    return parent(identifier, db)


@router.get('/{identifier:path}/lines')
def lines(identifier: str, filters: Annotated[OwnedPage, Query()], db: Session = Depends(get_db)):
    owner = parent(identifier, db)
    if owner['id'] != str(filters.site_id):
        raise HTTPException(404, 'site selection changed')
    stmt = line_rows().where(Line.site_id == filters.site_id)
    return page(db, stmt, filters, [Line.name, Line.id], kind='manufacturing-lines', site_id=owner['id'], site_code=owner['site_code'])
