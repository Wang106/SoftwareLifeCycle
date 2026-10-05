"""Bounded DVP browsing and exact-context execution history."""
import uuid
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, SoftwareChangeRequest
from app.models.acceptance import AcceptanceDvpLink
from app.models.core import ApplicationReleaseDetail, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, DvpPlan, IssueDvpItem, TestRelease

router = APIRouter(prefix='/api/v1/testing/dvp', tags=['DVP browsing'])


def execution_context(db, release_id, snapshot_no):
    if snapshot_no and not release_id:
        raise HTTPException(422, 'snapshot_no requires release_id')
    release = db.get(Release, release_id) if release_id else None
    if release_id and not release:
        raise HTTPException(404, 'release not found')
    snapshot = None
    if release:
        stmt = select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id, ReleaseSnapshot.status == 'FROZEN')
        if snapshot_no:
            snapshot = db.scalars(stmt.where(ReleaseSnapshot.snapshot_no == snapshot_no).limit(1)).first()
            if not snapshot:
                raise HTTPException(409, 'snapshot is not a frozen snapshot of the selected release')
        else:
            snapshot = db.scalars(stmt.order_by(ReleaseSnapshot.snapshot_number.desc(), ReleaseSnapshot.id.desc()).limit(1)).first()
    return release, snapshot


def context_json(release, snapshot):
    return {'release': {'id': str(release.id), 'version': release.version, 'type': release.release_type} if release else None,
            'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no} if snapshot else None,
            'mode': 'EXACT_SNAPSHOT' if snapshot else 'NO_FROZEN_SNAPSHOT' if release else 'ALL_RECORDED_CONTEXTS'}


def scoped_items(stmt, release):
    stmt = stmt.where(SoftwareChangeRequest.software_id == release.software_id)
    if release.release_type == 'APPLICATION':
        stmt = stmt.join(ApplicationReleaseDetail, ApplicationReleaseDetail.release_id == release.id).where(
            or_(SoftwareChangeRequest.project_id.is_(None), SoftwareChangeRequest.project_id == ApplicationReleaseDetail.project_id),
            or_(SoftwareChangeRequest.customer_id.is_(None), SoftwareChangeRequest.customer_id == ApplicationReleaseDetail.customer_id))
    return stmt


def serialize_executions(db, rows):
    if not rows:
        return []
    releases = {r.id: r for r in db.scalars(select(Release).where(Release.id.in_({e.release_id for e in rows}))).all()}
    snapshots = {s.id: s for s in db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.id.in_({e.snapshot_id for e in rows}))).all()}
    tests = {t.id: t for t in db.scalars(select(TestRelease).where(TestRelease.id.in_({e.test_release_id for e in rows if e.test_release_id}))).all()}
    result = []
    for e in rows:
        release, snapshot, test = releases.get(e.release_id), snapshots.get(e.snapshot_id), tests.get(e.test_release_id)
        consistent = bool(release and snapshot and snapshot.release_id == e.release_id and snapshot.status == 'FROZEN'
            and (not e.test_release_id or test and test.release_id == e.release_id and test.snapshot_id == e.snapshot_id))
        result.append({'execution_no': e.execution_no, 'result': e.result, 'actual_result': e.actual_result,
            'executed_at': e.executed_at, 'release_id': str(e.release_id), 'release_version': release.version if release else None,
            'release_type': release.release_type if release else None, 'snapshot_id': str(e.snapshot_id),
            'snapshot_no': snapshot.snapshot_no if snapshot else None, 'test_release_no': test.test_release_no if test else None,
            'context_consistent': consistent})
    return result


