"""Strict empty ASR creation; synthetic SQLite is not PostgreSQL acceptance."""
import uuid
from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, MetaData, create_engine, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import app.models
from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.core.db import Base
from app.models.core import (Supplier, Customer, Project, SoftwareProduct, Release,
                             StandardReleaseDetail, ApplicationReleaseDetail, ReleaseComponent, Artifact)
from app.models.audit import AuditEvent
from app.models.security import SecurityPrincipal, ProjectMembership, SoftwareMembership, BrowserSession, GlobalRoleAssignment
from app.models.snapshot import ReleaseSnapshot

ISSUER = 'https://asr.synthetic.example'
TOKEN = 'synthetic-token'


def configure(monkeypatch):
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    monkeypatch.setattr(settings, 'oidc_issuer_url', ISSUER)
    monkeypatch.setattr(settings, 'read_only_mode', False)


def seed(db):
    supplier = Supplier(code='ASR-S', name='Supplier')
    customer = Customer(code='ASR-C', name='Customer')
    db.add_all([supplier, customer]); db.flush()
    software = SoftwareProduct(supplier_id=supplier.id, code='ASR-SW', name='Software')
    project = Project(customer_id=customer.id, project_code='ASR-P', name='Project')
    other = Project(customer_id=customer.id, project_code='ASR-P2', name='Other project')
    actor = SecurityPrincipal(issuer=ISSUER, subject='creator', principal_type='USER', display_name='Creator')
    db.add_all([software, project, other, actor]); db.flush()
    standard = Release(software_id=software.id, release_type='STANDARD', version='base-1', status='DRAFT')
    db.add(standard); db.flush(); db.add(StandardReleaseDetail(release_id=standard.id))
    pm = ProjectMembership(principal_id=actor.id, project_id=project.id, role='CONTRIBUTOR')
    sm = SoftwareMembership(principal_id=actor.id, software_id=software.id, role='SOFTWARE_VIEWER')
    db.add_all([pm, sm, ProjectMembership(principal_id=actor.id, project_id=other.id, role='CONTRIBUTOR')]); db.commit()
    return dict(project=project.id, other=other.id, customer=customer.id, software=software.id,
                standard=standard.id, actor=actor.id, pm=pm.id, sm=sm.id)


def request(db, ids, sid=None):
    actor = db.get(SecurityPrincipal, ids['actor'])
    headers = [(b'authorization', ('Bearer '+TOKEN).encode())]
    if sid: headers.append((b'x-browser-session', str(sid).encode()))
    req = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': headers})
    req.state.principal = AuthenticatedPrincipal(actor.id, actor.issuer, actor.subject, actor.principal_type, actor.display_name, actor.email)
    return req


def service(db):
    from app.services.application_release_creation import ApplicationReleaseCreationService
    return ApplicationReleaseCreationService(db)


def context(db, ids):
    return service(db).context(ids['project'], ids['standard'], request(db, ids))


def body(db, ids):
    return dict(request_id=uuid.uuid4(), project_id=ids['project'], standard_base_release_id=ids['standard'],
                version='app-1', release_notes='  original notes\n', reason='Create empty draft',
                expected_context_digest=context(db, ids)['context_digest'])


def submit(db, ids, values, req=None):
    return service(db).create(request=req or request(db, ids), **values)


@pytest.fixture
def creation_db(monkeypatch):
    configure(monkeypatch)
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for col in copied.columns:
            if isinstance(col.type, JSONB): col.type = JSON()
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db: yield db, seed(db)
    engine.dispose()


