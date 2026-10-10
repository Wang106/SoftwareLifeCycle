"""Current SCR assignments with exact release/snapshot execution evidence.

This report does not assert incorporation into a release or alter readiness gates.
"""
import uuid
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import or_, select
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.acceptance import AcceptanceDvpLink
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, DvpPlan, IssueDvpItem
from app.services.audit import AuditEventService
from app.actor import ActorContext, audit_actor_matches, idempotent_actor_matches
from app.services.acceptance_history import effective


class CoverageError(ValueError):
    def __init__(self, detail, status_code=409):
        super().__init__(detail)
        self.status_code = status_code


def get_change(db, request_no, lock=False):
    stmt = select(SoftwareChangeRequest).where(SoftwareChangeRequest.request_no == request_no)
    row = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if row is None:
        raise CoverageError('change request not found', 404)
    return row


def candidate_query(change):
    stmt = select(Release).outerjoin(ApplicationReleaseDetail, ApplicationReleaseDetail.release_id == Release.id)
    stmt = stmt.where(Release.software_id == change.software_id)
    if change.project_id:
        stmt = stmt.where(or_(Release.release_type == 'STANDARD', ApplicationReleaseDetail.project_id == change.project_id))
    if change.customer_id:
        stmt = stmt.where(or_(Release.release_type == 'STANDARD', ApplicationReleaseDetail.customer_id == change.customer_id))
    return stmt


