"""Synthetic bytes only; this package registers no HTTP upload or download."""
import hashlib
import io
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.core import Artifact, Release, ReleaseComponent
from app.models.security import ProjectMembership, SecurityPrincipal, SoftwareMembership
from test_application_component_declaration import (
    component_db, creation_db, body as component_body, submit as component_submit,
)
from test_application_release_creation import request

SCOPE = uuid.UUID('30b29557-3814-480f-b719-dab9a17626a8')
DATA = b'synthetic upload payload, not a user file'


@pytest.fixture
def upload_db(component_db, tmp_path):
    db, ids = component_db
    result, _ = component_submit(db, ids, component_body(db, ids))
    root = tmp_path / 'private-bytes'
    root.mkdir(mode=0o700)
    return db, {**ids, 'component': uuid.UUID(result['component_id'])}, root


def service(db, root, **options):
    from app.services.private_upload_sessions import PrivateUploadService
    return PrivateUploadService(db, root=str(root), storage_scope_id=SCOPE,
                                max_bytes=1024, enabled=True, **options)


def values(svc, db, ids, data=DATA):
    context = svc.context(ids['component'], request(db, ids))
    return dict(request_id=uuid.uuid4(), component_id=ids['component'],
                expected_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                expected_context_digest=context['context_digest'], reason='Synthetic storage test')


def reserve(svc, db, ids, data=DATA):
    command = values(svc, db, ids, data)
    result, created = svc.reserve(request=request(db, ids), **command)
    assert created
    return command, result


def test_disabled_is_inert_before_database_or_filesystem():
    from app.services.private_upload_sessions import PrivateUploadService
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError('disabled service must not touch database')
    svc = PrivateUploadService(NoDatabase(), root='/not/accessed')
    for operation in (
        lambda: svc.context(uuid.uuid4(), None),
        lambda: svc.reserve(request=None),
        lambda: svc.receive(uuid.uuid4(), io.BytesIO(DATA), None),
        lambda: svc.receipt(uuid.uuid4(), None),
        lambda: svc.inspect(uuid.uuid4(), None),
    ):
        with pytest.raises(HTTPException) as exc:
            operation()
        assert exc.value.status_code == 403 and exc.value.detail == 'private_upload_disabled'


def test_reservation_is_durable_before_bytes_and_replay_is_exact(upload_db):
    from app.models.upload import PrivateUploadSession
    db, ids, root = upload_db
    svc = service(db, root)
    command, original = reserve(svc, db, ids)
    assert list(root.iterdir()) == []
    row = db.get(PrivateUploadSession, command['request_id'])
    assert row.state == 'RESERVED' and row.revision == 0
    assert str(row.object_id) == original['object_id']
    assert str(row.object_id) != str(command['request_id'])
    assert svc.reserve(request=request(db, ids), **command) == (original, False)
    receipt = svc.receipt(command['request_id'], request(db, ids))
    assert receipt['reservation'] == original and receipt['stored_receipt'] is None
    assert not db.in_transaction() and list(root.iterdir()) == []
    assert db.scalar(select(func.count()).select_from(Artifact)) == 0


@pytest.mark.parametrize('data', [b'', DATA, b'x' * 1024])
def test_one_shot_storage_and_original_receipt(upload_db, data):
    db, ids, root = upload_db
    svc = service(db, root)
    command, original = reserve(svc, db, ids, data)
    source = io.BytesIO(data)
    stored = svc.receive(command['request_id'], source, request(db, ids))
    assert not source.closed and stored['state'] == 'STORED_PRIVATE'
    assert stored['request_id'] == str(command['request_id'])
    assert stored['object_id'] == original['object_id']
    assert sorted(path.suffix for path in root.iterdir()) == ['.blob', '.part']
    restart = service(db, root)
    status = restart.receipt(command['request_id'], request(db, ids))
    assert status['state'] == 'STORED_PRIVATE' and status['revision'] == 4
    assert status['stored_receipt'] == stored and status['reservation'] == original
    observation = restart.inspect(command['request_id'], request(db, ids))
    assert observation['status'] == status
    assert set(observation['bytes'].values()) == {'verified'}
    class NeverRead:
        def read(self, count): raise AssertionError('must not retransmit')
    with pytest.raises(HTTPException) as exc:
        restart.receive(command['request_id'], NeverRead(), request(db, ids))
    assert exc.value.detail == 'private_upload_attempt_consumed'
    assert db.scalar(select(func.count()).select_from(Artifact)) == 0


