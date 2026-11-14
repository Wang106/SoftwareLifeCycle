"""Independent connections in normal CI's disposable migrated PostgreSQL only."""
import hashlib
import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.core import Artifact, Release
from app.models.security import BrowserSession, ProjectMembership
from app.models.upload import PrivateUploadSession
from app.services.admin_lock import admin_write_gate
from app.services.private_upload_sessions import PrivateUploadService
from app.services.local_artifact_storage import LocalArtifactStorage
from test_command_concurrency_postgres import pg, count
from test_application_component_declaration_postgres import component_pg
from test_application_component_declaration import body, submit
from test_application_release_creation import TOKEN, request
from test_private_upload_sessions import DATA, service, values


@pytest.fixture
def upload_pg(component_pg, tmp_path):
    engine, ids = component_pg
    with Session(engine) as db:
        receipt, _ = submit(db, ids, body(db, ids))
        ids = {**ids, 'component': uuid.UUID(receipt['component_id'])}
        artifacts = count(db, Artifact)
    root = tmp_path / 'private-bytes'
    root.mkdir(mode=0o700)
    yield engine, ids, root
    with Session(engine) as db:
        assert count(db, Artifact) == artifacts


def prepared(upload_pg):
    engine, ids, root = upload_pg
    with Session(engine) as db:
        svc = service(db, root)
        command = values(svc, db, ids)
        reservation, created = svc.reserve(request=request(db, ids), **command)
        assert created
    return command, reservation


def invoke(engine, fn, pids=None, name=None):
    with Session(engine, expire_on_commit=False) as db:
        if pids is not None:
            pids[name] = db.scalar(text('SELECT pg_backend_pid()'))
        try:
            result = fn(db)
            assert not db.in_transaction()
            return ('ok', result)
        except HTTPException as exc:
            assert not db.in_transaction()
            return ('denied', exc.status_code, exc.detail)


def assert_blocked_by(engine, pids):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if 'waiter' in pids:
            with engine.connect() as connection:
                blockers = connection.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pids['waiter']})
            if pids['holder'] in blockers:
                assert pids['holder'] != pids['waiter']
                return
        time.sleep(.01)
    pytest.fail('second independent backend did not wait for the held transaction')


@pytest.mark.parametrize('race', ['identical', 'changed_body', 'independent_request'])
def test_reservation_races_preserve_original_descriptor(upload_pg, monkeypatch, race):
    engine, ids, root = upload_pg
    with Session(engine) as db:
        first = values(service(db, root), db, ids)
    second = dict(first)
    if race == 'changed_body':
        second['reason'] = 'Different synthetic request body'
    elif race == 'independent_request':
        second['request_id'] = uuid.uuid4()
    held, release = Event(), Event()
    pids = {}
    original = PrivateUploadService._record
    descriptors = []
    original_reserve = LocalArtifactStorage.reserve
    def reserve_descriptor(storage, **kwargs):
        descriptor = original_reserve(storage, **kwargs)
        descriptors.append(descriptor.object_id)
        return descriptor
    monkeypatch.setattr(LocalArtifactStorage, 'reserve', reserve_descriptor)
    def record(svc, row, actor, previous):
        if row.id == first['request_id'] and previous is None:
            pids['holder'] = svc.db.scalar(text('SELECT pg_backend_pid()'))
            held.set()
            assert release.wait(8), 'reservation holder was not released'
        return original(svc, row, actor, previous)
    monkeypatch.setattr(PrivateUploadService, '_record', record)
    def reserve(command):
        return lambda db: service(db, root).reserve(request=request(db, ids), **command)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(invoke, engine, reserve(first))
        try:
            assert held.wait(5)
            two = pool.submit(invoke, engine, reserve(second), pids, 'waiter')
            assert_blocked_by(engine, pids)
        finally:
            release.set()
        result1, result2 = one.result(timeout=12), two.result(timeout=12)
    assert result1[0] == 'ok' and result1[1][1] is True
    if race == 'changed_body':
        assert result2 == ('denied', 409, 'private_upload_request_conflict')
    elif race == 'identical':
        assert result2 == ('ok', (result1[1][0], False))
    else:
        assert result2[0] == 'ok' and result2[1][1] is True
        assert result2[1][0]['object_id'] != result1[1][0]['object_id']
    with Session(engine) as db:
        expected = 2 if race == 'independent_request' else 1
        assert len(descriptors) == len(set(descriptors)) == expected
        assert count(db, PrivateUploadSession) == expected
        assert count(db, AuditEvent, event_type='PRIVATE_UPLOAD_SESSION') == expected
        assert service(db, root).receipt(first['request_id'], request(db, ids))['reservation'] == result1[1][0]
    assert list(root.iterdir()) == []


class BlockingSource(io.BytesIO):
    def __init__(self, db, entered, release):
        super().__init__(DATA)
        self.db, self.entered, self.release = db, entered, release
    def read(self, size):
        assert not self.db.in_transaction(), 'stream I/O retained a database transaction'
        self.entered.set()
        assert self.release.wait(8), 'synthetic stream was not released'
        return super().read(size)