def report_coverage(db, request_no, release_id=None, snapshot_no=None):
    change = get_change(db, request_no)
    if snapshot_no and release_id is None:
        raise CoverageError('snapshot_no requires release_id', 422)
    candidates = db.scalars(candidate_query(change).order_by(Release.created_at.desc(), Release.id.desc()).limit(101)).all()
    release = None
    snapshot = None
    if release_id:
        release = db.get(Release, release_id)
        if release is None:
            raise CoverageError('release not found', 404)
        if db.scalars(candidate_query(change).where(Release.id == release_id)).first() is None:
            raise CoverageError('release software/customer/project is outside SCR context')
        stmt = select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release_id, ReleaseSnapshot.status == 'FROZEN')
        if snapshot_no:
            snapshot = db.scalars(stmt.where(ReleaseSnapshot.snapshot_no == snapshot_no)).first()
            if snapshot is None:
                raise CoverageError('snapshot is not a frozen snapshot of the selected release')
        else:
            snapshot = db.scalars(stmt.order_by(ReleaseSnapshot.snapshot_number.desc())).first()
    criteria = db.scalars(select(AcceptanceCriterion).where(AcceptanceCriterion.change_request_id == change.id)
        .order_by(AcceptanceCriterion.criterion_no, AcceptanceCriterion.id)).all()
    points = db.scalars(select(ChangePoint).where(ChangePoint.change_request_id == change.id)
        .order_by(ChangePoint.change_no, ChangePoint.id)).all()
    issues = db.scalars(select(Issue).join(IssueChangeRequestRelation, IssueChangeRequestRelation.issue_id == Issue.id)
        .where(IssueChangeRequestRelation.change_request_id == change.id).distinct().order_by(Issue.issue_no)).all()
    plans = db.scalars(select(DvpPlan).where(DvpPlan.change_request_id == change.id).order_by(DvpPlan.plan_no)).all()
    items = db.scalars(select(DvpItem).where(DvpItem.plan_id.in_([p.id for p in plans]))
        .order_by(DvpItem.item_no, DvpItem.id)).all() if plans else []
    own_items = {i.id: i for i in items}
    ac_links = db.scalars(select(AcceptanceDvpLink).where(AcceptanceDvpLink.criterion_id.in_([c.id for c in criteria]), effective())).all() if criteria else []
    cp_links = db.scalars(select(ChangePointDvpItem).where(ChangePointDvpItem.change_point_id.in_([p.id for p in points]))).all() if points else []
    issue_links = db.scalars(select(IssueDvpItem).where(IssueDvpItem.issue_id.in_([i.id for i in issues]))).all() if issues else []
    latest = {}
    if snapshot and own_items:
        executions = db.scalars(select(DvpExecution).where(DvpExecution.dvp_item_id.in_(own_items),
            DvpExecution.release_id == release.id, DvpExecution.snapshot_id == snapshot.id)
            .order_by(DvpExecution.execution_no.desc())).all()
        for execution in executions:
            latest.setdefault(execution.dvp_item_id, execution)
    gaps = []
    for present, code, message in [(bool((change.requirement or '').strip()), 'REQUIREMENT_MISSING', 'No requirement text.'),
        (bool(criteria), 'CRITERIA_MISSING', 'No acceptance criteria.'),
        (bool(points), 'CHANGE_POINTS_MISSING', 'No change points.'),
        (bool(plans), 'DVP_PLAN_MISSING', 'No DVP plan.'),
        (bool(items), 'DVP_ITEMS_MISSING', 'No DVP items in SCR plans.')]:
        if not present:
            gaps.append({'code': code, 'ref': change.request_no, 'message': message})
    if release and not snapshot:
        gaps.append({'code': 'FROZEN_SNAPSHOT_MISSING', 'ref': release.version, 'message': 'No frozen snapshot for selected release.'})

    def test_item(item):
        execution = latest.get(item.id)
        return {'id': str(item.id), 'item_no': item.item_no, 'title': item.title, 'scope': item.scope,
            'declared_status': item.status, 'execution': {'execution_no': execution.execution_no,
                'result': execution.result, 'actual_result': execution.actual_result, 'executed_at': execution.executed_at}
            if execution else None}

    def group(rows, links, attr, ref_attr):
        output = []
        for row in rows:
            linked_ids = {getattr(link, 'dvp_item_id') for link in links if getattr(link, attr) == row.id}
            valid_ids = linked_ids & own_items.keys()
            foreign = linked_ids - own_items.keys()
            if not valid_ids:
                gaps.append({'code': 'DVP_ASSIGNMENT_MISSING', 'ref': getattr(row, ref_attr), 'message': 'No DVP assignment within this SCR.'})
            if foreign:
                gaps.append({'code': 'DVP_OUTSIDE_SCR', 'ref': getattr(row, ref_attr), 'message': 'Some linked tests belong outside this SCR; excluded from coverage.'})
            if not valid_ids:
                state = 'UNASSIGNED'
            elif not release:
                state = 'CONTEXT_REQUIRED'
            elif not snapshot:
                state = 'NO_FROZEN_SNAPSHOT'
            elif any(latest.get(i) and latest[i].result in {'FAIL', 'ERROR', 'CANCELLED'} for i in valid_ids):
                state = 'FAILED'
            elif all(latest.get(i) and latest[i].result == 'PASS' for i in valid_ids):
                state = 'PASSED'
            else:
                state = 'PENDING'
            output.append({'id': str(row.id), 'ref': getattr(row, ref_attr),
                'description': getattr(row, 'description', None) or getattr(row, 'title', ''),
                'verification': state, 'excluded_link_count': len(foreign),
                'assignments': [{'id': str(link.id), 'dvp_item_id': str(link.dvp_item_id), 'actor_name': link.actor_name,
                    'reason': link.reason, 'created_at': link.created_at} for link in links
                    if attr == 'criterion_id' and getattr(link, attr) == row.id],
                'dvp_items': [test_item(own_items[i]) for i in sorted(valid_ids, key=lambda i: (own_items[i].item_no, str(i)))]})
        return output
    acceptance = group(criteria, ac_links, 'criterion_id', 'criterion_no')
    changes = group(points, cp_links, 'change_point_id', 'change_no')
    linked_issues = group(issues, issue_links, 'issue_id', 'issue_no')
    for criterion in criteria:
        if not criterion.description.strip():
            gaps.append({'code': 'CRITERION_DESCRIPTION_MISSING', 'ref': criterion.criterion_no, 'message': 'Acceptance text is blank.'})
    def summary(rows):
        assigned = sum(bool(r['dvp_items']) for r in rows)
        return {'total': len(rows), 'assigned': assigned,
            'assignment_percent': round(assigned / len(rows) * 100) if rows else None,
            'passed': sum(r['verification'] == 'PASSED' for r in rows) if snapshot else None}
    return {'request_no': change.request_no,
        'basis': 'Current SCR definitions and assignments; candidate releases are software/customer/project matches, not proof of change incorporation. Historical snapshots do not freeze these assignments.',
        'release': {'id': str(release.id), 'type': release.release_type, 'version': release.version} if release else None,
        'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no, 'number': snapshot.snapshot_number} if snapshot else None,
        'candidate_releases': [{'id': str(r.id), 'type': r.release_type, 'version': r.version, 'status': r.status} for r in candidates[:100]],
        'candidates_truncated': len(candidates) > 100, 'gaps': gaps,
        'summary': {'acceptance': summary(acceptance), 'change_points': summary(changes), 'issues': summary(linked_issues),
            'dvp': {'total': len(items), 'executed': len(latest) if snapshot else None,
                'passed': sum(e.result == 'PASS' for e in latest.values()) if snapshot else None}},
        'acceptance_criteria': acceptance, 'change_points': changes, 'issues': linked_issues,
        'dvp_items': [test_item(i) for i in items]}