@pytest.mark.parametrize('field,value', [
    ('expected_bytes', True), ('expected_bytes', -1), ('expected_bytes', 1025),
    ('sha256', 'A' * 64), ('request_id', 'not-uuid'), ('request_id', str(uuid.UUID(int=0))),
    ('reason', ''), ('reason', 'x\ud800'), ('filename', '../../private'), ('storage_reference', '/elsewhere'),
])
def test_bad_metadata_never_creates_bytes(upload_db, field, value):
    db, ids, root = upload_db
    svc = service(db, root)
    command = {**values(svc, db, ids), field: value}
    with pytest.raises((HTTPException, ValueError)):
        svc.reserve(request=request(db, ids), **command)
    assert list(root.iterdir()) == [] and not db.in_transaction()


@pytest.mark.parametrize('kind', ['principal', 'service', 'project', 'software', 'readonly', 'auth'])
def test_authority_rechecked_before_any_bytes(upload_db, monkeypatch, kind):
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    if kind == 'principal': db.get(SecurityPrincipal, ids['actor']).status = 'DISABLED'
    elif kind == 'service': db.get(SecurityPrincipal, ids['actor']).principal_type = 'SERVICE'
    elif kind == 'project': db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
    elif kind == 'software': db.get(SoftwareMembership, ids['sm']).status = 'SUSPENDED'
    elif kind == 'readonly': monkeypatch.setattr(settings, 'read_only_mode', True)
    else: monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    db.commit()
    with pytest.raises(HTTPException):
        svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    assert list(root.iterdir()) == [] and not db.in_transaction()


@pytest.mark.parametrize('kind', ['context', 'released', 'revoked', 'public_component'])
def test_exact_private_draft_context_required(upload_db, kind):
    db, ids, root = upload_db
    svc = service(db, root)
    command = values(svc, db, ids)
    if kind == 'context': command['expected_context_digest'] = '0' * 64
    elif kind == 'released': db.get(Release, ids['release']).status = 'RELEASED'
    elif kind == 'revoked': db.get(Release, ids['standard']).status = 'REVOKED'
    else: command['component_id'] = ids['base']
    db.commit()
    with pytest.raises(HTTPException): svc.reserve(request=request(db, ids), **command)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('data', [b'short', DATA + b'overflow', b'x' * len(DATA)])
def test_mismatch_retained_and_never_retried(upload_db, data):
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    with pytest.raises(Exception): svc.receive(command['request_id'], io.BytesIO(data), request(db, ids))
    status = svc.receipt(command['request_id'], request(db, ids))
    assert status['state'] == 'RECONCILIATION_REQUIRED' and status['stored_receipt'] is None
    assert len(list(root.iterdir())) == 1
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(HTTPException): svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


def test_published_bytes_after_uncertain_ack_do_not_become_success(upload_db, monkeypatch):
    from app.services.local_artifact_storage import StorageError
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    commit = svc._storage.commit
    def uncertain(descriptor):
        commit(descriptor)
        raise StorageError('synthetic lost acknowledgement')
    monkeypatch.setattr(svc._storage, 'commit', uncertain)
    with pytest.raises(StorageError): svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    observation = service(db, root).inspect(command['request_id'], request(db, ids))
    assert observation['status']['state'] == 'RECONCILIATION_REQUIRED'
    assert observation['status']['stored_receipt'] is None
    assert set(observation['bytes'].values()) == {'verified'}


@pytest.mark.parametrize('kind', ['project', 'release'])
def test_revocation_during_stream_prevents_business_completion(upload_db, kind):
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    class RevokeDuringRead(io.BytesIO):
        changed = False
        def read(self, n):
            assert not db.in_transaction(), 'network/stream I/O must not hold authorization locks'
            if not self.changed:
                self.changed = True
                if kind == 'project': db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
                else: db.get(Release, ids['release']).status = 'RELEASED'
                db.commit()
            return super().read(n)
    with pytest.raises(HTTPException):
        svc.receive(command['request_id'], RevokeDuringRead(DATA), request(db, ids))
    from app.models.upload import PrivateUploadSession
    row = db.get(PrivateUploadSession, command['request_id'])
    assert row.state != 'STORED_PRIVATE' and row.stored_receipt_json is None
    assert not any(p.suffix == '.blob' for p in root.iterdir())


