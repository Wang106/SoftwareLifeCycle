"""Exact release passport, bounded independent histories and explicit selection pins."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release, ApplicationReleaseDetail, SoftwareProduct, Customer, Project
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ReleaseDecision, ApprovalRequest
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization

router = APIRouter(prefix='/api/v1/releases/application/id', tags=['application passport'])
Pin = uuid.UUID | Literal['none']

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: Pin | None = None
    decision_id: Pin | None = None

    @model_validator(mode='after')
    def paired(self):
        if (self.snapshot_id is None) != (self.decision_id is None):
            raise ValueError('snapshot_id and decision_id must be supplied together')
        return self

class Page(Selection):
    snapshot_id: Pin
    decision_id: Pin
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def selection(db, release_id, filters):
    release = db.get(Release, release_id)
    if release is None or release.release_type != 'APPLICATION':
        raise HTTPException(404, 'application release not found')
    def resolve(model, pin, order):
        if pin == 'none':
            return None
        if pin is not None:
            row = db.get(model, pin)
            if row is None or row.release_id != release_id:
                raise HTTPException(404, 'selection not found for application release')
            return row
        return db.scalar(select(model).where(model.release_id == release_id).order_by(*order).limit(1))
    snapshot = resolve(ReleaseSnapshot, filters.snapshot_id, [ReleaseSnapshot.snapshot_number.desc(), ReleaseSnapshot.id.desc()])
    decision = resolve(ReleaseDecision, filters.decision_id, [ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc(), ReleaseDecision.id.desc()])
    return release, snapshot, decision


def pins(snapshot, decision):
    return {'snapshot_id': str(snapshot.id) if snapshot else 'none', 'decision_id': str(decision.id) if decision else 'none'}


def count(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))


def decision_rows(release_id):
    d, s, a = ReleaseDecision, ReleaseSnapshot, ApprovalRequest
    return select(d, s, a).outerjoin(s, and_(s.id == d.snapshot_id, s.release_id == d.release_id)).outerjoin(a,
        and_(a.id == d.approval_request_id, a.target_type == 'RELEASE', a.target_id == d.release_id, a.snapshot_id == d.snapshot_id)).where(d.release_id == release_id)


def decision_row(d, s, a, selected_id):
    return {'id': str(d.id), 'decision_no': d.decision_no, 'decision': d.decision,
        'readiness_status': d.readiness_status, 'decided_by': d.decided_by, 'decision_notes': d.decision_notes,
        'decided_at': d.decided_at, 'snapshot_id': str(d.snapshot_id), 'snapshot_no': s.snapshot_no if s else None,
        'snapshot_content_hash': s.content_hash if s else None, 'is_selected_snapshot': d.snapshot_id == selected_id,
        'context_consistent': bool(s and s.status == 'FROZEN' and a),
        'approval_no': a.approval_no if a else None, 'approval_status': a.status if a else None}


def statements(release_id, decision):
    p, s, d, a = DeliveryPackage, ReleaseSnapshot, Distribution, SoftwareAuthorization
    deliveries = select(p, s.snapshot_no).outerjoin(s, and_(s.id == p.snapshot_id, s.release_id == p.release_id)).where(p.release_id == release_id)
    if decision is not None:
        deliveries = deliveries.where(p.snapshot_id == decision.snapshot_id)
    return {'decisions': decision_rows(release_id), 'deliveries': deliveries,
        'distributions': select(d, p.package_no, p.revision).join(p, p.id == d.delivery_package_id).where(p.release_id == release_id),
        'authorizations': select(a, s.snapshot_no, d.distribution_no).outerjoin(s, and_(s.id == a.snapshot_id, s.release_id == a.release_id))
            .outerjoin(d, d.id == a.distribution_id).where(a.release_id == release_id)}


@router.get('/{release_id}/passport/summary')
def summary(release_id: uuid.UUID, filters: Annotated[Selection, Query()], db: Session = Depends(get_db)):
    release, snapshot, decision = selection(db, release_id, filters)
    latest_snapshot = db.scalar(select(ReleaseSnapshot.id).where(ReleaseSnapshot.release_id == release_id)
        .order_by(ReleaseSnapshot.snapshot_number.desc(), ReleaseSnapshot.id.desc()).limit(1))
    latest_decision = db.scalar(select(ReleaseDecision.id).where(ReleaseDecision.release_id == release_id)
        .order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc(), ReleaseDecision.id.desc()).limit(1))
    detail = db.get(ApplicationReleaseDetail, release_id)
    software = db.get(SoftwareProduct, release.software_id)
    customer = db.get(Customer, detail.customer_id) if detail else None
    project = db.get(Project, detail.project_id) if detail else None
    base = db.get(Release, detail.standard_base_release_id) if detail else None
    row = None
    if decision:
        d, s, a = db.execute(decision_rows(release_id).where(ReleaseDecision.id == decision.id)).one()
        row = decision_row(d, s, a, snapshot.id if snapshot else None)
        row['is_latest_decision'] = decision.id == latest_decision
        row['is_current_snapshot'] = bool(snapshot and snapshot.id == latest_snapshot and d.snapshot_id == snapshot.id)
    return {'release_id': str(release_id), 'selection': pins(snapshot, decision),
        'profile': {'id': str(release.id), 'version': release.version, 'status': release.status, 'release_notes': release.release_notes,
            'software': {'code': software.code, 'name': software.name} if software else None,
            'customer': {'code': customer.code, 'name': customer.name} if customer else None,
            'project': {'id': str(project.id), 'code': project.project_code, 'name': project.name} if project else None,
            'base_release': {'id': str(base.id), 'version': base.version, 'status': base.status} if base else None,
            'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no, 'status': snapshot.status,
                'content_hash': snapshot.content_hash, 'is_current_snapshot': snapshot.id == latest_snapshot} if snapshot else None},
        'decision': row, 'delivery_scope_snapshot_id': str(decision.snapshot_id) if decision else None,
        'counts': {kind: count(db, stmt) for kind, stmt in statements(release_id, decision).items()}}


def history(release_id, filters, db, kind):
    _, snapshot, decision = selection(db, release_id, filters)
    stmt = statements(release_id, decision)[kind]
    total = count(db, stmt)
    orders = {'decisions': [ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc(), ReleaseDecision.id.desc()],
        'deliveries': [DeliveryPackage.package_no, DeliveryPackage.revision, DeliveryPackage.id],
        'distributions': [Distribution.distribution_no, Distribution.id],
        'authorizations': [SoftwareAuthorization.authorization_no, SoftwareAuthorization.id]}
    items = []
    for row in db.execute(stmt.order_by(*orders[kind]).limit(filters.limit).offset(filters.offset)):
        if kind == 'decisions':
            items.append(decision_row(*row, snapshot.id if snapshot else None))
        elif kind == 'deliveries':
            p, number = row
            items.append({'id': str(p.id), 'package_no': p.package_no, 'revision': p.revision, 'status': p.status,
                'snapshot_id': str(p.snapshot_id), 'snapshot_no': number, 'recipient_code': p.recipient_code})
        elif kind == 'distributions':
            d, package, revision = row
            items.append({'id': str(d.id), 'distribution_no': d.distribution_no, 'status': d.status,
                'package_no': package, 'package_revision': revision, 'recipient_code': d.recipient_code})
        else:
            a, number, distribution = row
            items.append({'id': str(a.id), 'authorization_no': a.authorization_no, 'status': a.status,
                'snapshot_id': str(a.snapshot_id), 'snapshot_no': number, 'distribution_no': distribution,
                'site_code': a.site_code, 'line_code': a.line_code})
    return {'release_id': str(release_id), **pins(snapshot, decision), 'total': total, 'limit': filters.limit,
        'offset': filters.offset, 'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'delivery_scope_snapshot_id': str(decision.snapshot_id) if decision else None, 'items': items}

@router.get('/{release_id}/passport/decisions')
def decisions(release_id: uuid.UUID, filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    return history(release_id, filters, db, 'decisions')

@router.get('/{release_id}/passport/deliveries')
def deliveries(release_id: uuid.UUID, filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    return history(release_id, filters, db, 'deliveries')

@router.get('/{release_id}/passport/distributions')
def distributions(release_id: uuid.UUID, filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    return history(release_id, filters, db, 'distributions')

@router.get('/{release_id}/passport/authorizations')
def authorizations(release_id: uuid.UUID, filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    return history(release_id, filters, db, 'authorizations')