def test_context_and_creation_are_exact_empty_and_atomic(creation_db):
    db, ids = creation_db
    info = context(db, ids)
    assert info['context']['standard_base_status'] == 'DRAFT'
    assert info['context']['customer_id'] == str(ids['customer'])
    assert not db.in_transaction()
    values = body(db, ids); result, created = submit(db, ids, values)
    assert created is True and result['applied_status'] == 'DRAFT'
    row = db.get(Release, values['request_id']); detail = db.get(ApplicationReleaseDetail, row.id)
    assert (row.release_type, row.status, row.customer_scope_id, row.software_id) == ('APPLICATION', 'DRAFT', ids['customer'], ids['software'])
    assert detail.project_id == ids['project'] and detail.standard_base_release_id == ids['standard']
    assert detail.previous_application_release_id is None and row.release_notes == values['release_notes']
    for model in (ReleaseComponent, Artifact, ReleaseSnapshot): assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
    assert submit(db, ids, values) == (result, False)
    assert service(db).receipt(values['request_id'], request(db, ids)) == result
    from app.services.snapshot import SnapshotService, SnapshotError
    with pytest.raises(SnapshotError, match='Release has no artifacts'):
        SnapshotService().create(db, values['request_id'])
    assert db.scalar(select(func.count()).select_from(ReleaseSnapshot)) == 0


@pytest.mark.parametrize('kind', ['project', 'software', 'principal', 'service', 'admin_only', 'disabled_mode', 'readonly'])
def test_current_authority_checked_before_replay(creation_db, monkeypatch, kind):
    db, ids = creation_db; values = body(db, ids); submit(db, ids, values)
    if kind == 'project': db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
    elif kind == 'software': db.get(SoftwareMembership, ids['sm']).status = 'SUSPENDED'
    elif kind == 'principal': db.get(SecurityPrincipal, ids['actor']).status = 'DISABLED'
    elif kind == 'service': db.get(SecurityPrincipal, ids['actor']).principal_type = 'SERVICE'
    elif kind == 'admin_only':
        db.get(ProjectMembership, ids['pm']).status = 'SUSPENDED'
        db.add(GlobalRoleAssignment(principal_id=ids['actor'], role='PLATFORM_ADMIN'))
    elif kind == 'disabled_mode': monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    else: monkeypatch.setattr(settings, 'read_only_mode', True)
    db.commit()
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.status_code in (401,403) and not db.in_transaction()


@pytest.mark.parametrize('kind', ['revoked', 'expired', 'token', 'principal'])
def test_browser_claim_checked_before_replay(creation_db, kind):
    db, ids = creation_db; values = body(db, ids); submit(db, ids, values)
    now = datetime.now(timezone.utc); sid = uuid.uuid4()
    db.add(BrowserSession(id=sid, principal_id=uuid.uuid4() if kind == 'principal' else ids['actor'],
        token_digest=hashlib.sha256((TOKEN+'x' if kind == 'token' else TOKEN).encode()).hexdigest(),
        created_at=now-timedelta(minutes=5), expires_at=now+timedelta(minutes=-1 if kind == 'expired' else 5),
        revoked_at=now if kind == 'revoked' else None)); db.commit()
    with pytest.raises(HTTPException) as exc: submit(db, ids, values, request(db, ids, sid))
    assert exc.value.status_code == 401


@pytest.mark.parametrize('kind', ['project', 'customer', 'software', 'standard_type', 'standard_revoked', 'standard_missing', 'detail_missing'])
def test_fresh_ineligible_parents_rejected(creation_db, kind):
    db, ids = creation_db; values = body(db, ids)
    if kind in ('project','customer','software'):
        db.get({'project':Project,'customer':Customer,'software':SoftwareProduct}[kind], ids[kind]).status = 'INACTIVE'
    elif kind == 'standard_type': db.get(Release, ids['standard']).release_type = 'APPLICATION'
    elif kind == 'standard_revoked': db.get(Release, ids['standard']).status = 'REVOKED'
    elif kind == 'standard_missing': values['standard_base_release_id'] = uuid.uuid4()
    else: db.delete(db.get(StandardReleaseDetail, ids['standard']))
    db.commit()
    with pytest.raises(HTTPException): submit(db, ids, values)
    assert db.get(Release, values['request_id']) is None


@pytest.mark.parametrize('legacy', [True, False])
def test_same_customer_other_project_duplicate_and_legacy_conflict(creation_db, legacy):
    db, ids = creation_db; values = body(db, ids)
    row = Release(software_id=ids['software'], customer_scope_id=None if legacy else ids['customer'], release_type='APPLICATION', version=values['version'])
    db.add(row); db.flush(); db.add(ApplicationReleaseDetail(release_id=row.id, project_id=ids['other'], customer_id=ids['customer'], standard_base_release_id=ids['standard'])); db.commit()
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.status_code == 409


