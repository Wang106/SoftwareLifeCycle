"""Create purpose-limited test drafts pinned to an existing frozen snapshot."""
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import TestRelease
from app.services.audit import AuditEventService
from app.actor import ActorContext, idempotent_actor_matches


class TestReleaseError(ValueError):
    def __init__(self, detail, status_code=409):
        super().__init__(detail)
        self.status_code = status_code


class TestReleaseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    test_release_no: str = Field(min_length=1, max_length=50)
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    purpose_scope: Literal['SOFTWARE_TEST', 'BATTERY_TEST', 'CUSTOMER_TEST']
    actor_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('test_release_no', 'actor_name', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value.strip()


def create_test_draft(db, data, actor_context: ActorContext | None = None):
    resolved_actor = actor_context or ActorContext.legacy(data.actor_name)
    release = db.scalars(select(Release).where(Release.id == data.release_id).with_for_update()).first()
    if not release:
        raise TestReleaseError('release not found', 404)
    event_no = f'EVT-TR-{data.request_id}'
    existing = db.get(TestRelease, data.request_id)
    if existing:
        audit = db.scalars(select(AuditEvent).where(AuditEvent.event_no == event_no)).first()
        fields = ('test_release_no', 'release_id', 'snapshot_id', 'purpose_scope')
        if (any(getattr(existing, field) != getattr(data, field) for field in fields)
            or not audit or audit.actor_name != resolved_actor.name
            or audit.detail != data.reason
            or not idempotent_actor_matches(audit, resolved_actor)):
            raise TestReleaseError('request_id already used for different or legacy content')
        return existing, False
    snapshot = db.get(ReleaseSnapshot, data.snapshot_id)
    if not snapshot:
        raise TestReleaseError('snapshot not found', 404)
    if snapshot.release_id != release.id or snapshot.status != 'FROZEN':
        raise TestReleaseError('test release requires a matching frozen snapshot')
    if db.scalars(select(TestRelease).where(TestRelease.test_release_no == data.test_release_no)).first():
        raise TestReleaseError('test_release_no already exists')
    row = TestRelease(id=data.request_id, test_release_no=data.test_release_no, release_id=release.id,
        snapshot_id=snapshot.id, purpose_scope=data.purpose_scope, status='DRAFT')
    db.add(row); db.flush()
    AuditEventService(db).record(event_no=event_no, event_type='TEST_RELEASE', action='CREATE_DRAFT',
        entity_type='TEST_RELEASE', entity_id=row.id, entity_ref=row.test_release_no,
        **resolved_actor.audit_fields(),
        summary=f'{row.test_release_no}: {release.version} / {snapshot.snapshot_no} · {row.purpose_scope}'[:240],
        detail=data.reason, payload={'release_id': str(release.id), 'snapshot_id': str(snapshot.id),
            'snapshot_no': snapshot.snapshot_no, 'purpose_scope': row.purpose_scope,
            'status': 'DRAFT', 'actor_source': resolved_actor.source})
    return row, True
