"""Original Resource digest and atomic audit on an isolated migrated PostgreSQL schema."""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from app.models.audit import AuditEvent
from app.models.resource import ResourceLink
from app.services.resource_links import ResourceInput, register_link, request_digest
from app.services.audit import AuditEventService


def request(release):
    return ResourceInput(request_id=uuid.uuid4(), entity_type='RELEASE', entity_id=release,
        title='原始报告', location_kind='NETWORK_PATH', location='//server/share/报告.pdf',
        description='说明', actor_name='Declared engineer', reason='原始原因')


def test_resource_digest_is_committed_once_with_original_audit(pg):
    engine, ids = pg
    data = request(ids['release'])
    with Session(engine) as db:
        _, created = register_link(db, data)
        assert created
        db.commit()
        event = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == data.request_id)).one()
        assert event.payload_json['request_digest_version'] == 1
        assert event.payload_json['request_sha256'] == request_digest(data)
        assert event.declared_actor_name == data.actor_name
        assert 'location' not in event.payload_json
        _, created = register_link(db, data)
        db.commit()
        assert not created
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == data.request_id)).all()) == 1


def test_resource_digest_failure_rolls_back_business_and_audit(pg, monkeypatch):
    engine, ids = pg
    data = request(ids['release'])
    original = AuditEventService.record
    def fail_after_audit(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError('simulated commit interruption')
    monkeypatch.setattr(AuditEventService, 'record', fail_after_audit)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            try:
                register_link(db, data)
                db.commit()
            except Exception:
                db.rollback()
                raise
        assert db.get(ResourceLink, data.request_id) is None
        assert not db.scalars(select(AuditEvent).where(AuditEvent.entity_id == data.request_id)).all()