def test_context_change_conflicts_but_history_preserves_original_draft(creation_db):
    db, ids = creation_db; values = body(db, ids)
    db.get(Release, ids['standard']).status = 'RELEASED'; db.commit()
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.detail == 'asr_context_conflict'
    values = body(db, ids); original, _ = submit(db, ids, values)
    db.get(Release, ids['standard']).status = 'REVOKED'; db.get(Release, values['request_id']).status = 'RELEASED'; db.commit()
    assert submit(db, ids, values) == (original, False)
    assert service(db).receipt(values['request_id'], request(db, ids)) == original
    assert original['applied_status'] == 'DRAFT' and original['standard_base_status'] == 'RELEASED'


@pytest.mark.parametrize('kind', ['reason','version','notes','context','actor','audit','binding'])
def test_reuse_or_malformed_evidence_is_conflict(creation_db, kind):
    db, ids = creation_db; values = body(db, ids); submit(db, ids, values)
    if kind in ('reason','version'): values[kind] += 'changed'
    elif kind == 'notes': values['release_notes'] = 'changed'
    elif kind == 'context': values['expected_context_digest'] = 'f'*64
    elif kind == 'actor':
        event = db.scalar(select(AuditEvent)); event.actor_principal_id = uuid.uuid4(); db.commit()
    elif kind == 'audit':
        event = db.scalar(select(AuditEvent)); event.payload_json = {'receipt': {'applied_status':'DRAFT'}}; db.commit()
    else: db.get(ApplicationReleaseDetail, values['request_id']).project_id = ids['other']; db.commit()
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.status_code == 409 and not db.in_transaction()


@pytest.mark.parametrize('point', ['audit','commit'])
def test_failure_rolls_back_domain_detail_and_audit(creation_db, monkeypatch, point):
    db, ids = creation_db; values = body(db, ids)
    def broken(*args, **kwargs): raise RuntimeError('synthetic failure')
    if point == 'audit':
        from app.services.audit import AuditEventService
        monkeypatch.setattr(AuditEventService, 'record', broken)
    else: monkeypatch.setattr(db, 'commit', broken)
    with pytest.raises(RuntimeError): submit(db, ids, values)
    assert not db.in_transaction()
    assert db.get(Release, values['request_id']) is None
    assert db.get(ApplicationReleaseDetail, values['request_id']) is None
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize('field,value', [('version',' x'),('version','x'*101),('version',1),('reason',''),('reason','x'*4001),('release_notes','x'*4001),('expected_context_digest','A'*64),('customer_id',str(uuid.uuid4()))])
def test_body_strict_canonical_validation(creation_db, field, value):
    from app.api.application_release_creation import CreateApplicationRelease
    from pydantic import ValidationError
    db, ids = creation_db; values = body(db, ids); values[field] = value
    with pytest.raises(ValidationError): CreateApplicationRelease(**values)


@pytest.mark.parametrize('field,value', [('event_type','APPLICATION_RELEASE_CREATED'), ('event_no','EVT-ASR-legacy'), ('event_no','evt-asr-mixed')])
def test_creation_audit_never_leaks_through_public_reads(creation_db, field, value):
    from app.api.activity import get_activity, list_activity, audit_catalog, AuditFilters
    from app.api.search import search_records
    from app.api.dashboard import dashboard_summary
    db, ids = creation_db; values = body(db, ids); result, _ = submit(db, ids, values)
    event = db.scalar(select(AuditEvent)); setattr(event, field, value); db.commit()
    with pytest.raises(HTTPException) as exc: get_activity(event.event_no, db)
    assert exc.value.status_code == 404
    assert list_activity(limit=50, db=db) == []
    catalog = audit_catalog(AuditFilters(), db)
    assert catalog['total'] == 0 and catalog['items'] == [] and catalog['event_type_counts'] == {}
    assert not any(row['type'] == 'Activity' for row in search_records(db, event.event_no, 50))
    assert dashboard_summary(db)['recent_activity'] == []


