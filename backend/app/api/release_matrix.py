"""Customer/project release history, including empty organization contexts."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.db import get_db
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot

router = APIRouter(prefix='/api/v1/organizations', tags=['organizations'])
Region = Literal['APAC', 'EUROPE', 'AMERICAS', 'OTHER', 'UNASSIGNED']


@router.get('/release-matrix')
def release_matrix(region: Region | None = None,
                   customer: str | None = Query(None, min_length=1, max_length=50),
                   project_id: uuid.UUID | None = None,
                   status: str | None = Query(None, min_length=1, max_length=30),
                   q: str | None = Query(None, max_length=100),
                   limit: int = Query(50, ge=1, le=100),
                   offset: int = Query(0, ge=0, le=100000), db: Session = Depends(get_db)):
    application, baseline = aliased(Release), aliased(Release)
    latest_snapshot_id = select(ReleaseSnapshot.id).where(
        ReleaseSnapshot.release_id == application.id).order_by(
        ReleaseSnapshot.snapshot_number.desc()).limit(1).correlate(application).scalar_subquery()
    statement = select(Customer, Project, application, baseline, SoftwareProduct, ReleaseSnapshot).select_from(Customer)
    statement = statement.outerjoin(Project, Project.customer_id == Customer.id).outerjoin(
        ApplicationReleaseDetail, and_(ApplicationReleaseDetail.project_id == Project.id,
                                      ApplicationReleaseDetail.customer_id == Customer.id)).outerjoin(
        application, and_(application.id == ApplicationReleaseDetail.release_id,
                          application.release_type == 'APPLICATION')).outerjoin(
        baseline, and_(baseline.id == ApplicationReleaseDetail.standard_base_release_id,
                       baseline.release_type == 'STANDARD')).outerjoin(
        SoftwareProduct, SoftwareProduct.id == application.software_id).outerjoin(
        ReleaseSnapshot, ReleaseSnapshot.id == latest_snapshot_id)
    if region:
        statement = statement.where(Customer.region.is_(None) if region == 'UNASSIGNED' else Customer.region == region)
    if customer:
        statement = statement.where(Customer.code == customer)
    if project_id:
        statement = statement.where(Project.id == project_id)
    if status:
        statement = statement.where(application.status == status)
    if q and q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = f'%{escaped}%'
        statement = statement.where(or_(*[column.ilike(pattern, escape='\\') for column in (
            Customer.code, Customer.name, Project.project_code, Project.name,
            SoftwareProduct.code, SoftwareProduct.name, application.version, baseline.version)]))
    # All summaries describe the filtered dataset, not just the current page.
    summary = db.execute(statement.with_only_columns(
        func.count(), func.count(func.distinct(Customer.id)), func.count(func.distinct(Project.id)),
        func.count(func.distinct(application.id)), maintain_column_froms=True)).one()
    rows = db.execute(statement.order_by(Customer.code, Project.project_code.asc().nulls_last(),
        Project.id.asc().nulls_last(), application.created_at.desc().nulls_last(),
        application.id.desc().nulls_last()).limit(limit).offset(offset)).all()
    def release_ref(row):
        return {'id': str(row.id), 'version': row.version, 'status': row.status,
                'created_at': row.created_at} if row else None
    return {'total': summary[0], 'summary': {'customers': summary[1], 'projects': summary[2],
            'application_releases': summary[3]},
            'next_offset': offset + limit if offset + limit < summary[0] else None,
            'items': [{
                'customer': {'code': c.code, 'name': c.name, 'region': c.region or 'UNASSIGNED', 'status': c.status},
                'project': {'id': str(p.id), 'code': p.project_code, 'name': p.name, 'status': p.status} if p else None,
                'software': {'code': software.code, 'name': software.name} if software else None,
                'application_release': release_ref(asr), 'standard_release': release_ref(ssr),
                'snapshot': {'snapshot_no': snap.snapshot_no, 'status': snap.status} if snap else None,
            } for c, p, asr, ssr, software, snap in rows]}
