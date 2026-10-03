"""Bounded SCR and Issue directories; observations, not release judgments."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.change import Issue, SoftwareChangeRequest

router = APIRouter(prefix='/api/v1/change-catalog', tags=['change and issue catalogs'])


class PageFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str | None = Field(None, max_length=200)
    status: str | None = Field(None, max_length=40)
    scope: str | None = Field(None, max_length=30)
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


class ChangeFilters(PageFilters):
    source: str | None = Field(None, max_length=30)
    change_type: str | None = Field(None, max_length=40)
    software_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class IssueFilters(PageFilters):
    severity: str | None = Field(None, max_length=20)


def filtered(stmt, model, filters, search, extra):
    for key in ['status', 'scope', *extra]:
        value = getattr(filters, key)
        if value is not None and value != '':
            stmt = stmt.where(getattr(model, key) == value)
    if filters.q and filters.q.strip():
        stmt = stmt.where(or_(*[column.contains(filters.q.strip(), autoescape=True) for column in search]))
    return stmt


def envelope(kind, filters, total, items, **extra):
    return {'kind': kind, 'total': total, 'limit': filters.limit, 'offset': filters.offset,
            'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
            'items': items, **extra}


@router.get('/requests')
def change_catalog(filters: Annotated[ChangeFilters, Query()], db: Session = Depends(get_db)):
    m = SoftwareChangeRequest
    stmt = filtered(select(m.id, m.request_no, m.title, m.source, m.scope, m.change_type,
        m.status, m.created_at), m, filters, [m.request_no, m.title],
        ['source', 'change_type', 'software_id', 'customer_id', 'project_id'])
    sub = stmt.subquery()
    # JS String.includes is case-sensitive. SQL replace preserves that behavior
    # on PostgreSQL and SQLite, unlike SQLite's case-insensitive default LIKE.
    def contains(token):
        return func.length(sub.c.status) > func.length(func.replace(sub.c.status, token, ''))
    total, testing, ready = db.execute(select(func.count(),
        func.coalesce(func.sum(case((contains('TEST'), 1), else_=0)), 0),
        func.coalesce(func.sum(case((contains('READY'), 1), else_=0)), 0)).select_from(sub)).one()
    rows = db.execute(stmt.order_by(m.created_at.desc().nulls_last(), m.id.desc())
        .limit(filters.limit).offset(filters.offset)).mappings()
    return envelope('changes', filters, total, [
        {key: str(row[key]) if key == 'id' else row[key] for key in
         ['id', 'request_no', 'title', 'source', 'scope', 'change_type', 'status']} for row in rows
    ], in_verification=testing, ready_for_release=ready)


@router.get('/issues')
def issue_catalog(filters: Annotated[IssueFilters, Query()], db: Session = Depends(get_db)):
    m = Issue
    # Descriptions remain on the exact profile, not the directory projection.
    stmt = filtered(select(m.id, m.issue_no, m.title, m.scope, m.severity, m.status),
        m, filters, [m.issue_no, m.title], ['severity'])
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(m.issue_no, m.id).limit(filters.limit).offset(filters.offset)).mappings()
    return envelope('issues', filters, total, [dict(row, id=str(row['id'])) for row in rows])