def formal_standard(db, ids):
    from app.models.approval import ApprovalRequest, ReleaseDecision
    snapshot = ReleaseSnapshot(release_id=ids['standard'], snapshot_no='ASR-SSR-SNAP', snapshot_number=1, status='FROZEN', content_hash='a'*64)
    db.add(snapshot); db.flush()
    approval = ApprovalRequest(approval_no='ASR-SSR-APR', target_type='RELEASE', target_id=ids['standard'], snapshot_id=snapshot.id, status='APPROVED')
    db.add(approval); db.flush()
    decision = ReleaseDecision(decision_no='ASR-SSR-RD', release_id=ids['standard'], snapshot_id=snapshot.id,
        approval_request_id=approval.id, readiness_status='READY', decision='RELEASE', decided_by='Synthetic reviewer')
    db.add(decision); db.commit()


def test_actual_chain_revocation_rejects_new_work_without_changing_status(creation_db):
    from app.services.revocation import RevocationService
    db, ids = creation_db; formal_standard(db, ids); values = body(db, ids)
    RevocationService(db).revoke('RELEASE', ids['standard'], 'Synthetic revocation', request_id=uuid.uuid4())
    assert db.get(Release, ids['standard']).status == 'DRAFT'
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.detail == 'standard_release_revoked'


def test_different_customer_may_use_same_version(creation_db):
    db, ids = creation_db; values = body(db, ids); submit(db, ids, values)
    customer = Customer(code='ASR-OTHER', name='Other'); db.add(customer); db.flush()
    project = Project(customer_id=customer.id, project_code='ASR-OTHER', name='Other'); db.add(project); db.flush()
    db.add(ProjectMembership(principal_id=ids['actor'], project_id=project.id, role='CONTRIBUTOR')); db.commit()
    other = {**ids, 'project':project.id, 'customer':customer.id}
    result, created = submit(db, other, body(db, other))
    assert created and result['customer_id'] == str(customer.id)


@pytest.fixture
def creation_client(creation_db, monkeypatch):
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import auth, main
    from app.core.db import get_db
    from test_auth import AUDIENCE, signed_token
    db, ids = creation_db; sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, 'jwks_client', lambda *_:SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(auth, 'SessionLocal', sessions)
    for name, value in {'oidc_audience':AUDIENCE, 'oidc_jwks_url':ISSUER+'/keys','oidc_leeway_seconds':0}.items(): monkeypatch.setattr(settings, name, value)
    token = signed_token(key, iss=ISSUER, sub='creator')
    def route_db():
        with sessions() as route_session: yield route_session
    previous = dict(main.app.dependency_overrides); main.app.dependency_overrides[get_db] = route_db
    try:
        with TestClient(main.app) as client: yield client, {'Authorization':'Bearer '+token}, ids
    finally: main.app.dependency_overrides.clear(); main.app.dependency_overrides.update(previous)


def test_signed_http_context_create_replay_receipt_and_public_exclusion(creation_client):
    client, headers, ids = creation_client
    path = '/api/v1/application-release-creation'
    context = client.get(path+'/context', params={'project_id':str(ids['project']), 'standard_base_release_id':str(ids['standard'])}, headers=headers)
    assert context.status_code == 200, context.text
    data = dict(request_id=str(uuid.uuid4()), project_id=str(ids['project']), standard_base_release_id=str(ids['standard']),
        version='new-http', release_notes=None, reason='HTTP synthetic', expected_context_digest=context.json()['context_digest'])
    new = client.post('/api/v1/releases/application', json=data, headers=headers)
    assert new.status_code == 201, new.text
    again = client.post('/api/v1/releases/application', json=data, headers=headers)
    assert again.status_code == 200 and again.json() == new.json()
    receipt = client.get(path+'/receipts/'+data['request_id'], headers=headers)
    assert receipt.status_code == 200 and receipt.json() == new.json()
    for response in (context, new, again, receipt):
        assert response.headers['cache-control'] == 'private, no-store'
        assert 'x-browser-session' in response.headers['vary'].lower()
    assert client.get(path+'/receipts/'+data['request_id']).status_code == 401
    assert client.get('/api/v1/activity/'+new.json()['audit_event_no']).status_code == 404