def test_reentrant_source_is_rejected_without_second_effect(upload_db):
    from app.services.local_artifact_storage import StorageError
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    class Reentrant:
        def read(self, count):
            return svc.receipt(command['request_id'], request(db, ids))
    with pytest.raises(StorageError) as exc:
        svc.receive(command['request_id'], Reentrant(), request(db, ids))
    assert isinstance(exc.value.__cause__, HTTPException)
    assert exc.value.__cause__.detail == 'private_upload_busy'
    assert svc.receipt(command['request_id'], request(db, ids))['state'] == 'RECONCILIATION_REQUIRED'


def test_public_audit_surfaces_hide_uploads_even_with_bad_markers(upload_db):
    from app.api.activity import audit_catalog, AuditFilters, list_activity
    from app.api.dashboard import dashboard_summary
    from app.api.search import search_records
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == command['request_id'])))
    assert len(events) == 5
    events[0].event_type = 'UNKNOWN'
    events[1].event_no = 'some-other-marker'
    db.commit()
    assert list_activity(limit=50, db=db) == []
    assert audit_catalog(AuditFilters(), db)['total'] == 0
    assert dashboard_summary(db)['recent_activity'] == []
    assert not any(r['type'] == 'Activity' for r in search_records(db, 'Synthetic', 50))


def test_wrong_storage_namespace_rejected_without_io(upload_db):
    from app.services.private_upload_sessions import PrivateUploadService
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    wrong = PrivateUploadService(db, root='/must/not/access', storage_scope_id=uuid.uuid4(), max_bytes=1024, enabled=True)
    with pytest.raises(HTTPException): wrong.inspect(command['request_id'], request(db, ids))
    with pytest.raises(HTTPException): wrong.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('revision', [0, 1, 2, 3, 4])
@pytest.mark.parametrize('ack_lost', [False, True])
def test_every_database_commit_window_preserves_original_identity(upload_db, monkeypatch, revision, ack_lost):
    """A failed DB return is not treated as successful reservation/storage."""
    from app.models.upload import PrivateUploadSession
    db, ids, root = upload_db
    svc = service(db, root)
    command = values(svc, db, ids)
    original_commit = db.commit
    armed = True
    def interrupted_commit():
        nonlocal armed
        row = db.get(PrivateUploadSession, command['request_id'])
        if armed and row is not None and row.revision == revision:
            armed = False
            if ack_lost:
                original_commit()
            raise RuntimeError('synthetic lost database result')
        original_commit()
    monkeypatch.setattr(db, 'commit', interrupted_commit)
    if revision == 0:
        with pytest.raises(RuntimeError): svc.reserve(request=request(db, ids), **command)
        assert list(root.iterdir()) == []
        if ack_lost:
            status = svc.receipt(command['request_id'], request(db, ids))
            assert status['state'] == 'RESERVED'
        else:
            with pytest.raises(HTTPException) as exc: svc.receipt(command['request_id'], request(db, ids))
            assert exc.value.status_code == 404
        return
    reservation, _ = svc.reserve(request=request(db, ids), **command)
    with pytest.raises(RuntimeError): svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    status = svc.receipt(command['request_id'], request(db, ids))
    assert status['reservation'] == reservation
    if revision == 4 and ack_lost:
        assert status['state'] == 'STORED_PRIVATE' and status['stored_receipt'] is not None
    else:
        assert status['state'] != 'STORED_PRIVATE' and status['stored_receipt'] is None
    if revision == 1:
        assert list(root.iterdir()) == []
    elif revision in (2, 3):
        assert [p.suffix for p in root.iterdir()] == ['.part']
    else:
        assert sorted(p.suffix for p in root.iterdir()) == ['.blob', '.part']
    assert db.scalar(select(func.count()).select_from(Artifact)) == 0


