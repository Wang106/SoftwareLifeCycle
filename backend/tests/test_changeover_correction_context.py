"""Private context with synthetic signed bearer middleware, never a real provider."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker
from app import auth, main
from app.core.db import get_db
from app.models.security import BrowserSession, GlobalRoleAssignment, ProjectMembership, SecurityPrincipal
from app.services.changeover_correction_context import changeover_correction_context
from test_auth import AUDIENCE, signed_token
from test_production_correction_scope import correction_context, payload, post, stored  # noqa: F401
from test_command_concurrency_postgres import pg  # noqa: F401

ISSUER = 'https://synthetic.example'


@pytest.fixture
def private_context(correction_context, monkeypatch):
    ctx = correction_context
    sessions = sessionmaker(bind=ctx['engine'], expire_on_commit=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, 'jwks_client', lambda *_: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(auth, 'SessionLocal', sessions)
    monkeypatch.setattr(main.settings, 'oidc_issuer_url', ISSUER)
    monkeypatch.setattr(main.settings, 'oidc_audience', AUDIENCE)
    monkeypatch.setattr(main.settings, 'oidc_jwks_url', ISSUER + '/keys')
    monkeypatch.setattr(main.settings, 'oidc_leeway_seconds', 0)
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    token = signed_token(key, iss=ISSUER, sub='scope-operator')
    def route_db():
        with sessions() as db: yield db
    previous = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[get_db] = route_db
    try:
        with TestClient(main.app) as client:
            yield {**ctx, 'private_client': client, 'token': token, 'key': key,
                   'headers': {'Authorization': 'Bearer ' + token}}
    finally:
        main.app.dependency_overrides.clear(); main.app.dependency_overrides.update(previous)


def path(ctx, parent='owned', child=None):
    return f"/api/v1/deployments/{ctx['deps'][parent]}/changeovers/{child or ctx['children']['owned']['changeover']}/correction-context"


def get(ctx, **kw):
    return ctx['private_client'].get(path(ctx, **kw), headers=ctx['headers'])


def private(response):
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert 'authorization' in response.headers['vary'].lower()


def test_minimal_read_only_context(private_context):
    ctx = private_context; before = stored(ctx)
    response = get(ctx)
    assert response.status_code == 200, response.text
    private(response)
    assert 'x-browser-session' in response.headers['vary'].lower()
    data = response.json()
    assert set(data) == {'deployment_no','changeover_no','changeover_id','from_release_id','to_release_id','history_state',
                         'expected_revision','predecessor_id','changed_at','note'}
    assert data['deployment_no'] == ctx['deps']['owned'] and data['changeover_no'] == ctx['children']['owned']['changeover']
    assert data['history_state'] == 'NOT_RECORDED'
    assert data['expected_revision'] == 0 and data['predecessor_id'] is None
    started = datetime.fromisoformat(data['changed_at'])
    assert started.utcoffset() == timedelta(0)
    assert started == datetime(2026, 1, 1, tzinfo=timezone.utc)
    for forbidden in [ctx['token'], ISSUER, 'scope-operator', str(ctx['actor_id']), 'request_json', 'actor_principal_id']:
        assert forbidden not in response.text
    assert stored(ctx) == before
    response = ctx['private_client'].post(path(ctx).replace('/correction-context','/correction'), json={}, headers=ctx['headers'])
    assert response.status_code == 403 and response.json()['detail'] == 'read_only_mode'


@pytest.mark.parametrize('mode', ['disabled','missing','invalid'])
def test_requires_valid_oidc(private_context, monkeypatch, mode):
    ctx = private_context; before = stored(ctx); headers = ctx['headers']
    if mode == 'disabled': monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    elif mode == 'missing': headers = {}
    else: headers = {'Authorization': 'Bearer invalid'}
    response = ctx['private_client'].get(path(ctx), headers=headers)
    assert response.status_code == 401
    private(response)
    assert stored(ctx) == before


@pytest.mark.parametrize('target', ['foreign','sibling','missing'])
def test_mismatch_and_missing_share_404(private_context, target):
    ctx = private_context; before = stored(ctx)
    child = ctx['children'][target]['changeover'] if target != 'missing' else 'ABSENT'
    response = get(ctx, child=child)
    assert response.status_code == 404
    assert response.json() == {'detail': 'production correction target not found'}
    private(response)
    assert stored(ctx) == before


def test_forbidden_parent_never_reaches_projection(private_context, monkeypatch):
    ctx = private_context
    import app.services.changeover_correction_context as projection
    monkeypatch.setattr(projection, 'changeover_correction_context', lambda *_: pytest.fail('forbidden scope reached projection'))
    response = get(ctx, parent='foreign', child=ctx['children']['foreign']['changeover'])
    assert response.status_code == 403
    private(response)


@pytest.mark.parametrize('revoked', ['membership','principal'])
def test_revoked_scope_or_principal(private_context, revoked):
    ctx = private_context
    assert get(ctx).status_code == 200
    with Session(ctx['engine']) as db:
        row = db.get(ProjectMembership, ctx['grant_id']) if revoked == 'membership' else db.get(SecurityPrincipal, ctx['actor_id'])
        row.status = 'SUSPENDED' if revoked == 'membership' else 'DISABLED'; db.commit()
    response = get(ctx)
    assert response.status_code == (403 if revoked == 'membership' else 401)
    private(response)


def test_browser_session_binding_and_revocation(private_context):
    ctx = private_context; sid = uuid.uuid4(); now = datetime.now(timezone.utc)
    with Session(ctx['engine']) as db:
        db.add(BrowserSession(id=sid, principal_id=ctx['actor_id'],
            token_digest=hashlib.sha256(ctx['token'].encode()).hexdigest(),
            created_at=now, expires_at=now+timedelta(minutes=2))); db.commit()
    headers = {**ctx['headers'], 'X-Browser-Session': str(sid)}
    assert ctx['private_client'].get(path(ctx), headers=headers).status_code == 200
    other = signed_token(ctx['key'], iss=ISSUER, sub='scope-operator', jti='different-token')
    assert ctx['private_client'].get(path(ctx), headers={**headers,'Authorization':'Bearer '+other}).status_code == 401
    with Session(ctx['engine']) as db:
        db.get(BrowserSession, sid).revoked_at = now; db.commit()
    response = ctx['private_client'].get(path(ctx), headers=headers)
    assert response.status_code == 401 and response.json()['detail'] == 'invalid_browser_session'
    private(response)
    assert get(ctx).status_code == 200  # Revoking a browser session does not revoke the provider bearer token.


def test_head_and_effective_values(private_context):
    ctx = private_context; body = payload(ctx, 'changeover'); body['note'] = 'corrected current value'
    assert post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body).status_code == 200
    before = stored(ctx); data = get(ctx).json()
    assert data['expected_revision'] == 1 and data['predecessor_id'] == body['request_id']
    assert data['note'] == body['note'] and data['history_state'] == 'IMPORTED_CORRECTED'
    assert stored(ctx) == before


def test_admin_still_requires_matching_parent(private_context):
    ctx = private_context
    with Session(ctx['engine']) as db:
        db.add(GlobalRoleAssignment(principal_id=ctx['actor_id'], role='PLATFORM_ADMIN')); db.commit()
    assert get(ctx, parent='foreign', child=ctx['children']['foreign']['changeover']).status_code == 200
    assert get(ctx, child=ctx['children']['foreign']['changeover']).status_code == 404


def test_one_bounded_projection_statement(private_context):
    ctx = private_context; statements = []
    def record(_conn, _cursor, statement, _params, _context, _many): statements.append(statement)
    event.listen(ctx['engine'], 'before_cursor_execute', record)
    try:
        with Session(ctx['engine']) as db:
            value = changeover_correction_context(db, ctx['deps']['owned'], ctx['children']['owned']['changeover'])
    finally: event.remove(ctx['engine'], 'before_cursor_execute', record)
    assert value is not None and len(statements) == 1 and 'LIMIT' in statements[0]
    assert all(name not in statements[0] for name in ('request_json','actor_name','actor_principal_id','FOR UPDATE'))


@pytest.mark.parametrize('suffix,method,status', [('', 'HEAD', 405), ('/', 'GET', 307)])
def test_private_headers_cover_method_and_redirect(private_context, suffix, method, status):
    ctx = private_context
    response = ctx['private_client'].request(method, path(ctx)+suffix, headers=ctx['headers'], follow_redirects=False)
    assert response.status_code == status
    private(response)
    assert 'x-browser-session' in response.headers['vary'].lower()


def test_service_principal_keeps_existing_exact_role_contract(private_context):
    ctx = private_context
    with Session(ctx['engine']) as db:
        db.get(SecurityPrincipal, ctx['actor_id']).principal_type = 'SERVICE'; db.commit()
    assert get(ctx).status_code == 200


def test_new_correction_audit_binds_canonical_parent(private_context):
    from app.models.audit import AuditEvent
    from sqlalchemy import select
    ctx = private_context; body = payload(ctx, 'changeover')
    assert post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body).status_code == 200
    with Session(ctx['engine']) as db:
        audit = db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-CC-'+uuid.UUID(body['request_id']).hex))
        assert audit.payload_json['deployment_no'] == ctx['deps']['owned']
        assert 'deployment_no' not in audit.payload_json['request']
    before = stored(ctx)
    assert post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body).status_code == 200
    assert stored(ctx) == before


def test_legacy_audit_replay_remains_original_without_parent(private_context, monkeypatch):
    import app.services.production as service
    from app.models.audit import AuditEvent
    from sqlalchemy import select
    ctx = private_context; body = payload(ctx, 'changeover'); original = service.commit_with_audit
    # Generate a synthetic old-format event at creation; never update stored audit history.
    def old_format(db, factory):
        def event_factory():
            value = factory(); value['payload'].pop('deployment_no', None); return value
        return original(db, event_factory)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'commit_with_audit', old_format)
        first = post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body)
    assert first.status_code == 200, first.text
    before = stored(ctx)
    replay = post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert stored(ctx) == before
    with Session(ctx['engine']) as db:
        audit = db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-CC-'+uuid.UUID(body['request_id']).hex))
        assert 'deployment_no' not in audit.payload_json


@pytest.mark.parametrize('correction_context', ['postgres'], indirect=True)
def test_concurrent_append_cannot_mix_context_revision_and_values(private_context):
    from app.services.production import ProductionService
    ctx = private_context; first = payload(ctx, 'changeover'); first['note'] = 'first version'
    assert post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], first).status_code == 200
    second = uuid.uuid4(); appended = False
    def append_after_statement(_conn, _cursor, statement, _params, _context, _many):
        nonlocal appended
        if appended or not statement.startswith('SELECT software_changeovers.id AS changeover_id'):
            return
        appended = True
        with Session(ctx['engine']) as db:
            ProductionService(db).correct_changeover(ctx['children']['owned']['changeover'], from_release_id=ctx['source_id'],
                changed_at=datetime(2026, 1, 3, tzinfo=timezone.utc), request_id=second,
                expected_revision=1, predecessor_id=uuid.UUID(first['request_id']),
                correction_reason='concurrent context', note='second version')
    event.listen(ctx['engine'], 'after_cursor_execute', append_after_statement)
    try: response = get(ctx)
    finally: event.remove(ctx['engine'], 'after_cursor_execute', append_after_statement)
    assert appended and response.status_code == 200, response.text
    data = response.json()
    assert data['expected_revision'] == 1 and data['predecessor_id'] == first['request_id']
    assert data['note'] == 'first version'
    fresh = get(ctx).json()
    assert fresh['expected_revision'] == 2 and fresh['predecessor_id'] == str(second)
    assert fresh['note'] == 'second version'


def test_source_time_note_replace_but_target_and_recorded_facts_stay(private_context):
    from app.models.core import Release
    from app.models.production import SoftwareChangeover
    from app.models.production_history import ChangeoverBaseline
    from sqlalchemy import select
    ctx = private_context; initial = get(ctx).json()
    with Session(ctx['engine']) as db:
        source = db.get(Release, ctx['source_id'])
        replacement = Release(software_id=source.software_id, release_type='STANDARD', version='replacement-source')
        db.add(replacement); db.commit(); replacement_id = replacement.id
    first = payload(ctx, 'changeover', from_release_id=str(replacement_id),
                    changed_at='2026-02-01T02:30:00Z', note=None)
    result = post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], first)
    assert result.status_code == 200, result.text
    current = get(ctx).json()
    assert current['from_release_id'] == str(replacement_id)
    assert current['to_release_id'] == initial['to_release_id']
    assert current['note'] is None
    assert datetime.fromisoformat(current['changed_at']) == datetime(2026, 2, 1, 2, 30, tzinfo=timezone.utc)
    with Session(ctx['engine']) as db:
        physical = db.scalar(select(SoftwareChangeover).where(SoftwareChangeover.changeover_no == initial['changeover_no']))
        baseline = db.scalar(select(ChangeoverBaseline).where(ChangeoverBaseline.changeover_id == physical.id))
        assert physical.from_release_id == baseline.from_release_id == ctx['source_id']
        assert str(physical.to_release_id) == str(baseline.to_release_id) == initial['to_release_id']
    second = payload(ctx, 'changeover', expected_revision=1, predecessor_id=first['request_id'],
                     changed_at=None, note='explicit second')
    before = datetime.now(timezone.utc)
    assert post(ctx, 'changeover', 'owned', initial['changeover_no'], second).status_code == 200
    after = datetime.now(timezone.utc); current = get(ctx).json()
    assert before <= datetime.fromisoformat(current['changed_at']) <= after
    assert current['expected_revision'] == 2 and current['predecessor_id'] == second['request_id']
    assert current['to_release_id'] == initial['to_release_id']


@pytest.mark.parametrize('correction_context', ['postgres'], indirect=True)
def test_non_utc_command_time_roundtrips_as_same_instant(private_context):
    ctx = private_context
    body = payload(ctx, 'changeover', changed_at='2026-02-01T10:30:00+08:00')
    response = post(ctx, 'changeover', 'owned', ctx['children']['owned']['changeover'], body)
    assert response.status_code == 200, response.text
    value = datetime.fromisoformat(get(ctx).json()['changed_at'])
    assert value.utcoffset() == timedelta(0)
    assert value == datetime(2026, 2, 1, 2, 30, tzinfo=timezone.utc)


def test_unrecorded_original_time_can_be_null(private_context):
    from app.models.production import SoftwareChangeover
    from sqlalchemy import select
    ctx = private_context
    with Session(ctx['engine']) as db:
        row = db.scalar(select(SoftwareChangeover).where(
            SoftwareChangeover.changeover_no == ctx['children']['owned']['changeover']))
        row.changed_at = None
        db.commit()
    before = stored(ctx)
    response = get(ctx)
    assert response.status_code == 200, response.text
    assert response.json()['changed_at'] is None
    assert response.json()['history_state'] == 'NOT_RECORDED'
    assert stored(ctx) == before
