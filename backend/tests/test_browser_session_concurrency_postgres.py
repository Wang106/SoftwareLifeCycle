"""Real PostgreSQL locks serialize same-user registration, quota and revocation."""
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.browser_sessions import CreateSession, create_session, revoke_session
from app.auth import AuthenticatedPrincipal
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, SecurityPrincipal
from test_command_concurrency_postgres import pg, overlapping_commands


def setup(engine):
    with Session(engine) as db:
        person = SecurityPrincipal(issuer='https://issuer.test', subject='person', principal_type='USER', display_name='User')
        db.add(person); db.commit(); identifier = person.id
    request = Request({'type': 'http', 'headers': [(b'authorization', b'Bearer verified-test-token')]})
    request.state.principal = AuthenticatedPrincipal(identifier, 'https://issuer.test', 'person', 'USER', 'User', None)
    request.state.token_expires = int(datetime.now(timezone.utc).timestamp()) + 600
    return request


def value():
    return CreateSession(id=uuid.uuid4(), expires_at=int(datetime.now(timezone.utc).timestamp()) + 300)


def command(fn):
    def run(db):
        try:
            result = fn(db)
            return SimpleNamespace(id=str(result['id']))
        except HTTPException as exc:
            db.rollback()
            return SimpleNamespace(id='error:'+str(exc.status_code))
    return run


def test_concurrent_registration_retry_creates_one_row_and_audit(pg, monkeypatch):
    engine, _ = pg; request = setup(engine); body = value()
    one, two = overlapping_commands(engine, monkeypatch,
        command(lambda db: create_session(body, request, db)), command(lambda db: create_session(body, request, db)))
    assert one[1] == two[1] == str(body.id)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BrowserSession)) == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == 'BROWSER_SESSION')) == 1


def test_concurrent_last_quota_slot_allows_only_one_new_session(pg, monkeypatch):
    engine, _ = pg; request = setup(engine)
    for _ in range(15):
        with Session(engine) as db: create_session(value(), request, db)
    body1, body2 = value(), value()
    one, two = overlapping_commands(engine, monkeypatch,
        command(lambda db: create_session(body1, request, db)), command(lambda db: create_session(body2, request, db)))
    assert one[1] == str(body1.id) and two[1] == 'error:429'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BrowserSession)) == 16


def test_concurrent_revoke_retry_records_one_revocation(pg, monkeypatch):
    engine, _ = pg; request = setup(engine); body = value()
    with Session(engine) as db: create_session(body, request, db)
    one, two = overlapping_commands(engine, monkeypatch,
        command(lambda db: revoke_session(body.id, request, db)), command(lambda db: revoke_session(body.id, request, db)))
    assert one[1] == two[1] == str(body.id)
    with Session(engine) as db:
        assert db.get(BrowserSession, body.id).revoked_at
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'BROWSER_SESSION_REVOKED')) == 1


def test_registration_retry_racing_revoke_cannot_resurrect_session(pg, monkeypatch):
    engine, _ = pg; request = setup(engine); body = value()
    with Session(engine) as db: create_session(body, request, db)
    one, two = overlapping_commands(engine, monkeypatch,
        command(lambda db: revoke_session(body.id, request, db)), command(lambda db: create_session(body, request, db)))
    assert one[1] == str(body.id) and two[1] == 'error:409'
    with Session(engine) as db:
        assert db.get(BrowserSession, body.id).revoked_at
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == 'BROWSER_SESSION')) == 2