@pytest.mark.parametrize('phase', ['receive', 'stage', 'publish', 'stored'])
def test_abrupt_interrupt_does_not_resume_a_durable_phase(upload_db, monkeypatch, phase):
    db, ids, root = upload_db
    svc = service(db, root)
    command, reservation = reserve(svc, db, ids)
    class Interrupted(BaseException): pass
    if phase == 'receive':
        def stop(*a): raise Interrupted()
        monkeypatch.setattr(svc._storage, 'stage', stop)
    elif phase == 'stage':
        stage = svc._storage.stage
        def stop(*args): stage(*args); raise Interrupted()
        monkeypatch.setattr(svc._storage, 'stage', stop)
    elif phase == 'publish':
        def stop(*a): raise Interrupted()
        monkeypatch.setattr(svc._storage, 'commit', stop)
    else:
        commit = svc._storage.commit
        def stop(*args): commit(*args); raise Interrupted()
        monkeypatch.setattr(svc._storage, 'commit', stop)
    with pytest.raises(Interrupted): svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    restart = service(db, root)
    status = restart.receipt(command['request_id'], request(db, ids))
    assert status['reservation'] == reservation and status['stored_receipt'] is None
    assert status['state'] in ('RECEIVING', 'PUBLISHING')
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(HTTPException): restart.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    observed = restart.inspect(command['request_id'], request(db, ids))
    assert observed['status'] == status
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.parametrize('kind', ['row_sha', 'context', 'reservation', 'stored', 'event', 'missing_event', 'boolean_version'])
def test_corrupt_evidence_fails_closed_and_never_repairs(upload_db, kind):
    from app.models.upload import PrivateUploadSession
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    row = db.get(PrivateUploadSession, command['request_id'])
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == svc._event_no(row.id, 4)))
    if kind == 'row_sha': row.sha256 = '0' * 64
    elif kind == 'context': row.context_json = {**row.context_json, 'project_id': str(uuid.uuid4())}
    elif kind == 'reservation': row.reservation_receipt_json = {**row.reservation_receipt_json, 'object_id': str(uuid.uuid4())}
    elif kind == 'stored': row.stored_receipt_json = {**row.stored_receipt_json, 'stored_at': '2020-01-01T00:00:00+00:00'}
    elif kind == 'event': event.payload_json = {**event.payload_json, 'from_state': 'RESERVED'}
    elif kind == 'missing_event': db.delete(event)
    else:
        event.payload_json = {**event.payload_json, 'version': True}
        flag_modified(event, 'payload_json')
    db.commit()
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(HTTPException): svc.receipt(command['request_id'], request(db, ids))
    with pytest.raises(HTTPException): svc.inspect(command['request_id'], request(db, ids))
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


def test_request_is_actor_bound_but_component_may_be_shared(upload_db):
    from test_application_release_creation import ISSUER
    from app.services.application_component_declaration import ApplicationComponentDeclarationService
    db, ids, root = upload_db
    svc = service(db, root)
    original_command, _ = reserve(svc, db, ids)
    other = SecurityPrincipal(issuer=ISSUER, subject='second-contributor', principal_type='USER', display_name='Other')
    db.add(other); db.flush()
    db.add_all([ProjectMembership(principal_id=other.id, project_id=ids['project'], role='CONTRIBUTOR'),
                SoftwareMembership(principal_id=other.id, software_id=ids['software'], role='SOFTWARE_VIEWER')])
    db.commit()
    other_ids = {**ids, 'actor': other.id}
    with pytest.raises(HTTPException): svc.receipt(original_command['request_id'], request(db, other_ids))
    with pytest.raises(HTTPException): svc.reserve(request=request(db, other_ids), **original_command)
    # Original declaration receipt remains creator-only; private upload context
    # independently validates the second contributor's exact current scope.
    with pytest.raises(HTTPException):
        ApplicationComponentDeclarationService(db).receipt(ids['component'], request(db, other_ids))
    own_command, own_receipt = reserve(svc, db, other_ids)
    assert own_receipt['actor_principal_id'] == str(other.id)
    assert svc.receive(own_command['request_id'], io.BytesIO(DATA), request(db, other_ids))['state'] == 'STORED_PRIVATE'


