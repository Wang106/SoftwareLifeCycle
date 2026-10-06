"""Real PostgreSQL overlap: principal state, identity uniqueness and session locks."""
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.browser_sessions import CreateSession, create_session
from app.api.principal_admin import RegisterPrincipal, PrincipalStatusChange, register_principal, change_principal_status
from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, SecurityPrincipal
from test_command_concurrency_postgres import pg, overlapping_commands


def setup(engine, monkeypatch):
    monkeypatch.setattr(settings,'auth_mode','oidc')
    monkeypatch.setattr(settings,'read_only_mode',False)
    monkeypatch.setattr(settings,'oidc_issuer_url','https://test.example.com')
    with Session(engine,expire_on_commit=False) as db:
        rows = [SecurityPrincipal(issuer=settings.oidc_issuer_url,subject='person-'+str(index),
                principal_type='USER',display_name='Test person') for index in range(3)]
        db.add_all(rows); db.flush()
        db.add_all([GlobalRoleAssignment(principal_id=row.id,role='PLATFORM_ADMIN') for row in rows[:2]])
        db.commit()
        requests = []
        for row in rows:
            request = Request({'type':'http','headers':[(b'authorization',b'Bearer verified-test-token')]})
            request.state.principal = AuthenticatedPrincipal(row.id,row.issuer,row.subject,row.principal_type,row.display_name,None)
            request.state.token_expires = int(datetime.now(timezone.utc).timestamp())+600
            requests.append(request)
        return [row.id for row in rows], requests


def command(fn):
    def execute(db):
        try:
            result = fn(db)
            return SimpleNamespace(id=json.dumps(result,default=str,sort_keys=True))
        except HTTPException as exc:
            # Session routes release their context at request end; admin controls
            # explicitly roll back before throwing and must release locks themselves.
            if fn.__name__ != 'session_command': assert not db.in_transaction()
            db.rollback()
            return SimpleNamespace(id='error:'+exc.detail)
    return execute


def outcome(value):
    result = value[1]
    return result if result.startswith('error:') else json.loads(result)


@pytest.mark.parametrize('same_admin',[False,True])
@pytest.mark.parametrize('same_event',[False,True])
def test_competing_status_requests_wait_and_recheck_or_replay(pg,monkeypatch,same_admin,same_event):
    engine,_ = pg; ids,requests = setup(engine,monkeypatch)
    body = PrincipalStatusChange(event_no='P-DISABLE',expected_status='ACTIVE',status='DISABLED',reason='Disable pending review')
    second = body if same_event else body.model_copy(update={'event_no':'P-OTHER'})
    results = overlapping_commands(engine,monkeypatch,
        command(lambda db:change_principal_status(ids[2],body,requests[0],db)),
        command(lambda db:change_principal_status(ids[2],second,requests[0 if same_admin else 1],db)))
    assert outcome(results[0])['replayed'] is False
    if same_admin and same_event: assert outcome(results[1])['replayed'] is True
    else: assert outcome(results[1]) == ('error:audit_event_conflict' if same_event else 'error:principal_status_conflict')
    with Session(engine) as db:
        assert db.get(SecurityPrincipal,ids[2]).status == 'DISABLED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == ids[2])) == 1


@pytest.mark.parametrize('duplicate',['exact_retry','uuid','subject','audit_owner'])
def test_concurrent_registration_has_one_identity_and_audit(pg,monkeypatch,duplicate):
    engine,_ = pg; _,requests = setup(engine,monkeypatch)
    body = RegisterPrincipal(event_no='P-REGISTER',principal_id=uuid.uuid4(),subject='new-opaque-subject',
        principal_type='USER',display_name='New identity',reason='Register approved reference')
    second = body if duplicate != 'subject' else body.model_copy(update={'principal_id':uuid.uuid4()})
    if duplicate in {'uuid','subject'}:
        second = second.model_copy(update={'event_no':'P-REGISTER-OTHER'})
    same_admin = duplicate == 'exact_retry'
    results = overlapping_commands(engine,monkeypatch,
        command(lambda db:register_principal(body,requests[0],db)),
        command(lambda db:register_principal(second,requests[0 if same_admin else 1],db)))
    assert outcome(results[0])['replayed'] is False
    if same_admin: assert outcome(results[1])['replayed'] is True
    else: assert outcome(results[1]) == ('error:audit_event_conflict' if duplicate == 'audit_owner' else 'error:principal_registration_conflict')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(SecurityPrincipal).where(SecurityPrincipal.subject == body.subject)) == 1
        assert db.get(SecurityPrincipal,body.principal_id).status == 'DISABLED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'PRINCIPAL_REGISTERED')) == 1


@pytest.mark.parametrize('disable_first',[False,True])
def test_disable_and_session_registration_share_principal_lock(pg,monkeypatch,disable_first):
    engine,_ = pg; ids,requests = setup(engine,monkeypatch)
    body = PrincipalStatusChange(event_no='P-DISABLE',expected_status='ACTIVE',status='DISABLED',reason='Disable pending review')
    cookie = CreateSession(id=uuid.uuid4(),expires_at=int(datetime.now(timezone.utc).timestamp())+300)
    def session_command(db): return create_session(cookie,requests[2],db)
    disable = command(lambda db:change_principal_status(ids[2],body,requests[0],db))
    register = command(session_command)
    one,two = overlapping_commands(engine,monkeypatch,disable if disable_first else register,register if disable_first else disable)
    disabled = outcome(one if disable_first else two)
    assert disabled['current_status'] == 'DISABLED'
    assert disabled['revoked_browser_sessions'] == (0 if disable_first else 1)
    if disable_first: assert outcome(two) == 'error:inactive_principal'
    with Session(engine) as db:
        assert db.get(SecurityPrincipal,ids[2]).status == 'DISABLED'
        row = db.get(BrowserSession,cookie.id)
        assert row is None if disable_first else row.revoked_at is not None
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'PRINCIPAL_STATUS_CHANGED')) == 1
