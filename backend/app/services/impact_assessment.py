"""Atomic, idempotent writer; transaction ownership stays with the route."""
import uuid
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.impact import IssueImpactAssessment
from app.models.audit import AuditEvent
from app.actor import ActorContext, audit_actor_matches, idempotent_actor_matches
from app.services.audit import AuditEventService
from app.services.impact_history import effective


class AssessmentInput(BaseModel):
    request_id: uuid.UUID
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    decision: Literal['AFFECTED', 'NOT_AFFECTED', 'NEEDS_REVIEW']
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ref: str | None = Field(default=None, max_length=2000)
    actor_name: str = Field(min_length=1, max_length=120)
    supersedes_id: uuid.UUID | None = None
    correction_reason: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode='after')
    def correction_pair(self):
        if (self.supersedes_id is None) != (self.correction_reason is None):
            raise ValueError('supersedes_id and correction_reason must be supplied together')
        if self.correction_reason is not None:
            if not self.correction_reason.strip():
                raise ValueError('correction_reason must not be blank')
            self.correction_reason = self.correction_reason.strip()
        return self

    @field_validator('reason', 'actor_name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value.strip()

    @field_validator('evidence_ref')
    @classmethod
    def clean_reference(cls, value):
        return (value.strip() or None) if value is not None else None


class AssessmentError(ValueError):
    pass


def evidence_reference_digest(reference: str | None) -> str:
    """Version-1 normalized nullable reference digest; no reference in activity payload."""
    encoded = json.dumps(reference, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def record_assessment(
    db: Session,
    issue_no: str,
    data: AssessmentInput,
    actor_context: ActorContext | None = None,
):
    resolved_actor = actor_context or ActorContext.legacy(data.actor_name)
    # Serializes issue review writes, including concurrent retries.
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no).with_for_update()).first()
    if issue is None:
        raise AssessmentError('issue not found')
    existing = db.get(IssueImpactAssessment, data.request_id)
    fields = ('release_id', 'snapshot_id', 'decision', 'reason', 'evidence_ref', 'supersedes_id', 'correction_reason')
    if existing:
        event = db.scalars(select(AuditEvent).where(
            AuditEvent.event_no == f'EVT-IMPACT-{data.request_id}'
        )).first()
        previous = db.get(IssueImpactAssessment, data.supersedes_id) if data.supersedes_id else None
        correction_audit_matches = data.supersedes_id is None or (
            event is not None and previous is not None and isinstance(event.payload_json, dict)
            and audit_actor_matches(event, resolved_actor)
            and event.action == 'SUPERSEDE' and event.event_type == 'ISSUE_IMPACT'
            and event.entity_type == 'Issue' and event.entity_id == issue.id and event.entity_ref == issue.issue_no
            and event.detail == data.reason
            and all(event.payload_json.get(key) == value for key, value in {
                'assessment_id': str(existing.id), 'release_id': str(data.release_id), 'snapshot_id': str(data.snapshot_id),
                'supersedes_id': str(data.supersedes_id), 'previous_decision': previous.decision,
                'correction_reason': data.correction_reason, 'decision': data.decision,
                'evidence_ref_digest_version': 1, 'evidence_ref_sha256': evidence_reference_digest(data.evidence_ref),
                'actor_source': resolved_actor.source}.items()))
        if (existing.issue_id != issue.id
            or any(getattr(existing, field) != getattr(data, field) for field in fields)
            or existing.actor_name != resolved_actor.name
            or not idempotent_actor_matches(event, resolved_actor)
            or not correction_audit_matches):
            raise AssessmentError('request_id already used for a different assessment')
        return existing, False
    release = db.get(Release, data.release_id)
    snapshot = db.get(ReleaseSnapshot, data.snapshot_id)
    if not release or not snapshot:
        raise AssessmentError('release or snapshot not found')
    if snapshot.release_id != release.id or snapshot.status != 'FROZEN':
        raise AssessmentError('assessment requires a matching frozen snapshot')
    software_ids = set(db.scalars(select(SoftwareChangeRequest.software_id)
        .join(IssueChangeRequestRelation, IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id)
        .where(IssueChangeRequestRelation.issue_id == issue.id)).all())
    if release.software_id not in software_ids:
        raise AssessmentError('release is not a candidate from linked SCR software')
    previous = None
    if data.supersedes_id is not None:
        previous = db.get(IssueImpactAssessment, data.supersedes_id)
        if (previous is None or previous.id == data.request_id or previous.issue_id != issue.id
            or previous.release_id != data.release_id or previous.snapshot_id != data.snapshot_id):
            raise AssessmentError('correction predecessor must match the issue, release and frozen snapshot')
        current = db.scalar(select(IssueImpactAssessment.id).where(
            IssueImpactAssessment.issue_id == issue.id, IssueImpactAssessment.release_id == data.release_id,
            IssueImpactAssessment.snapshot_id == data.snapshot_id, effective())
            .order_by(IssueImpactAssessment.created_at.desc(), IssueImpactAssessment.id.desc()).limit(1))
        if current != previous.id:
            raise AssessmentError('correction predecessor is not the current effective judgment')
    assessment = IssueImpactAssessment(id=data.request_id, issue_id=issue.id,
        actor_name=resolved_actor.name, **{field: getattr(data, field) for field in fields})
    db.add(assessment)
    db.flush()
    AuditEventService(db).record(event_no=f'EVT-IMPACT-{data.request_id}', event_type='ISSUE_IMPACT',
        action='SUPERSEDE' if previous else 'ASSESS', entity_type='Issue', entity_id=issue.id, entity_ref=issue.issue_no,
        **resolved_actor.audit_fields(),
        summary=f'{issue.issue_no}: {release.version} / {snapshot.snapshot_no} → {data.decision}'[:240],
        detail=data.reason, payload={'assessment_id': str(assessment.id), 'release_id': str(release.id),
            'snapshot_id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no,
            'evidence_ref_digest_version': 1,
            'evidence_ref_sha256': evidence_reference_digest(data.evidence_ref),
            'decision': data.decision, 'actor_source': resolved_actor.source,
            **({'supersedes_id': str(previous.id), 'previous_decision': previous.decision,
                'correction_reason': data.correction_reason} if previous else {})})
    return assessment, True
