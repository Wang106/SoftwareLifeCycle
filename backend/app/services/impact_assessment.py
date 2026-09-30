"""Atomic, idempotent writer; transaction ownership stays with the route."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.impact import IssueImpactAssessment
from app.services.audit import AuditEventService


class AssessmentInput(BaseModel):
    request_id: uuid.UUID
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    decision: Literal['AFFECTED', 'NOT_AFFECTED', 'NEEDS_REVIEW']
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ref: str | None = Field(default=None, max_length=2000)
    actor_name: str = Field(min_length=1, max_length=120)

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


def record_assessment(db: Session, issue_no: str, data: AssessmentInput):
    # Serializes issue review writes, including concurrent retries.
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no).with_for_update()).first()
    if issue is None:
        raise AssessmentError('issue not found')
    existing = db.get(IssueImpactAssessment, data.request_id)
    fields = ('release_id', 'snapshot_id', 'decision', 'reason', 'evidence_ref', 'actor_name')
    if existing:
        if existing.issue_id != issue.id or any(getattr(existing, field) != getattr(data, field) for field in fields):
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
    assessment = IssueImpactAssessment(id=data.request_id, issue_id=issue.id,
        **{field: getattr(data, field) for field in fields})
    db.add(assessment)
    db.flush()
    AuditEventService(db).record(event_no=f'EVT-IMPACT-{data.request_id}', event_type='ISSUE_IMPACT',
        action='ASSESS', entity_type='Issue', entity_id=issue.id, entity_ref=issue.issue_no,
        actor_name=data.actor_name, summary=f'{issue.issue_no}: {release.version} / {snapshot.snapshot_no} → {data.decision}'[:240],
        detail=data.reason, payload={'assessment_id': str(assessment.id), 'release_id': str(release.id),
            'snapshot_id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no, 'decision': data.decision})
    return assessment, True