@pytest.mark.parametrize('field,value', [('version','a\nb'), ('version','a\tb'), ('version','a\x7fb'),
    ('reason','a\rb'), ('reason','a\x85b'), ('release_notes','a\x01b'), ('release_notes','a\ud800b'),
    ('reason','a\udfffb'), ('version','a\ud800b')])
def test_control_characters_and_surrogates_fail_before_database(creation_db, field, value):
    db, ids = creation_db; values = body(db, ids); values[field] = value
    with pytest.raises(HTTPException) as exc: submit(db, ids, values)
    assert exc.value.status_code == 422 and not db.in_transaction()
    assert db.get(Release, values['request_id']) is None


def test_unicode_emoji_notes_and_multiline_reason_preserved(creation_db):
    db, ids = creation_db; values = {**body(db, ids), 'version':'应用😀', 'reason':'Reason\n\t继续😀', 'release_notes':'\n\t原样😀'}
    receipt, _ = submit(db, ids, values)
    assert all(receipt[key] == values[key] for key in ('version','reason','release_notes'))
    assert service(db).receipt(values['request_id'], request(db, ids)) == receipt


@pytest.mark.parametrize('auth_mode', ['disabled', 'oidc'])
@pytest.mark.parametrize('method,suffix,expected', [('GET','',410), ('GET','/',410), ('HEAD','',405), ('HEAD','/',405)])
def test_existing_application_catalogue_remains_public(creation_client, monkeypatch, method, suffix, expected, auth_mode):
    from app import main
    client, _headers, _ids = creation_client
    monkeypatch.setattr(settings, 'auth_mode', auth_mode)
    monkeypatch.setattr(settings, 'read_only_mode', True)
    def forbidden(*args): raise AssertionError('public catalogue must not authenticate')
    monkeypatch.setattr(main, 'authenticate_write_request', forbidden)
    response = client.request(method, '/api/v1/releases/application'+suffix)
    assert response.status_code == expected, response.text
    assert response.headers.get('cache-control') != 'private, no-store'
    if method == 'GET':
        assert response.json()['detail'] == 'legacy_read_retired'
        assert response.json()['replacements'] == ['/api/v1/release-catalog/application']
    catalog = client.get('/api/v1/release-catalog/application')
    assert catalog.status_code == 200 and 'items' in catalog.json()


def options(db, ids, **kw):
    return service(db).standard_options(ids['project'], request(db, ids), **kw)


