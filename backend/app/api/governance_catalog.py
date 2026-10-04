"""Exact, bounded governance history. No approval state transitions are performed."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func,or_,select,and_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.approval import ApprovalRequest,ApprovalStep,ApprovalAction,ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot

router=APIRouter(prefix='/api/v1/governance',tags=['governance history'])

class Filters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    state: str | None=Field(None,max_length=30)
    release_id: uuid.UUID | None=None
    snapshot_id: uuid.UUID | None=None
    approval_id: uuid.UUID | None=None
    q: str | None=Field(None,max_length=200)
    limit: int=Field(50,ge=1,le=100)
    offset: int=Field(0,ge=0,le=100000)

class HistoryFilters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approval_id: uuid.UUID | None=None
    action: str | None=Field(None,max_length=30)
    limit: int=Field(50,ge=1,le=100)
    offset: int=Field(0,ge=0,le=100000)


def references(release,snapshot):
    return {'release':{'id':str(release.id),'type':release.release_type,'version':release.version} if release else None,
        'snapshot':{'id':str(snapshot.id),'snapshot_no':snapshot.snapshot_no,'status':snapshot.status,'content_hash':snapshot.content_hash} if snapshot else None}


def approval_row(a,r,s):
    state='UNVERIFIED_TARGET_TYPE' if a.target_type!='RELEASE' else 'CONSISTENT' if r and s and s.release_id==r.id and s.status=='FROZEN' else 'MISMATCH'
    return {'id':str(a.id),'approval_no':a.approval_no,'target_type':a.target_type,'target_id':str(a.target_id),
        'snapshot_id':str(a.snapshot_id) if a.snapshot_id else None,'status':a.status,'submitted_by':a.submitted_by,
        'submitted_at':a.submitted_at,**references(r,s),'binding_state':state}


def decision_row(d,a,r,s):
    match=bool(r and s and s.release_id==r.id and s.status=='FROZEN' and a and a.target_type=='RELEASE' and a.target_id==d.release_id and a.snapshot_id==d.snapshot_id)
    return {'id':str(d.id),'decision_no':d.decision_no,'decision':d.decision,'readiness_status':d.readiness_status,
        'decided_by':d.decided_by,'decided_at':d.decided_at,'decision_notes':d.decision_notes,
        'release_id':str(d.release_id),'snapshot_id':str(d.snapshot_id),**references(r,s),'context_consistent':match,
        'approval':{'id':str(a.id),'approval_no':a.approval_no,'status':a.status} if a else None}


def apply_filters(stmt,filters,state,release_id,snapshot_id,search):
    for value,column in [(filters.state,state),(filters.release_id,release_id),(filters.snapshot_id,snapshot_id)]:
        if value is not None and value!='':stmt=stmt.where(column==value)
    if filters.q and filters.q.strip():stmt=stmt.where(or_(*[c.contains(filters.q.strip(),autoescape=True) for c in search]))
    return stmt


def paged(db,stmt,filters,state_name,order):
    sub=stmt.subquery();column=sub.c[state_name]
    total=db.scalar(select(func.count()).select_from(sub))
    states=dict(db.execute(select(column,func.count()).group_by(column)).all())
    rows=db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).all()
    return rows,{'total':total,'state_counts':states,'next_offset':filters.offset+filters.limit if filters.offset+filters.limit<total else None}


def approval_stmt():
    a=ApprovalRequest
    return select(a,Release,ReleaseSnapshot).outerjoin(Release,and_(a.target_type=='RELEASE',Release.id==a.target_id)).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==a.snapshot_id)


def decision_stmt():
    d=ReleaseDecision
    return select(d,ApprovalRequest,Release,ReleaseSnapshot).outerjoin(ApprovalRequest,ApprovalRequest.id==d.approval_request_id).outerjoin(Release,Release.id==d.release_id).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==d.snapshot_id)


@router.get('/approvals')
def approval_catalog(filters: Annotated[Filters,Query()],db: Session=Depends(get_db)):
    a=ApprovalRequest
    stmt=apply_filters(approval_stmt(),filters,a.status,Release.id,a.snapshot_id,[a.approval_no,a.submitted_by,Release.version,ReleaseSnapshot.snapshot_no])
    if filters.approval_id:stmt=stmt.where(a.id==filters.approval_id)
    rows,result=paged(db,stmt,filters,'status',[a.approval_no,a.id]);ids=[a.id for a,_,_ in rows]
    counts={}
    if ids:
        for model in [ApprovalStep,ApprovalAction,ReleaseDecision]:
            counts[model]=dict(db.execute(select(model.approval_request_id,func.count()).where(model.approval_request_id.in_(ids)).group_by(model.approval_request_id)).all())
    return {**result,'items':[{**approval_row(a,r,s),'step_count':counts.get(ApprovalStep,{}).get(a.id,0),
        'action_count':counts.get(ApprovalAction,{}).get(a.id,0),'decision_count':counts.get(ReleaseDecision,{}).get(a.id,0)} for a,r,s in rows]}


@router.get('/decisions')
def decision_catalog(filters: Annotated[Filters,Query()],db: Session=Depends(get_db)):
    d=ReleaseDecision;a=ApprovalRequest
    stmt=apply_filters(decision_stmt(),filters,d.decision,d.release_id,d.snapshot_id,[d.decision_no,d.decided_by,a.approval_no,Release.version,ReleaseSnapshot.snapshot_no])
    if filters.approval_id:stmt=stmt.where(d.approval_request_id==filters.approval_id)
    rows,result=paged(db,stmt,filters,'decision',[d.decision_no,d.id])
    return {**result,'items':[decision_row(*row) for row in rows]}


@router.get('/decisions/{decision_no}')
def decision_profile(decision_no: str,db: Session=Depends(get_db)):
    row=db.execute(decision_stmt().where(ReleaseDecision.decision_no==decision_no)).first()
    if not row:raise HTTPException(404,'release decision not found')
    return decision_row(*row)


def _approval_profile(approval_no, db, include_steps=True):
    row=db.execute(approval_stmt().where(ApprovalRequest.approval_no==approval_no)).first()
    if not row:raise HTTPException(404,'approval not found')
    a,r,s=row
    steps=db.scalars(select(ApprovalStep).where(ApprovalStep.approval_request_id==a.id).order_by(ApprovalStep.step_order,ApprovalStep.id).limit(200)).all() if include_steps else []
    step_total=db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.approval_request_id==a.id))
    action_total=db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.approval_request_id==a.id))
    result = {**approval_row(a,r,s), 'step_total':step_total, 'action_total':action_total}
    if include_steps:
        result.update(steps_truncated=step_total>len(steps), steps=[step_row(step) for step in steps])
    return result


def step_row(step):
    return {'id':str(step.id),'step_order':step.step_order,'role_name':step.role_name,
            'approver_name':step.approver_name,'status':step.status}


@router.get('/approvals/{approval_no}')
def approval_profile(approval_no: str,db: Session=Depends(get_db)):
    return _approval_profile(approval_no,db)


@router.get('/approvals/{approval_no}/summary')
def approval_summary(approval_no: str,db: Session=Depends(get_db)):
    return _approval_profile(approval_no,db,False)


class StepFilters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approval_id: uuid.UUID
    limit: int=Field(50,ge=1,le=100)
    offset: int=Field(0,ge=0,le=100000)


@router.get('/approvals/{approval_no}/steps')
def step_history(approval_no: str,filters: Annotated[StepFilters,Query()],db: Session=Depends(get_db)):
    a=db.scalar(select(ApprovalRequest).where(ApprovalRequest.approval_no==approval_no).limit(1))
    if not a or a.id!=filters.approval_id:raise HTTPException(404,'approval not found')
    stmt=select(ApprovalStep).where(ApprovalStep.approval_request_id==a.id)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.scalars(stmt.order_by(ApprovalStep.step_order,ApprovalStep.id).limit(filters.limit).offset(filters.offset)).all()
    return {'approval_id':str(a.id),'approval_no':a.approval_no,'total':total,'limit':filters.limit,
        'offset':filters.offset,'next_offset':filters.offset+filters.limit if filters.offset+filters.limit<total else None,
        'items':[step_row(step) for step in rows]}


@router.get('/approvals/{approval_no}/actions')
def action_history(approval_no: str,filters: Annotated[HistoryFilters,Query()],db: Session=Depends(get_db)):
    a=db.scalars(select(ApprovalRequest).where(ApprovalRequest.approval_no==approval_no)).first()
    if not a or (filters.approval_id is not None and filters.approval_id!=a.id):raise HTTPException(404,'approval not found')
    stmt=select(ApprovalAction,ApprovalStep).outerjoin(ApprovalStep,ApprovalStep.id==ApprovalAction.step_id).where(ApprovalAction.approval_request_id==a.id)
    if filters.action:stmt=stmt.where(ApprovalAction.action==filters.action)
    rows,result=paged(db,stmt,filters,'action',[ApprovalAction.created_at.desc(),ApprovalAction.id.desc()])
    return {**result,'approval_id':str(a.id),'approval_no':a.approval_no,'items':[{'id':str(action.id),'actor_name':action.actor_name,'action':action.action,'comment':action.comment,'created_at':action.created_at,
        'step':{'id':str(step.id),'role_name':step.role_name,'step_order':step.step_order} if step else None,
        'step_id':str(action.step_id) if action.step_id else None,'context_consistent':not action.step_id or bool(step and step.approval_request_id==a.id)} for action,step in rows]}
