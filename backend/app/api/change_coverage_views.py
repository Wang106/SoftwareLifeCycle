"""Bounded current SCR definitions with exactly selected frozen execution context."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.acceptance import AcceptanceDvpLink
from app.models.core import ApplicationReleaseDetail, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, DvpPlan, IssueDvpItem

router = APIRouter(prefix='/api/v1/change-coverage-views', tags=['change coverage views'])
Kind = Literal['acceptance', 'points', 'issues']
WHITESPACE = ''.join(chr(value) for value in range(0x3001) if chr(value).isspace())
BASIS = 'Current SCR definitions and assignments; candidate releases are software/customer/project matches, not proof of change incorporation. Historical snapshots do not freeze these assignments.'

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    release_id: uuid.UUID | None = None
    snapshot_no: str | None = Field(None, min_length=1, max_length=80)
    snapshot_id: uuid.UUID | Literal['none'] | None = None

    @model_validator(mode='after')
    def context_fields(self):
        if (self.snapshot_no or self.snapshot_id is not None) and self.release_id is None:
            raise ValueError('snapshot selection requires release_id')
        if self.snapshot_no and self.snapshot_id is not None:
            raise ValueError('select snapshot_no or snapshot_id, not both')
        return self

class PageFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    change_id: uuid.UUID
    release_id: uuid.UUID | Literal['none']
    snapshot_id: uuid.UUID | Literal['none']
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)

    @model_validator(mode='after')
    def context_fields(self):
        if self.release_id == 'none' and self.snapshot_id != 'none':
            raise ValueError('snapshot requires a release')
        return self


def candidates(ctx):
    r = Release; a = ApplicationReleaseDetail
    stmt = select(r.id, r.release_type.label('type'), r.version, r.status, r.created_at).outerjoin(a,a.release_id == r.id).where(r.software_id == ctx['software_id'])
    if ctx['project_id']:
        stmt = stmt.where(or_(r.release_type == 'STANDARD',a.project_id == ctx['project_id']))
    if ctx['customer_id']:
        stmt = stmt.where(or_(r.release_type == 'STANDARD',a.customer_id == ctx['customer_id']))
    return stmt


def context(db, request_no, release_id=None, snapshot_no=None, snapshot_id=None, change_id=None):
    ctx = db.execute(select(SoftwareChangeRequest.id,SoftwareChangeRequest.request_no,SoftwareChangeRequest.software_id,
        SoftwareChangeRequest.project_id,SoftwareChangeRequest.customer_id,SoftwareChangeRequest.requirement).where(SoftwareChangeRequest.request_no == request_no)).mappings().first()
    if ctx is None or (change_id is not None and change_id != ctx['id']):
        raise HTTPException(404,'change request identity not found')
    ctx = dict(ctx,release=None,snapshot=None)
    if release_id is None or release_id == 'none':
        return ctx
    release = db.execute(select(Release.id,Release.release_type.label('type'),Release.version).where(Release.id == release_id)).mappings().first()
    if release is None:
        raise HTTPException(404,'release not found')
    if not db.scalar(candidates(ctx).with_only_columns(Release.id).where(Release.id == release_id)):
        raise HTTPException(409,'release software/customer/project is outside SCR context')
    ctx['release'] = dict(release)
    s = ReleaseSnapshot
    stmt = select(s.id,s.snapshot_no,s.snapshot_number.label('number')).where(s.release_id == release_id,s.status == 'FROZEN')
    if isinstance(snapshot_id,uuid.UUID):
        stmt = stmt.where(s.id == snapshot_id)
    elif snapshot_no:
        stmt = stmt.where(s.snapshot_no == snapshot_no)
    else:
        stmt = stmt.order_by(s.snapshot_number.desc()).limit(1)
    snapshot = db.execute(stmt).mappings().first()
    if snapshot_id == 'none':
        if snapshot is not None:
            raise HTTPException(409,'frozen snapshot context changed; reset report')
    elif (snapshot_no or isinstance(snapshot_id,uuid.UUID)) and snapshot is None:
        raise HTTPException(409,'snapshot is not a frozen snapshot of the selected release')
    else:
        ctx['snapshot'] = dict(snapshot) if snapshot else None
    return ctx


def pins(ctx):
    return {'change_id':str(ctx['id']),'request_no':ctx['request_no'],
        'release_id':str(ctx['release']['id']) if ctx['release'] else 'none',
        'snapshot_id':str(ctx['snapshot']['id']) if ctx['snapshot'] else 'none'}


def page_context(db, request_no, filters):
    return context(db,request_no,release_id=filters.release_id,snapshot_id=filters.snapshot_id,change_id=filters.change_id)


def own_items(ctx):
    i = DvpItem; p = DvpPlan
    stmt = select(i.id,i.item_no,i.title,i.scope,i.status.label('declared_status'),i.plan_id).join(p,p.id == i.plan_id).where(p.change_request_id == ctx['id'])
    fields = ['execution_no','result','actual_result','executed_at']
    if ctx['snapshot']:
        e = DvpExecution
        ranked = select(e.dvp_item_id,*[getattr(e,k) for k in fields],func.row_number().over(
            partition_by=e.dvp_item_id,order_by=e.execution_no.desc()).label('rank')).join(i,i.id == e.dvp_item_id).join(p,p.id == i.plan_id).where(
            p.change_request_id == ctx['id'],e.release_id == ctx['release']['id'],e.snapshot_id == ctx['snapshot']['id']).subquery()
        latest = select(ranked).where(ranked.c.rank == 1).subquery()
        stmt = stmt.outerjoin(latest,latest.c.dvp_item_id == i.id).add_columns(*[latest.c[k] for k in fields])
    else:
        stmt = stmt.add_columns(*[literal(None).label(k) for k in fields])
    return stmt.cte('coverage_items')


def group_rows(ctx,kind,items):
    m, link, attr, number = {
        'acceptance':(AcceptanceCriterion,AcceptanceDvpLink,'criterion_id','criterion_no'),
        'points':(ChangePoint,ChangePointDvpItem,'change_point_id','change_no'),
        'issues':(Issue,IssueDvpItem,'issue_id','issue_no')}[kind]
    desc = m.description if kind == 'acceptance' else func.coalesce(func.nullif(m.description,''),m.title)
    scope = select(IssueChangeRequestRelation.id).where(IssueChangeRequestRelation.issue_id == m.id,IssueChangeRequestRelation.change_request_id == ctx['id']).exists() if kind == 'issues' else m.change_request_id == ctx['id']
    base = select(m.id,getattr(m,number).label('ref'),desc.label('description')).where(scope).subquery()
    def count(condition=None, foreign=False):
        stmt = select(func.count()).select_from(link).where(getattr(link,attr) == base.c.id)
        if foreign:
            stmt = stmt.where(~select(items.c.id).where(items.c.id == link.dvp_item_id).exists())
        else:
            stmt = stmt.join(items,items.c.id == link.dvp_item_id)
        if condition is not None:stmt = stmt.where(condition)
        return stmt.correlate(base).scalar_subquery()
    valid = count(); excluded = count(foreign=True)
    if not ctx['release']:state = case((valid == 0,'UNASSIGNED'),else_='CONTEXT_REQUIRED')
    elif not ctx['snapshot']:state = case((valid == 0,'UNASSIGNED'),else_='NO_FROZEN_SNAPSHOT')
    else:state = case((valid == 0,'UNASSIGNED'),(count(items.c.result.in_(['FAIL','ERROR','CANCELLED'])) > 0,'FAILED'),(count(items.c.result == 'PASS') == valid,'PASSED'),else_='PENDING')
    return select(base,valid.label('item_count'),excluded.label('excluded_link_count'),state.label('verification')).subquery(kind+'_coverage')


def gap_query(ctx,items,groups):
    code_ref_message = []
    def fixed(code,ref,message,condition):
        code_ref_message.append(select(literal(code).label('code'),literal(ref).label('ref'),literal(message).label('message'),literal('').label('owner_id'),literal('parent').label('kind')).where(condition))
    fixed('REQUIREMENT_MISSING',ctx['request_no'],'No requirement text.',literal(not (ctx['requirement'] or '').strip()))
    for kind,code,msg in [('acceptance','CRITERIA_MISSING','No acceptance criteria.'),('points','CHANGE_POINTS_MISSING','No change points.')]:
        fixed(code,ctx['request_no'],msg,select(func.count()).select_from(groups[kind]).scalar_subquery() == 0)
    fixed('DVP_PLAN_MISSING',ctx['request_no'],'No DVP plan.',select(func.count()).select_from(DvpPlan).where(DvpPlan.change_request_id == ctx['id']).scalar_subquery() == 0)
    fixed('DVP_ITEMS_MISSING',ctx['request_no'],'No DVP items in SCR plans.',select(func.count()).select_from(items).scalar_subquery() == 0)
    if ctx['release'] and not ctx['snapshot']:
        fixed('FROZEN_SNAPSHOT_MISSING',ctx['release']['version'],'No frozen snapshot for selected release.',literal(True))
    from sqlalchemy import String, cast
    for kind,rows in groups.items():
        for code,msg,condition in [('DVP_ASSIGNMENT_MISSING','No DVP assignment within this SCR.',rows.c.item_count == 0),('DVP_OUTSIDE_SCR','Some linked tests belong outside this SCR; excluded from coverage.',rows.c.excluded_link_count > 0)]:
            code_ref_message.append(select(literal(code).label('code'),rows.c.ref,literal(msg).label('message'),cast(rows.c.id,String).label('owner_id'),literal(kind).label('kind')).where(condition))
    rows = groups['acceptance']
    code_ref_message.append(select(literal('CRITERION_DESCRIPTION_MISSING').label('code'),rows.c.ref,literal('Acceptance text is blank.').label('message'),cast(rows.c.id,String).label('owner_id'),literal('acceptance').label('kind')).where(func.trim(rows.c.description,WHITESPACE) == ''))
    return union_all(*code_ref_message).subquery('coverage_gaps')


def aggregate(db,rows,snapshot):
    total,assigned,passed = db.execute(select(func.count(),func.coalesce(func.sum(case((rows.c.item_count > 0,1),else_=0)),0),func.coalesce(func.sum(case((rows.c.verification == 'PASSED',1),else_=0)),0)).select_from(rows)).one()
    return {'total':total,'assigned':assigned,'assignment_percent':round(assigned / total * 100) if total else None,'passed':passed if snapshot else None}


@router.get('/{request_no}/summary')
def summary(request_no: str, filters: Annotated[Selection,Query()], db: Session = Depends(get_db)):
    ctx = context(db,request_no,filters.release_id,filters.snapshot_no,filters.snapshot_id)
    items = own_items(ctx); groups = {kind:group_rows(ctx,kind,items) for kind in ['acceptance','points','issues']}
    totals = {kind:aggregate(db,rows,ctx['snapshot']) for kind,rows in groups.items()}
    total,executed,passed = db.execute(select(func.count(),func.count(items.c.execution_no),func.coalesce(func.sum(case((items.c.result == 'PASS',1),else_=0)),0)).select_from(items)).one()
    return {**pins(ctx),'basis':BASIS,'release':ctx['release'],'snapshot':ctx['snapshot'],
        'candidate_count':db.scalar(select(func.count()).select_from(candidates(ctx).subquery())),
        'gap_count':db.scalar(select(func.count()).select_from(gap_query(ctx,items,groups))),
        'summary':{'acceptance':totals['acceptance'],'change_points':totals['points'],'issues':totals['issues'],
            'dvp':{'total':total,'executed':executed if ctx['snapshot'] else None,'passed':passed if ctx['snapshot'] else None}}}


def serialize(row):
    return {key:str(value) if isinstance(value,uuid.UUID) else value for key,value in row.items()}


def page(db,ctx,filters,stmt,order,**extra):
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).mappings()
    return {**pins(ctx),'total':total,'limit':filters.limit,'offset':filters.offset,
        'next_offset':filters.offset+filters.limit if filters.offset+filters.limit < total else None,
        'items':[serialize(row) for row in rows],**extra}


@router.get('/{request_no}/candidates')
def candidate_page(request_no: str, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters)
    return page(db,ctx,filters,candidates(ctx),[Release.created_at.desc().nullslast(),Release.id.desc()])


@router.get('/{request_no}/gaps')
def gaps_page(request_no: str, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); items = own_items(ctx)
    rows = gap_query(ctx,items,{kind:group_rows(ctx,kind,items) for kind in ['acceptance','points','issues']})
    return page(db,ctx,filters,select(rows),[rows.c.code,rows.c.ref,rows.c.kind,rows.c.owner_id])


@router.get('/{request_no}/groups/{kind}')
def groups_page(request_no: str, kind: Kind, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); rows = group_rows(ctx,kind,own_items(ctx))
    return page(db,ctx,filters,select(rows),[rows.c.ref,rows.c.id],kind=kind)


def selected_group(db,ctx,kind,group_id):
    items = own_items(ctx); rows = group_rows(ctx,kind,items)
    row = db.execute(select(rows).where(rows.c.id == group_id)).mappings().first()
    if row is None:raise HTTPException(404,'coverage group not found for SCR')
    return items,rows,row


@router.get('/{request_no}/groups/{kind}/{group_id}/summary')
def group_summary(request_no: str, kind: Kind, group_id: uuid.UUID, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); _,_,row = selected_group(db,ctx,kind,group_id)
    assignments = db.scalar(select(func.count()).select_from(AcceptanceDvpLink).where(AcceptanceDvpLink.criterion_id == group_id)) if kind == 'acceptance' else 0
    return {**pins(ctx),'kind':kind,'group_id':str(group_id),'assignment_count':assignments,**serialize(row)}


@router.get('/{request_no}/groups/{kind}/{group_id}/items')
def group_items_page(request_no: str, kind: Kind, group_id: uuid.UUID, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); items,_,_ = selected_group(db,ctx,kind,group_id)
    link,attr = {'acceptance':(AcceptanceDvpLink,'criterion_id'),'points':(ChangePointDvpItem,'change_point_id'),'issues':(IssueDvpItem,'issue_id')}[kind]
    stmt = select(items).join(link,link.dvp_item_id == items.c.id).where(getattr(link,attr) == group_id)
    return page(db,ctx,filters,stmt,[items.c.item_no,items.c.id],kind=kind,group_id=str(group_id))


@router.get('/{request_no}/acceptance/{criterion_id}/assignments')
def assignment_page(request_no: str, criterion_id: uuid.UUID, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); selected_group(db,ctx,'acceptance',criterion_id); a = AcceptanceDvpLink
    stmt = select(a.id,a.dvp_item_id,a.actor_name,a.reason,a.created_at).where(a.criterion_id == criterion_id)
    return page(db,ctx,filters,stmt,[a.created_at,a.id],kind='acceptance',group_id=str(criterion_id))


@router.get('/{request_no}/items')
def items_page(request_no: str, filters: Annotated[PageFilters,Query()], db: Session = Depends(get_db)):
    ctx = page_context(db,request_no,filters); items = own_items(ctx)
    return page(db,ctx,filters,select(items),[items.c.item_no,items.c.id])