def test_standard_options_pagination_visibility_and_no_writes(creation_db):
    db, ids = creation_db
    # DRAFT is deliberately eligible; status is information, not release authority.
    for n in range(3):
        r = Release(software_id=ids['software'], release_type='STANDARD', version='page-'+str(n), status='READY')
        db.add(r); db.flush(); db.add(StandardReleaseDetail(release_id=r.id))
    hidden = SoftwareProduct(supplier_id=db.get(SoftwareProduct, ids['software']).supplier_id, code='HIDDEN', name='Private')
    db.add(hidden); db.flush()
    secret = Release(software_id=hidden.id, release_type='STANDARD', version='secret', status='RELEASED')
    db.add(secret); db.flush(); db.add(StandardReleaseDetail(release_id=secret.id)); db.commit()
    page = options(db, ids, limit=2)
    assert page['project_id'] == str(ids['project']) and len(page['items']) == 2
    assert page['next_after'] == page['items'][-1]['standard_base_release_id']
    second = options(db, ids, limit=2, after=uuid.UUID(page['next_after']))
    all_items = page['items'] + second['items']
    assert second['next_after'] is None
    assert len({r['standard_base_release_id'] for r in all_items}) == 4
    assert all(r['software_id'] == str(ids['software']) for r in all_items)
    assert any(r['standard_base_status'] == 'DRAFT' for r in all_items)
    assert all(r['software_name'] == 'Software' for r in all_items)
    for cursor in (secret.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as exc: options(db, ids, after=cursor)
        assert exc.value.detail == 'invalid_options_cursor'
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize('kind', ['project_grant', 'project', 'customer', 'software', 'software_grant', 'standard', 'detail', 'principal'])
def test_standard_options_rechecks_current_authority_and_parents(creation_db, kind):
    db, ids = creation_db
    assert len(options(db, ids)['items']) == 1
    if kind == 'detail': db.delete(db.get(StandardReleaseDetail, ids['standard']))
    else:
        model, key, status = {'project_grant':(ProjectMembership,'pm','SUSPENDED'), 'project':(Project,'project','INACTIVE'),
            'customer':(Customer,'customer','INACTIVE'), 'software':(SoftwareProduct,'software','INACTIVE'),
            'software_grant':(SoftwareMembership,'sm','SUSPENDED'), 'standard':(Release,'standard','REVOKED'),
            'principal':(SecurityPrincipal,'actor','DISABLED')}[kind]
        db.get(model, ids[key]).status = status
    db.commit()
    if kind in ('project_grant','project','customer','principal'):
        with pytest.raises(HTTPException): options(db, ids)
    else:
        assert options(db, ids)['items'] == []
        with pytest.raises(HTTPException) as exc: options(db, ids, after=ids['standard'])
        assert exc.value.detail == 'invalid_options_cursor'
    assert not db.in_transaction()


@pytest.mark.parametrize('limit', [0,51,-1,True,'2'])
def test_standard_options_reject_invalid_limit(creation_db, limit):
    db, ids = creation_db
    with pytest.raises(HTTPException) as exc: options(db, ids, limit=limit)
    assert exc.value.status_code == 422


def test_standard_options_no_cross_project_grant_or_nonstandard_leak(creation_db):
    db, ids = creation_db
    other = db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == ids['other']))
    other.status = 'SUSPENDED'
    wrong = Release(software_id=ids['software'], release_type='APPLICATION', version='not-SSR', status='DRAFT')
    missing = Release(software_id=ids['software'], release_type='STANDARD', version='no-detail', status='DRAFT')
    db.add_all([wrong, missing]); db.flush(); db.add(StandardReleaseDetail(release_id=wrong.id)); db.commit()
    assert [x['standard_base_release_id'] for x in options(db, ids)['items']] == [str(ids['standard'])]
    with pytest.raises(HTTPException) as exc:
        service(db).standard_options(ids['other'], request(db, ids))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException): service(db).standard_options(uuid.uuid4(), request(db, ids))


def test_standard_options_chain_revocation_without_status_change(creation_db):
    from app.services.revocation import RevocationService
    db, ids = creation_db; formal_standard(db, ids)
    RevocationService(db).revoke('RELEASE', ids['standard'], 'Synthetic revocation', request_id=uuid.uuid4())
    assert db.get(Release, ids['standard']).status == 'DRAFT'
    assert options(db, ids)['items'] == []


def test_standard_options_missing_browser_session_is_denied(creation_db):
    db, ids = creation_db
    with pytest.raises(HTTPException) as exc:
        service(db).standard_options(ids['project'], request(db, ids, uuid.uuid4()))
    assert exc.value.status_code == 401
    assert not db.in_transaction()


@pytest.mark.parametrize('kind', ['revoked', 'expired', 'token', 'principal'])
def test_standard_options_rechecks_browser_session(creation_db, kind):
    db, ids = creation_db
    now = datetime.now(timezone.utc); sid = uuid.uuid4()
    db.add(BrowserSession(id=sid, principal_id=uuid.uuid4() if kind == 'principal' else ids['actor'],
        token_digest=hashlib.sha256((TOKEN+'x' if kind == 'token' else TOKEN).encode()).hexdigest(),
        created_at=now-timedelta(minutes=5), expires_at=now+timedelta(minutes=-1 if kind == 'expired' else 5),
        revoked_at=now if kind == 'revoked' else None)); db.commit()
    with pytest.raises(HTTPException) as exc:
        service(db).standard_options(ids['project'], request(db, ids, sid))
    assert exc.value.status_code == 401 and not db.in_transaction()