class AssignmentInput(BaseModel):
    request_id: uuid.UUID
    criterion_id: uuid.UUID
    dvp_item_id: uuid.UUID
    action: Literal['ASSIGN', 'SUPERSEDE', 'WITHDRAW'] = 'ASSIGN'
    supersedes_id: uuid.UUID | None = None
    actor_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('actor_name', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value.strip()

    @model_validator(mode='after')
    def history_pair(self):
        if (self.action == 'ASSIGN') != (self.supersedes_id is None):
            raise ValueError('replacement/withdrawal requires supersedes_id; assignment must omit it')
        return self


def correction_payload(data, predecessor, actor):
    return {'assignment_id': str(data.request_id), 'criterion_id': str(data.criterion_id),
        'dvp_item_id': str(data.dvp_item_id), 'supersedes_id': str(data.supersedes_id),
        'previous_dvp_item_id': str(predecessor.dvp_item_id), 'previous_action': predecessor.action,
        'actor_source': actor.source}


def record_assignment(db, request_no, data, actor_context: ActorContext | None = None):
    resolved_actor = actor_context or ActorContext.legacy(data.actor_name)
    change = get_change(db, request_no, lock=True)
    existing = db.get(AcceptanceDvpLink, data.request_id)
    if existing:
        criterion = db.get(AcceptanceCriterion, existing.criterion_id)
        event = db.scalars(select(AuditEvent).where(
            AuditEvent.event_no == f'EVT-AC-{data.request_id}'
        )).first()
        if (criterion is None or criterion.change_request_id != change.id
            or any(getattr(existing, field) != getattr(data, field)
                for field in ('criterion_id', 'dvp_item_id', 'reason', 'action', 'supersedes_id'))
            or existing.actor_name != resolved_actor.name
            or not idempotent_actor_matches(event, resolved_actor)):
            raise CoverageError('request_id already used for different content')
        if data.action != 'ASSIGN':
            predecessor = db.get(AcceptanceDvpLink, data.supersedes_id)
            if (predecessor is None or event is None or not audit_actor_matches(event, resolved_actor)
                or event.event_type != 'ACCEPTANCE_DVP' or event.action != data.action
                or event.entity_type != 'SoftwareChangeRequest' or event.entity_id != change.id
                or event.entity_ref != change.request_no or event.detail != data.reason
                or event.payload_json != correction_payload(data, predecessor, resolved_actor)):
                raise CoverageError('request_id correction audit does not match original operation')
        return existing, False
    criterion = db.get(AcceptanceCriterion, data.criterion_id)
    item = db.get(DvpItem, data.dvp_item_id)
    plan = db.get(DvpPlan, item.plan_id) if item else None
    if not criterion or not item:
        raise CoverageError('criterion or DVP item not found', 404)
    if criterion.change_request_id != change.id or not plan or plan.change_request_id != change.id:
        raise CoverageError('criterion and DVP item must belong to this SCR')
    predecessor = None
    if data.action != 'ASSIGN':
        predecessor = db.scalar(select(AcceptanceDvpLink).where(AcceptanceDvpLink.id == data.supersedes_id,
            AcceptanceDvpLink.criterion_id == criterion.id, effective()))
        if data.supersedes_id == data.request_id or predecessor is None:
            raise CoverageError('supersedes_id must identify a current effective relationship of this criterion')
        if (data.action == 'WITHDRAW') != (data.dvp_item_id == predecessor.dvp_item_id):
            raise CoverageError('withdrawal must retain original DVP; replacement must select a different DVP')
    if data.action != 'WITHDRAW' and db.scalars(select(AcceptanceDvpLink).where(AcceptanceDvpLink.criterion_id == criterion.id,
        AcceptanceDvpLink.dvp_item_id == item.id, effective())).first():
        raise CoverageError('criterion/test pair already assigned; retry with its original request_id')
    row = AcceptanceDvpLink(id=data.request_id, criterion_id=data.criterion_id, dvp_item_id=data.dvp_item_id,
        actor_name=resolved_actor.name, reason=data.reason, action=data.action, supersedes_id=data.supersedes_id)
    db.add(row); db.flush()
    payload = correction_payload(data, predecessor, resolved_actor) if predecessor else {
        'assignment_id': str(row.id), 'criterion_id': str(criterion.id),
        'dvp_item_id': str(item.id), 'actor_source': resolved_actor.source}
    AuditEventService(db).record(event_no=f'EVT-AC-{data.request_id}', event_type='ACCEPTANCE_DVP', action=data.action,
        entity_type='SoftwareChangeRequest', entity_id=change.id, entity_ref=change.request_no,
        **resolved_actor.audit_fields(),
        summary=f'{change.request_no}: {criterion.criterion_no} → {item.item_no}'[:240],
        detail=data.reason, payload=payload)
    return row, True