@router.get('/catalog')
def dvp_catalog(scr: str | None = Query(None, max_length=50), plan: str | None = Query(None, max_length=50),
    scope: str | None = Query(None, max_length=30), status: str | None = Query(None, max_length=30),
    result: str | None = Query(None, max_length=30), q: str | None = Query(None, max_length=200),
    release_id: uuid.UUID | None = None, snapshot_no: str | None = Query(None, min_length=1, max_length=80),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000), db: Session = Depends(get_db)):
    release, snapshot = execution_context(db, release_id, snapshot_no)
    execution_stmt = select(DvpExecution.dvp_item_id.label('item_id'), func.max(DvpExecution.execution_no).label('number'),
        func.count().label('execution_count')).group_by(DvpExecution.dvp_item_id)
    if release:
        execution_stmt = execution_stmt.where(DvpExecution.release_id == release.id,
            DvpExecution.snapshot_id == snapshot.id if snapshot else DvpExecution.id.is_(None))
    latest = execution_stmt.subquery()
    stmt = select(DvpItem.id.label('item_id'), DvpItem.item_no, DvpItem.title, DvpItem.scope, DvpItem.status,
        DvpPlan.plan_no, SoftwareChangeRequest.request_no, latest.c.execution_count,
        DvpExecution.id.label('execution_id')).join(DvpPlan, DvpPlan.id == DvpItem.plan_id)
    stmt = stmt.join(SoftwareChangeRequest, SoftwareChangeRequest.id == DvpPlan.change_request_id)
    stmt = stmt.outerjoin(latest, latest.c.item_id == DvpItem.id).outerjoin(DvpExecution,
        and_(DvpExecution.dvp_item_id == DvpItem.id, DvpExecution.execution_no == latest.c.number))
    if release:
        stmt = scoped_items(stmt, release)
    for value, column in [(scr, SoftwareChangeRequest.request_no), (plan, DvpPlan.plan_no), (scope, DvpItem.scope), (status, DvpItem.status)]:
        if value:
            stmt = stmt.where(column == value)
    if result:
        stmt = stmt.where(DvpExecution.id.is_(None) if result == 'NOT_EXECUTED' else DvpExecution.result == result)
    if q and q.strip():
        stmt = stmt.where(or_(*[column.contains(q.strip(), autoescape=True) for column in
            (DvpItem.item_no, DvpItem.title, DvpPlan.plan_no, DvpPlan.title, SoftwareChangeRequest.request_no)]))
    filtered = stmt.subquery()
    counts = db.execute(select(func.count(), func.count(filtered.c.execution_id),
        func.count().filter(filtered.c.execution_count >= 2)).select_from(filtered)).one()
    # Totals cover the entire filtered result, not just the visible page.
    outcomes = dict(db.execute(select(DvpExecution.result, func.count()).join(filtered,
        filtered.c.execution_id == DvpExecution.id).group_by(DvpExecution.result)).all())
    page = db.execute(stmt.order_by(DvpItem.item_no, DvpItem.id).limit(limit).offset(offset)).all()
    executions = db.scalars(select(DvpExecution).where(DvpExecution.id.in_([r.execution_id for r in page if r.execution_id]))).all()
    evidence = {str(e.id): details for e, details in zip(executions, serialize_executions(db, executions))}
    options = db.scalars(select(Release).where(Release.software_id.in_(select(SoftwareChangeRequest.software_id).join(DvpPlan,
        DvpPlan.change_request_id == SoftwareChangeRequest.id))).order_by(Release.created_at.desc(), Release.id.desc()).limit(101)).all()
    return {'context': context_json(release, snapshot), 'total': counts[0], 'summary': {'executed': counts[1],
        'not_executed': counts[0] - counts[1], 'retested': counts[2], 'recorded_latest_results': outcomes},
        'items': [{'id': str(r.item_id), 'item_no': r.item_no, 'title': r.title, 'scope': r.scope, 'status': r.status,
            'plan_no': r.plan_no, 'request_no': r.request_no, 'execution_count': r.execution_count or 0,
            'latest_execution': evidence.get(str(r.execution_id)) if r.execution_id else None} for r in page],
        'next_offset': offset + limit if offset + limit < counts[0] else None,
        'release_options': [{'id': str(r.id), 'version': r.version, 'type': r.release_type} for r in options[:100]],
        'release_options_truncated': len(options) > 100}


class RelationPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dvp_item_id: uuid.UUID
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def relation_rows(item_id, kind):
    if kind == 'criteria':
        c, link = AcceptanceCriterion, AcceptanceDvpLink
        return select(c.id, c.criterion_no.label('number'), c.description.label('text')).where(
            select(link.id).where(link.criterion_id == c.id, link.dvp_item_id == item_id).exists())
    if kind == 'points':
        c, link = ChangePoint, ChangePointDvpItem
        return select(c.id, c.change_no.label('number'), c.title.label('text')).where(
            select(link.change_point_id).where(link.change_point_id == c.id, link.dvp_item_id == item_id).exists())
    c, link = Issue, IssueDvpItem
    return select(c.id, c.issue_no.label('number'), c.title.label('text')).where(
        select(link.issue_id).where(link.issue_id == c.id, link.dvp_item_id == item_id).exists())


@router.get('/id/{item_id}/relations/{kind}')
def dvp_relations(item_id: uuid.UUID, kind: Literal['criteria', 'points', 'issues'],
    filters: Annotated[RelationPage, Query()], db: Session = Depends(get_db)):
    if filters.dvp_item_id != item_id or not db.get(DvpItem, item_id):
        raise HTTPException(404, 'DVP item not found')
    rows = relation_rows(item_id, kind).subquery()
    total = db.scalar(select(func.count()).select_from(rows))
    page = db.execute(select(rows).order_by(rows.c.number, rows.c.id)
                      .limit(filters.limit).offset(filters.offset)).mappings()
    return {'item_id': str(item_id), 'kind': kind, 'total': total,
        'limit': filters.limit, 'offset': filters.offset,
        'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': [dict(row, id=str(row['id'])) for row in page]}


@router.get('/id/{item_id}/profile')
def dvp_profile(item_id: uuid.UUID, db: Session = Depends(get_db)):
    item = db.get(DvpItem, item_id)
    if not item:
        raise HTTPException(404, 'DVP item not found')
    plan = db.get(DvpPlan, item.plan_id)
    scr = db.get(SoftwareChangeRequest, plan.change_request_id) if plan else None
    options = db.scalars(select(Release).where(Release.id.in_(select(DvpExecution.release_id)
        .where(DvpExecution.dvp_item_id == item.id))).order_by(Release.created_at.desc(), Release.id.desc()).limit(101)).all()
    counts = {kind: db.scalar(select(func.count()).select_from(relation_rows(item.id, kind).subquery()))
              for kind in ('criteria', 'points', 'issues')}
    return {'id': str(item.id), 'item_no': item.item_no, 'title': item.title, 'scope': item.scope, 'status': item.status,
        'relation_counts': counts,
        'plan': {'plan_no': plan.plan_no, 'title': plan.title, 'change_request_no': scr.request_no if scr else None} if plan else None,
        'release_options': [{'id': str(r.id), 'version': r.version, 'type': r.release_type} for r in options[:100]],
        'release_options_truncated': len(options) > 100}


@router.get('/id/{item_id}/executions')
def dvp_history(item_id: uuid.UUID, release_id: uuid.UUID | None = None,
    snapshot_no: str | None = Query(None, min_length=1, max_length=80), result: str | None = Query(None, max_length=30),
    limit: int = Query(50, ge=1, le=200), before_number: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    if not db.get(DvpItem, item_id):
        raise HTTPException(404, 'DVP item not found')
    release, snapshot = execution_context(db, release_id, snapshot_no)
    stmt = select(DvpExecution).where(DvpExecution.dvp_item_id == item_id)
    if release:
        stmt = stmt.where(DvpExecution.release_id == release.id,
            DvpExecution.snapshot_id == snapshot.id if snapshot else DvpExecution.id.is_(None))
    if result:
        stmt = stmt.where(DvpExecution.result == result)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if before_number:
        stmt = stmt.where(DvpExecution.execution_no < before_number)
    rows = db.scalars(stmt.order_by(DvpExecution.execution_no.desc()).limit(limit + 1)).all()
    page = rows[:limit]
    return {'item_id': str(item_id), 'context': context_json(release, snapshot), 'total': total, 'items': serialize_executions(db, page),
        'next_before_number': page[-1].execution_no if len(rows) > limit else None}