class NeverRead:
    def read(self, size):
        raise AssertionError('second receive consumed its source')


def test_one_receive_consumes_source_and_receipt_observes_durable_receiving(upload_pg):
    engine, ids, root = upload_pg
    command, reservation = prepared(upload_pg)
    entered, release = Event(), Event()
    def receive(db):
        return service(db, root).receive(command['request_id'], BlockingSource(db, entered, release), request(db, ids))
    def observe_and_retry(db):
        svc = service(db, root)
        observed = svc.receipt(command['request_id'], request(db, ids))
        assert observed['state'] == 'RECEIVING' and observed['revision'] == 1
        assert observed['reservation'] == reservation and observed['stored_receipt'] is None
        return svc.receive(command['request_id'], NeverRead(), request(db, ids))
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(invoke, engine, receive)
        try:
            assert entered.wait(5)
            two = pool.submit(invoke, engine, observe_and_retry)
            # Finish while the original reader remains blocked, not after release.
            assert two.result(timeout=5) == ('denied', 409, 'private_upload_attempt_consumed')
        finally:
            release.set()
        result = one.result(timeout=12)
    assert result[0] == 'ok' and result[1]['state'] == 'STORED_PRIVATE'
    with Session(engine) as db:
        assert count(db, PrivateUploadSession) == 1
        assert count(db, AuditEvent, event_type='PRIVATE_UPLOAD_SESSION') == 5
        assert service(db, root).receipt(command['request_id'], request(db, ids))['stored_receipt'] == result[1]
    assert sorted(path.suffix for path in root.iterdir()) == ['.blob', '.part']


@pytest.mark.parametrize('kind', ['grant', 'session', 'release'])
def test_revocation_commits_during_blocked_stream_and_prevents_storage(upload_pg, kind):
    engine, ids, root = upload_pg
    command, _ = prepared(upload_pg)
    sid = None
    if kind == 'session':
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        with Session(engine) as db:
            db.add(BrowserSession(id=sid, principal_id=ids['actor'],
                token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
                created_at=now, expires_at=now + timedelta(minutes=5)))
            db.commit()
    entered, release = Event(), Event()
    def receive(db):
        return service(db, root).receive(command['request_id'], BlockingSource(db, entered, release), request(db, ids, sid))
    def revoke():
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            if kind != 'release':
                admin_write_gate(db)
            model, key = {'grant': (ProjectMembership, ids['pm']),
                          'session': (BrowserSession, sid),
                          'release': (Release, ids['release'])}[kind]
            row = db.scalar(select(model).where(model.id == key).with_for_update())
            if kind == 'session':
                row.revoked_at = datetime.now(timezone.utc)
            else:
                row.status = 'SUSPENDED' if kind == 'grant' else 'REVOKED'
            db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        uploader = pool.submit(invoke, engine, receive)
        try:
            assert entered.wait(5)
            pool.submit(revoke).result(timeout=5)
            # This commit proves authorization/parent locks are not retained over I/O.
            with Session(engine) as db:
                row = db.get(PrivateUploadSession, command['request_id'])
                assert row.state == 'RECEIVING' and row.revision == 1
        finally:
            release.set()
        result = uploader.result(timeout=12)
    assert result[0] == 'denied' and result[1] in (401, 403, 409)
    with Session(engine) as db:
        row = db.get(PrivateUploadSession, command['request_id'])
        assert row.state in ('RECEIVING', 'RECONCILIATION_REQUIRED')
        assert row.stored_receipt_json is None
        assert count(db, AuditEvent, event_type='PRIVATE_UPLOAD_SESSION', action='STORED_PRIVATE') == 0
    assert not any(path.suffix == '.blob' for path in root.iterdir())


def test_final_database_ack_loss_is_recovered_by_independent_receipt(upload_pg, monkeypatch):
    engine, ids, root = upload_pg
    command, reservation = prepared(upload_pg)
    with Session(engine) as db:
        svc = service(db, root)
        original_commit = db.commit
        lost = False
        def commit():
            nonlocal lost
            final = any(isinstance(row, PrivateUploadSession) and row.state == 'STORED_PRIVATE'
                        for row in db.identity_map.values())
            original_commit()
            if final and not lost:
                lost = True
                raise RuntimeError('synthetic final database acknowledgement lost')
        monkeypatch.setattr(db, 'commit', commit)
        with pytest.raises(RuntimeError, match='acknowledgement lost'):
            svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
        assert lost and not db.in_transaction()
    with Session(engine) as observer:
        svc = service(observer, root)
        receipt = svc.receipt(command['request_id'], request(observer, ids))
        assert receipt['state'] == 'STORED_PRIVATE' and receipt['revision'] == 4
        assert receipt['reservation'] == reservation
        assert receipt['stored_receipt']['object_id'] == reservation['object_id']
        assert count(observer, AuditEvent, event_type='PRIVATE_UPLOAD_SESSION') == 5
        with pytest.raises(HTTPException) as exc:
            svc.receive(command['request_id'], NeverRead(), request(observer, ids))
        assert exc.value.detail == 'private_upload_attempt_consumed'
        assert not observer.in_transaction()
