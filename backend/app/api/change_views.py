"""Exact SCR summary and independently bounded child/assignment projections."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import Customer, Project, SoftwareProduct
from app.models.testing import ChangePointDvpItem, DvpItem, DvpPlan

router = APIRouter(prefix='/api/v1/change-views', tags=['change request views'])


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PageFilters(Selection):
    change_id: uuid.UUID
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def owner(db, request_no, filters):
    identifier = db.scalar(select(SoftwareChangeRequest.id).where(SoftwareChangeRequest.request_no == request_no))
    if identifier is None or identifier != filters.change_id:
        raise HTTPException(404, 'change request identity not found')
    return identifier


def page(db, stmt, request_no, identifier, filters, order, **extra):
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).mappings()
    items = [{key: str(value) if isinstance(value, uuid.UUID) else value for key, value in row.items()} for row in rows]
    return {'change_id': str(identifier), 'request_no': request_no, 'total': count,
            'limit': filters.limit, 'offset': filters.offset,
            'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < count else None,
            'items': items, **extra}


def point_links(identifier):
    # Match the legacy profile: a missing DVP item is not a visible assignment.
    # A real item in another plan remains linked; never infer plan ownership.
    return select(ChangePointDvpItem.change_point_id, DvpItem.id.label('id'),
        DvpItem.item_no, DvpItem.title, DvpItem.status, DvpItem.plan_id,
        ChangePointDvpItem.relation_type).join(DvpItem,
        DvpItem.id == ChangePointDvpItem.dvp_item_id).where(ChangePointDvpItem.change_point_id == identifier)


@router.get('/{request_no}/summary')
def change_summary(request_no: str, filters: Annotated[Selection, Query()], db: Session = Depends(get_db)):
    m = SoftwareChangeRequest
    # Explicit correlated scalar counts avoid ID lists and rich nested children.
    counts = {
        'criterion_count': select(func.count(AcceptanceCriterion.id)).where(AcceptanceCriterion.change_request_id == m.id),
        'issue_count': select(func.count(IssueChangeRequestRelation.id)).join(Issue, Issue.id == IssueChangeRequestRelation.issue_id).where(IssueChangeRequestRelation.change_request_id == m.id),
        'point_count': select(func.count(ChangePoint.id)).where(ChangePoint.change_request_id == m.id),
        'plan_count': select(func.count(DvpPlan.id)).where(DvpPlan.change_request_id == m.id),
        'plan_item_count': select(func.count(DvpItem.id)).join(DvpPlan, DvpPlan.id == DvpItem.plan_id).where(DvpPlan.change_request_id == m.id),
        'point_item_count': select(func.count()).select_from(ChangePointDvpItem).join(ChangePoint, ChangePoint.id == ChangePointDvpItem.change_point_id).join(DvpItem, DvpItem.id == ChangePointDvpItem.dvp_item_id).where(ChangePoint.change_request_id == m.id),
    }
    cols = [m.id, m.request_no, m.title, m.source, m.scope, m.change_type, m.status,
        m.background, m.requirement, m.created_at, SoftwareProduct.code.label('software_code'),
        SoftwareProduct.name.label('software_name'), Customer.code.label('customer_code'),
        Customer.name.label('customer_name'), Project.id.label('project_id'),
        Project.project_code.label('project_code'), Project.name.label('project_name')]
    stmt = select(*cols, *[q.correlate(m).scalar_subquery().label(key) for key, q in counts.items()]).outerjoin(
        SoftwareProduct, SoftwareProduct.id == m.software_id).outerjoin(Customer, Customer.id == m.customer_id).outerjoin(Project, Project.id == m.project_id).where(m.request_no == request_no)
    row = db.execute(stmt).mappings().first()
    if row is None:
        raise HTTPException(404, 'change request not found')
    return {**{key: str(row[key]) if key == 'id' else row[key] for key in
        ['id', 'request_no', 'title', 'source', 'scope', 'change_type', 'status', 'background', 'requirement', 'created_at', *counts]},
        'software': {'code': row['software_code'], 'name': row['software_name']} if row['software_code'] is not None else None,
        'customer': {'code': row['customer_code'], 'name': row['customer_name']} if row['customer_code'] is not None else None,
        'project': {'id': str(row['project_id']), 'code': row['project_code'], 'name': row['project_name']} if row['project_id'] else None}


@router.get('/{request_no}/criteria')
def criteria_page(request_no: str, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters); m = AcceptanceCriterion
    return page(db, select(m.id, m.criterion_no, m.description).where(m.change_request_id == identifier), request_no, identifier, filters, [m.criterion_no, m.id])


@router.get('/{request_no}/issues')
def issues_page(request_no: str, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters); r = IssueChangeRequestRelation; m = Issue
    stmt = select(r.id.label('relation_id'), m.id, m.issue_no, m.title, r.relation_type, m.status).join(m, m.id == r.issue_id).where(r.change_request_id == identifier)
    return page(db, stmt, request_no, identifier, filters, [m.issue_no, r.relation_type, r.id])


@router.get('/{request_no}/points')
def points_page(request_no: str, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters); m = ChangePoint
    linked = select(func.count()).select_from(ChangePointDvpItem).join(DvpItem,
        DvpItem.id == ChangePointDvpItem.dvp_item_id).where(ChangePointDvpItem.change_point_id == m.id).correlate(m).scalar_subquery()
    stmt = select(m.id, m.change_no, m.title, m.description, m.status, linked.label('item_count')).where(m.change_request_id == identifier)
    return page(db, stmt, request_no, identifier, filters, [m.change_no, m.id])


@router.get('/{request_no}/plans')
def plans_page(request_no: str, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters); m = DvpPlan
    linked = select(func.count(DvpItem.id)).where(DvpItem.plan_id == m.id).correlate(m).scalar_subquery()
    return page(db, select(m.id, m.plan_no, m.title, m.status, linked.label('item_count')).where(m.change_request_id == identifier), request_no, identifier, filters, [m.plan_no, m.id])


@router.get('/{request_no}/points/{point_id}/items')
def point_items_page(request_no: str, point_id: uuid.UUID, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters)
    if not db.scalar(select(ChangePoint.id).where(ChangePoint.id == point_id, ChangePoint.change_request_id == identifier)):
        raise HTTPException(404, 'owned change point not found')
    return page(db, point_links(point_id), request_no, identifier, filters, [DvpItem.item_no, DvpItem.id], point_id=str(point_id))


@router.get('/{request_no}/plans/{plan_id}/items')
def plan_items_page(request_no: str, plan_id: uuid.UUID, filters: Annotated[PageFilters, Query()], db: Session = Depends(get_db)):
    identifier = owner(db, request_no, filters)
    if not db.scalar(select(DvpPlan.id).where(DvpPlan.id == plan_id, DvpPlan.change_request_id == identifier)):
        raise HTTPException(404, 'owned DVP plan not found')
    m = DvpItem
    return page(db, select(m.id, m.item_no, m.title, m.status, m.plan_id).where(m.plan_id == plan_id), request_no, identifier, filters, [m.item_no, m.id], plan_id=str(plan_id))
