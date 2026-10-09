"""Bounded Issue relations, review candidates, judgments and exact frozen evidence."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.production import Deployment, ProductionBatch
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.impact import IssueImpactAssessment
from app.services.impact_history import effective, successor_id
from app.models.testing import IssueDvpItem, DvpItem, DvpExecution

router = APIRouter(prefix='/api/v1/issue-views', tags=['issue views'])

class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Pages(Empty):
    issue_id: uuid.UUID
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)

class SnapshotSelection(Empty):
    snapshot_id: uuid.UUID | Literal['none'] | None = None

class EvidencePages(Pages):
    snapshot_id: uuid.UUID | Literal['none']


def issue(db,number,identifier=None):
    i = Issue
    row = db.execute(select(i.id,i.issue_no,i.title,i.scope,i.severity,i.status,i.description).where(i.issue_no == number)).mappings().first()
    if row is None or (identifier is not None and row['id'] != identifier):
        raise HTTPException(404,'issue identity not found')
    return row


def membership(identifier,software_id):
    return select(IssueChangeRequestRelation.id).join(SoftwareChangeRequest,
        SoftwareChangeRequest.id == IssueChangeRequestRelation.change_request_id).where(
        IssueChangeRequestRelation.issue_id == identifier,SoftwareChangeRequest.software_id == software_id).exists()


def relations(identifier):
    r = IssueChangeRequestRelation; c = SoftwareChangeRequest
    return select(r.id.label('relation_id'),c.id.label('id'),c.request_no,c.title,c.status,r.relation_type).join(c,c.id == r.change_request_id).where(r.issue_id == identifier)


def candidates(identifier):
    r = Release; s = SoftwareProduct; a = ApplicationReleaseDetail; f = ReleaseSnapshot; j = IssueImpactAssessment
    frozen = select(f.id).where(f.release_id == r.id,f.status == 'FROZEN').order_by(f.snapshot_number.desc()).limit(1).correlate(r).scalar_subquery()
    judgment = select(j.id).where(j.issue_id == identifier,j.release_id == r.id,j.snapshot_id == f.id,effective()).order_by(j.created_at.desc(),j.id.desc()).limit(1).correlate(r,f).scalar_subquery()
    deployment_count = select(func.count()).select_from(Deployment).where(Deployment.actual_release_id == r.id).correlate(r).scalar_subquery()
    batch_count = select(func.count()).select_from(ProductionBatch).where(ProductionBatch.release_id == r.id).correlate(r).scalar_subquery()
    # Legacy directory displays only releases with real product metadata. Candidate
    # scope is software membership, deliberately not SCR customer/project ownership.
    return select(r.id,r.release_type,r.version,r.status,r.created_at,s.code.label('software_code'),s.name.label('software_name'),
        Customer.code.label('customer_code'),Customer.name.label('customer'),a.project_id,Project.name.label('project'),
        f.id.label('snapshot_id'),f.snapshot_no,j.id.label('assessment_id'),j.decision,
        deployment_count.label('deployment_count'),batch_count.label('batch_count')).join(s,s.id == r.software_id).outerjoin(a,a.release_id == r.id).outerjoin(Customer,Customer.id == a.customer_id).outerjoin(Project,Project.id == a.project_id).outerjoin(f,f.id == frozen).outerjoin(j,j.id == judgment).where(membership(identifier,r.software_id))


def serialize(row):
    return {key:str(value) if isinstance(value,uuid.UUID) else value for key,value in row.items()}


def count(db,stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


def pins(row):
    return {'issue_id':str(row['id']),'issue_no':row['issue_no']}


def page(db,row,filters,stmt,order,**extra):
    total = count(db,stmt)
    rows = db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).mappings()
    return {**pins(row),'total':total,'limit':filters.limit,'offset':filters.offset,
        'next_offset':filters.offset+filters.limit if filters.offset+filters.limit < total else None,
        'items':[serialize(value) for value in rows],**extra}


@router.get('/{issue_no}/summary')
def summary(issue_no: str, filters: Annotated[Empty,Query()], db: Session = Depends(get_db)):
    row = issue(db,issue_no)
    linked = count(db,relations(row['id']))
    return {**serialize(row),'linked_count':linked,'candidate_count':count(db,candidates(row['id'])),
        'assessment_count':db.scalar(select(func.count()).select_from(IssueImpactAssessment).where(IssueImpactAssessment.issue_id == row['id'])),
        'basis':'Candidate releases share a software product with a linked SCR. Actual issue impact requires review.' if linked else 'No linked SCR; release impact cannot be inferred.'}


@router.get('/{issue_no}/changes')
def changes_page(issue_no: str, filters: Annotated[Pages,Query()], db: Session = Depends(get_db)):
    row = issue(db,issue_no,filters.issue_id)
    return page(db,row,filters,relations(row['id']),[SoftwareChangeRequest.request_no,IssueChangeRequestRelation.relation_type,IssueChangeRequestRelation.id])


@router.get('/{issue_no}/candidates')
def candidates_page(issue_no: str, filters: Annotated[Pages,Query()], db: Session = Depends(get_db)):
    row = issue(db,issue_no,filters.issue_id)
    return page(db,row,filters,candidates(row['id']),[Release.created_at.desc().nullslast(),Release.id.desc()])


def judgments(identifier):
    j = IssueImpactAssessment; s = ReleaseSnapshot; r = Release
    return select(j.id,j.release_id,j.snapshot_id,j.decision,j.reason,j.evidence_ref,j.actor_name,j.created_at,
        j.supersedes_id,j.correction_reason,successor_id().label('superseded_by_id'),
        r.version.label('release_version'),r.release_type,s.snapshot_no).outerjoin(r,r.id == j.release_id).outerjoin(s,s.id == j.snapshot_id).where(j.issue_id == identifier)


@router.get('/{issue_no}/assessments')
def assessments_page(issue_no: str, filters: Annotated[Pages,Query()], db: Session = Depends(get_db)):
    row = issue(db,issue_no,filters.issue_id)
    return page(db,row,filters,judgments(row['id']),[IssueImpactAssessment.created_at.desc(),IssueImpactAssessment.id.desc()])


def evidence_context(db,number,release_id,snapshot_id=None,issue_id=None):
    row = issue(db,number,issue_id); r = Release; s = ReleaseSnapshot
    release = db.execute(select(r.id,r.release_type.label('type'),r.version,r.software_id).where(r.id == release_id)).mappings().first()
    if release is None:raise HTTPException(404,'release not found')
    if not db.scalar(select(membership(row['id'],release['software_id']))):
        raise HTTPException(409,'release is not a candidate from linked SCR software')
    stmt = select(s.id,s.snapshot_no,s.status,s.snapshot_number.label('number'),s.content_hash).where(s.release_id == release_id,s.status == 'FROZEN')
    if isinstance(snapshot_id,uuid.UUID):stmt = stmt.where(s.id == snapshot_id)
    else:stmt = stmt.order_by(s.snapshot_number.desc()).limit(1)
    snapshot = db.execute(stmt).mappings().first()
    if snapshot_id == 'none':
        if snapshot:raise HTTPException(409,'frozen snapshot context changed; reset impact review')
    elif isinstance(snapshot_id,uuid.UUID) and snapshot is None:
        raise HTTPException(409,'snapshot is not frozen for selected release')
    return row,serialize(release),serialize(snapshot) if snapshot else None


def components(snapshot):
    a = SnapshotArtifact
    return select(a.component_code.label('code'),func.coalesce(a.component_version,'').label('version')).where(a.snapshot_id == (uuid.UUID(snapshot['id']) if snapshot else None)).distinct()


def verification(identifier,release_id,snapshot):
    i = DvpItem; e = DvpExecution
    linked = select(IssueDvpItem.issue_id).where(IssueDvpItem.issue_id == identifier,IssueDvpItem.dvp_item_id == i.id).exists()
    stmt = select(i.id,i.item_no,i.title).where(linked)
    fields = ['execution_no','result','actual_result','executed_at']
    if snapshot:
        rank = select(e.dvp_item_id,*[getattr(e,k) for k in fields],func.row_number().over(partition_by=e.dvp_item_id,order_by=e.execution_no.desc()).label('rank')).join(i,i.id == e.dvp_item_id).where(linked,e.release_id == release_id,e.snapshot_id == uuid.UUID(snapshot['id'])).subquery()
        latest = select(rank).where(rank.c.rank == 1).subquery()
        stmt = stmt.outerjoin(latest,latest.c.dvp_item_id == i.id).add_columns(*[latest.c[k] for k in fields])
    else:stmt = stmt.add_columns(*[literal(None).label(k) for k in fields])
    return stmt


def evidence_pins(release_id,snapshot):
    return {'release_id':str(release_id),'snapshot_id':snapshot['id'] if snapshot else 'none'}


@router.get('/{issue_no}/impact/{release_id}/summary')
def evidence_summary(issue_no: str, release_id: uuid.UUID, filters: Annotated[SnapshotSelection,Query()], db: Session = Depends(get_db)):
    row,release,snapshot = evidence_context(db,issue_no,release_id,filters.snapshot_id)
    assessment = None
    if snapshot:
        j = IssueImpactAssessment
        assessment = db.execute(judgments(row['id']).where(j.release_id == release_id,j.snapshot_id == uuid.UUID(snapshot['id']),effective()).order_by(j.created_at.desc(),j.id.desc()).limit(1)).mappings().first()
    return {**pins(row),**evidence_pins(release_id,snapshot),'release':{k:release[k] for k in ['id','type','version']},'snapshot':snapshot,
        'assessment':serialize(assessment) if assessment else None,'component_count':count(db,components(snapshot)),
        'verification_count':count(db,verification(row['id'],release_id,snapshot))}


@router.get('/{issue_no}/impact/{release_id}/components')
def components_page(issue_no: str, release_id: uuid.UUID, filters: Annotated[EvidencePages,Query()], db: Session = Depends(get_db)):
    row,_,snapshot = evidence_context(db,issue_no,release_id,filters.snapshot_id,filters.issue_id)
    rows = components(snapshot).subquery()
    return page(db,row,filters,select(rows),[rows.c.code,rows.c.version],**evidence_pins(release_id,snapshot))


@router.get('/{issue_no}/impact/{release_id}/verification')
def verification_page(issue_no: str, release_id: uuid.UUID, filters: Annotated[EvidencePages,Query()], db: Session = Depends(get_db)):
    row,_,snapshot = evidence_context(db,issue_no,release_id,filters.snapshot_id,filters.issue_id)
    return page(db,row,filters,verification(row['id'],release_id,snapshot),[DvpItem.item_no,DvpItem.id],**evidence_pins(release_id,snapshot))
