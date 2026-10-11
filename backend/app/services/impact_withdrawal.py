"""Append a terminal withdrawal; identical old requests only replay their audit."""
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from app.actor import ActorContext
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.impact import IssueImpactAssessment
from app.models.audit import AuditEvent
from app.services.audit import AuditEventService
from app.services.impact_history import action_value, current_event, next_sequence
from app.services.impact_assessment import (AssessmentError, evidence_reference_digest,
    sequenced_audit_matches, sequenced_payload)


class WithdrawalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    supersedes_id: uuid.UUID
    actor_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=4000)
    correction_reason: str = Field(min_length=1, max_length=4000)

    @field_validator('actor_name', 'reason', 'correction_reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value.strip()

    @model_validator(mode='after')
    def predecessor_not_self(self):
        if self.request_id == self.supersedes_id:
            raise ValueError('withdrawal cannot reference itself')
        return self


def record_withdrawal(db, issue_no, data, actor_context=None):
    actor = actor_context or ActorContext.legacy(data.actor_name)
    issue = db.scalar(select(Issue).where(Issue.issue_no == issue_no).with_for_update())
    if issue is None:
        raise AssessmentError('issue not found')
    existing = db.get(IssueImpactAssessment, data.request_id)
    previous = db.get(IssueImpactAssessment, data.supersedes_id)
    if existing:
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{data.request_id}'))
        expected = withdrawal_payload(previous, data, actor)
        if (existing.issue_id != issue.id or action_value(existing) != 'WITHDRAW'
            or existing.decision is not None or existing.evidence_ref is not None
            or existing.after_withdrawal_id is not None or existing.actor_name != actor.name
            or any(getattr(existing, field) != getattr(data, field)
                for field in ('release_id', 'snapshot_id', 'supersedes_id', 'reason', 'correction_reason'))
            or previous is None or not sequenced_audit_matches(event, existing, issue, data, actor)
            or any(key not in event.payload_json or event.payload_json[key] != value for key, value in expected.items())):
            raise AssessmentError('request_id already used for a different impact operation')
        return existing, False
    release = db.get(Release, data.release_id)
    snapshot = db.get(ReleaseSnapshot, data.snapshot_id)
    if not release or not snapshot or snapshot.release_id != release.id or snapshot.status != 'FROZEN':
        raise AssessmentError('withdrawal requires a matching frozen snapshot')
    linked = select(SoftwareChangeRequest.id).join(IssueChangeRequestRelation,
        IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id).where(
        IssueChangeRequestRelation.issue_id == issue.id, SoftwareChangeRequest.software_id == release.software_id).exists()
    if not db.scalar(select(linked)):
        raise AssessmentError('release is not a candidate from linked SCR software')
    current = current_event(db, issue.id, data.release_id, data.snapshot_id)
    if (current is None or action_value(current) == 'WITHDRAW' or current.id != data.supersedes_id):
        raise AssessmentError('withdrawal predecessor is not the current effective judgment')
    row = IssueImpactAssessment(id=data.request_id, issue_id=issue.id, release_id=data.release_id,
        snapshot_id=data.snapshot_id, action='WITHDRAW', decision=None, evidence_ref=None,
        supersedes_id=data.supersedes_id, reason=data.reason, correction_reason=data.correction_reason,
        actor_name=actor.name, context_seq=next_sequence(db, issue.id, data.release_id, data.snapshot_id))
    db.add(row); db.flush()
    AuditEventService(db).record(event_no=f'EVT-IMPACT-{data.request_id}', event_type='ISSUE_IMPACT',
        action='WITHDRAW', entity_type='Issue', entity_id=issue.id, entity_ref=issue.issue_no,
        **actor.audit_fields(), summary=f'{issue.issue_no}: withdraw {previous.id}'[:240], detail=data.reason,
        payload={**withdrawal_payload(previous, data, actor), **sequenced_payload(row, issue, data),
            'snapshot_no': snapshot.snapshot_no})
    return row, True


def withdrawal_payload(previous, data, actor):
    return {'assessment_id': str(data.request_id), 'release_id': str(data.release_id),
        'snapshot_id': str(data.snapshot_id), 'supersedes_id': str(data.supersedes_id),
        'previous_decision': previous.decision if previous else None, 'decision': None,
        'correction_reason': data.correction_reason, 'actor_source': actor.source,
        'evidence_ref_digest_version': 1, 'evidence_ref_sha256': evidence_reference_digest(None)}