def test_receipts_preserve_original_success_after_parent_ineligibility(upload_db):
    db, ids, root = upload_db
    svc = service(db, root)
    command, original = reserve(svc, db, ids)
    stored = svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    db.get(Release, ids['release']).status = 'RELEASED'
    db.get(Release, ids['standard']).status = 'REVOKED'
    db.commit()
    assert svc.reserve(request=request(db, ids), **command) == (original, False)
    assert svc.receipt(command['request_id'], request(db, ids))['stored_receipt'] == stored


@pytest.mark.parametrize('target', ['audit_version', 'audit_revision', 'reservation_version',
                                  'stored_version', 'stored_revision', 'stored_size'])
@pytest.mark.parametrize('replacement', [True, 1.0])
def test_numeric_evidence_types_are_exact(upload_db, target, replacement):
    from app.models.upload import PrivateUploadSession
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids, b'x')
    svc.receive(command['request_id'], io.BytesIO(b'x'), request(db, ids))
    row = db.get(PrivateUploadSession, command['request_id'])
    if target.startswith('audit'):
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == svc._event_no(row.id, 1)))
        field = 'version' if target == 'audit_version' else 'revision'
        event.payload_json = {**event.payload_json, field: replacement}
        flag_modified(event, 'payload_json')
    elif target == 'reservation_version':
        row.reservation_receipt_json = {**row.reservation_receipt_json, 'version': replacement}
        flag_modified(row, 'reservation_receipt_json')
    else:
        field = {'stored_version': 'version', 'stored_revision': 'revision', 'stored_size': 'expected_bytes'}[target]
        if field == 'revision' and type(replacement) is float:
            replacement = 4.0
        row.stored_receipt_json = {**row.stored_receipt_json, field: replacement}
        flag_modified(row, 'stored_receipt_json')
    db.commit()
    with pytest.raises(HTTPException): svc.receipt(command['request_id'], request(db, ids))


@pytest.mark.parametrize('operation', ['receipt', 'inspect'])
@pytest.mark.parametrize('kind', ['principal', 'project', 'software', 'auth'])
def test_private_reads_recheck_scope_before_storage(upload_db, monkeypatch, operation, kind):
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    if kind == 'principal': db.get(SecurityPrincipal, ids['actor']).status = 'DISABLED'
    elif kind == 'project': db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
    elif kind == 'software': db.get(SoftwareMembership, ids['sm']).status = 'SUSPENDED'
    else: monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    db.commit()
    def forbidden(*args): raise AssertionError('unauthorized storage inspection')
    monkeypatch.setattr(svc._storage, 'inspect', forbidden)
    with pytest.raises(HTTPException) as exc:
        getattr(svc, operation)(command['request_id'], request(db, ids))
    assert exc.value.status_code in (401, 403) and not db.in_transaction()


def test_inspection_rechecks_revocation_after_filesystem_read(upload_db, monkeypatch):
    db, ids, root = upload_db
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    inspect = svc._storage.inspect
    def revoke(descriptor):
        assert not db.in_transaction()
        result = inspect(descriptor)
        db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
        db.commit()
        return result
    monkeypatch.setattr(svc._storage, 'inspect', revoke)
    with pytest.raises(HTTPException) as exc: svc.inspect(command['request_id'], request(db, ids))
    assert exc.value.status_code == 403


def test_capability_has_no_application_caller_or_http_route():
    from pathlib import Path
    from app.main import app
    root = Path(__file__).resolve().parents[1] / 'app'
    imports = [path for path in root.rglob('*.py')
               if path.name != 'private_upload_sessions.py' and
               ('import PrivateUploadService' in path.read_text() or
                'from app.services.private_upload_sessions' in path.read_text())]
    assert imports == []
    assert not any('upload' in route.path.lower() or 'download' in route.path.lower()
                   for route in app.routes if hasattr(route, 'path'))


def test_explicit_storage_limits_are_required_and_configuration_is_pinned(upload_db):
    from app.services.private_upload_sessions import PrivateUploadService
    db, ids, root = upload_db
    unconfigured = PrivateUploadService(db, root=str(root), enabled=True)
    with pytest.raises(HTTPException): unconfigured.context(ids['component'], request(db, ids))
    svc = service(db, root)
    command, _ = reserve(svc, db, ids)
    svc._storage.root = '/different/not/accessed'
    with pytest.raises(HTTPException): svc.receive(command['request_id'], io.BytesIO(DATA), request(db, ids))
    assert list(root.iterdir()) == []
