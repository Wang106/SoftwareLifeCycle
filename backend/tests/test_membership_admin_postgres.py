"""Prove two different admins serialize on the exact membership in PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.api.membership_admin import MembershipStatusChange, change_status
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.services.audit import AuditEventService
from test_command_concurrency_postgres import pg


def request_for(row):
    request = Request({'type':'http', 'headers':[]})
    request.state.principal = AuthenticatedPrincipal(row.id, row.issuer, row.subject, row.principal_type, row.display_name, None)
    return request


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
@pytest.mark.parametrize('same_event', [False, True])
@pytest.mark.parametrize('same_admin', [False, True])
def test_competing_admins_wait_then_conflict_without_duplicate_audit(pg, monkeypatch, scope, same_event, same_admin):
    engine, ids = pg
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    monkeypatch.setattr(settings, 'read_only_mode', False)
    from app.models.core import Project, SoftwareProduct
    with Session(engine, expire_on_commit=False) as db:
        admins = [SecurityPrincipal(issuer='https://test.example.com', subject=str(uuid.uuid4()), principal_type='USER', display_name='Administrator') for _ in range(2)]
        recipient = SecurityPrincipal(issuer='https://test.example.com', subject='recipient', principal_type='USER', display_name='Recipient')
        db.add_all(admins+[recipient]); db.flush()
        db.add_all([GlobalRoleAssignment(principal_id=row.id, role='PLATFORM_ADMIN') for row in admins])
        model = ProjectMembership if scope == 'PROJECT' else SoftwareMembership
        scope_id = db.scalar(select(Project.id if scope == 'PROJECT' else SoftwareProduct.id))
        row = model(principal_id=recipient.id, **({'project_id':scope_id, 'role':'REVIEWER'} if scope == 'PROJECT' else {'software_id':scope_id, 'role':'SOFTWARE_VIEWER'}))
        db.add(row); db.commit(); identifier = row.id
        requests = [request_for(admin) for admin in admins]
    first = MembershipStatusChange(event_no='ADM-FIRST', expected_status='ACTIVE', status='SUSPENDED', reason='Review access before release')
    second = first if same_event else first.model_copy(update={'event_no':'ADM-SECOND'})
    reached, release = Event(), Event()
    record = AuditEventService.record
    def held(service, **kwargs):
        event = record(service, **kwargs)
        reached.set()
        assert release.wait(8)
        return event
    monkeypatch.setattr(AuditEventService, 'record', held)
    def execute(index, body):
        with Session(engine, expire_on_commit=False) as db:
            try:
                return change_status(scope, identifier, body, requests[index], db)
            except HTTPException as exc:
                assert not db.in_transaction()
                return exc.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(execute, 0, first)
        try:
            assert reached.wait(5)
            two = pool.submit(execute, 0 if same_admin else 1, second)
            deadline = time.monotonic()+5
            while True:
                with engine.connect() as connection:
                    waiting = connection.scalar(text('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid)) > 0'))
                if waiting:
                    break
                assert time.monotonic() < deadline, 'second admin never blocked on PostgreSQL'
                time.sleep(.01)
        finally:
            release.set()
        assert one.result(timeout=10)['replayed'] is False
        outcome = two.result(timeout=10)
        if same_event and same_admin:
            assert outcome['replayed'] is True and outcome['current_status'] == 'SUSPENDED'
        else:
            assert outcome == ('audit_event_conflict' if same_event else 'membership_status_conflict')
    with Session(engine) as db:
        assert db.get(model, identifier).status == 'SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == identifier)) == 1
