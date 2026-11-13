"""Isolated migrated PostgreSQL only, through normal CI's TEST_POSTGRES_URL."""
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.core import Release, ApplicationReleaseDetail, StandardReleaseDetail
from test_application_release_creation import configure, seed, body, submit, request, service
from test_command_concurrency_postgres import pg, overlapping_commands, count  # noqa: F401


@pytest.fixture
def creation_pg(pg, monkeypatch):
    configure(monkeypatch); engine, _ = pg
    with Session(engine, expire_on_commit=False) as db: ids = seed(db)
    return engine, ids


def command(fn):
    def execute(db):
        try:
            result = fn(db)
            return SimpleNamespace(id=json.dumps(result[0], sort_keys=True))
        except HTTPException as exc:
            assert not db.in_transaction()
            return SimpleNamespace(id='denied:'+str(exc.status_code)+':'+str(exc.detail))
    return execute


@pytest.mark.parametrize('race', ['same_key','different_body','same_version','cross_project','different_ssr'])
def test_concurrent_creation_serializes_exact_key_and_customer_version(creation_pg, monkeypatch, race):
    engine, ids = creation_pg
    with Session(engine) as db:
        values = body(db, ids); other_ids = dict(ids)
        if race == 'different_ssr':
            standard = Release(software_id=ids['software'], release_type='STANDARD', version='base-2', status='DRAFT')
            db.add(standard); db.flush(); db.add(StandardReleaseDetail(release_id=standard.id)); db.commit()
            other_ids['standard'] = standard.id
        if race == 'cross_project': other_ids['project'] = ids['other']
        other = body(db, other_ids)
    if race == 'same_key': other = dict(values)
    elif race == 'different_body': other = {**values, 'reason': 'Different reason'}
    first, second = overlapping_commands(engine, monkeypatch, command(lambda db: submit(db, ids, values)),
                                        command(lambda db: submit(db, other_ids, other)))
    assert first[0] == second[0] == 'ok'
    if race == 'same_key': assert first[1] == second[1]
    else: assert second[1].startswith('denied:409:')
    with Session(engine) as db:
        assert count(db, AuditEvent, event_type='APPLICATION_RELEASE_CREATED') == 1
        assert count(db, Release, release_type='APPLICATION', software_id=ids['software']) == 1
        assert count(db, ApplicationReleaseDetail, customer_id=ids['customer']) == 1
        assert service(db).receipt(values['request_id'], request(db, ids))['applied_status'] == 'DRAFT'
        assert not db.in_transaction()


def test_deferred_relationship_guard_rejects_wrong_customer_and_rolls_back(creation_pg):
    engine, ids = creation_pg
    with Session(engine) as db:
        values = body(db, ids); submit(db, ids, values)
        row = db.get(ApplicationReleaseDetail, values['request_id'])
        row.standard_base_release_id = values['request_id']
        with pytest.raises(DBAPIError): db.commit()
        db.rollback()
        assert db.get(ApplicationReleaseDetail, values['request_id']).standard_base_release_id == ids['standard']
        assert service(db).receipt(values['request_id'], request(db, ids))['applied_status'] == 'DRAFT'


@pytest.mark.parametrize('kind', ['principal', 'project', 'software', 'session'])
def test_security_revocation_waiter_rechecks_before_replay(creation_pg, kind):
    import hashlib
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from datetime import datetime, timedelta, timezone
    from app.models.security import SecurityPrincipal, ProjectMembership, SoftwareMembership, BrowserSession
    from app.services.admin_lock import admin_write_gate
    from test_application_release_creation import TOKEN
    engine, ids = creation_pg; sid = None
    with Session(engine) as db:
        values = body(db, ids); submit(db, ids, values)
        if kind == 'session':
            sid = uuid.uuid4(); now = datetime.now(timezone.utc)
            db.add(BrowserSession(id=sid, principal_id=ids['actor'], token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
                created_at=now, expires_at=now+timedelta(minutes=5))); db.commit()
    ready, release = Event(), Event(); pids = {}
    def revoke():
        with Session(engine) as db:
            admin_write_gate(db)
            model, key = {'principal': (SecurityPrincipal, ids['actor']), 'project': (ProjectMembership, ids['pm']),
                'software': (SoftwareMembership, ids['sm']), 'session': (BrowserSession, sid)}[kind]
            row = db.scalar(select(model).where(model.id == key).with_for_update())
            if kind == 'session': row.revoked_at = datetime.now(timezone.utc)
            else: row.status = 'DISABLED' if kind == 'principal' else 'SUSPENDED'
            db.flush(); ready.set(); assert release.wait(8); db.commit()
    def replay():
        with Session(engine) as db:
            pids['waiter'] = db.scalar(text('SELECT pg_backend_pid()'))
            try: submit(db, ids, values, request(db, ids, sid)); return 200
            except HTTPException as exc:
                assert not db.in_transaction(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(revoke)
        try:
            assert ready.wait(5); waiter = pool.submit(replay); deadline = time.monotonic()+5
            while True:
                with engine.connect() as con:
                    blocked = con.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'), {'pid':pids.get('waiter',0)})
                if blocked: break
                assert time.monotonic() < deadline; time.sleep(.01)
        finally: release.set()
        holder.result(timeout=10); assert waiter.result(timeout=10) in (401,403)


@pytest.mark.parametrize('revoke_first', [False, True])
def test_standard_revocation_and_creation_share_release_lock(creation_pg, monkeypatch, revoke_first):
    from app.services.revocation import RevocationService
    from test_application_release_creation import formal_standard
    engine, ids = creation_pg
    with Session(engine) as db:
        formal_standard(db, ids); values = body(db, ids)
    create = command(lambda db: submit(db, ids, values))
    revoke = lambda db: RevocationService(db).revoke('RELEASE', ids['standard'], 'Synthetic concurrent revocation', request_id=uuid.uuid4())
    first, second = overlapping_commands(engine, monkeypatch, revoke if revoke_first else create, create if revoke_first else revoke)
    assert first[0] == second[0] == 'ok'
    if revoke_first: assert second[1] == 'denied:409:standard_release_revoked'
    with Session(engine) as db:
        assert count(db, AuditEvent, event_type='APPLICATION_RELEASE_CREATED') == (0 if revoke_first else 1)
        if not revoke_first:
            assert submit(db, ids, values)[0]['applied_status'] == 'DRAFT'
            assert service(db).receipt(values['request_id'], request(db, ids))['applied_status'] == 'DRAFT'
