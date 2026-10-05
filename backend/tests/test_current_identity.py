"""Authenticated self reads must not expose another principal or imply write authority."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, main
from app.core.db import Base, get_db
from app.models.audit import AuditEvent
from app.models.core import Customer, Project, SoftwareProduct, Supplier
from app.models.security import BrowserSession, GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from test_auth import ISSUER, AUDIENCE, signed_token
from test_command_concurrency_postgres import pg


@pytest.fixture(params=['sqlite', 'postgres'])
def identity_client(monkeypatch, request):
    if request.param == 'postgres':
        engine, _ = request.getfixturevalue('pg')
    else:
        engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        monkeypatch.setattr(AuditEvent.__table__.c.payload_json, 'type', JSONB().with_variant(JSON(), 'sqlite'))
        Base.metadata.create_all(engine, tables=[model.__table__ for model in (
            SecurityPrincipal, BrowserSession, GlobalRoleAssignment, ProjectMembership, SoftwareMembership,
            Supplier, Customer, Project, SoftwareProduct, AuditEvent,
        )])
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, 'jwks_client', lambda *_: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(auth, 'SessionLocal', sessions)
    monkeypatch.setattr(main.settings, 'auth_mode', 'oidc')
    monkeypatch.setattr(main.settings, 'oidc_issuer_url', ISSUER)
    monkeypatch.setattr(main.settings, 'oidc_audience', AUDIENCE)
    monkeypatch.setattr(main.settings, 'oidc_jwks_url', ISSUER+'/keys')
    monkeypatch.setattr(main.settings, 'oidc_leeway_seconds', 0)
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    with sessions() as db:
        person = SecurityPrincipal(issuer=ISSUER, subject='user-123', principal_type='USER', display_name='评审人 / Reviewer', email='private@example.com')
        other = SecurityPrincipal(issuer=ISSUER, subject='other', principal_type='USER', display_name='Other')
        supplier = Supplier(code='IDENTITY-SUP', name='Supplier')
        customer = Customer(code='IDENTITY-CUS', name='Customer')
        db.add_all([person, other, supplier, customer]); db.flush()
        project = Project(customer_id=customer.id, project_code='IDENTITY-P', name='Project')
        software = SoftwareProduct(supplier_id=supplier.id, code='IDENTITY-SW', name='Software')
        db.add_all([project, software]); db.flush()
        db.add_all([
            GlobalRoleAssignment(principal_id=person.id, role='AUDITOR'),
            GlobalRoleAssignment(principal_id=other.id, role='PLATFORM_ADMIN'),
            ProjectMembership(principal_id=person.id, project_id=project.id, role='REVIEWER'),
            ProjectMembership(principal_id=person.id, project_id=project.id, role='CONTRIBUTOR', status='SUSPENDED'),
            ProjectMembership(principal_id=other.id, project_id=project.id, role='PRODUCTION_OPERATOR'),
            SoftwareMembership(principal_id=person.id, software_id=software.id, role='SOFTWARE_VIEWER'),
            SoftwareMembership(principal_id=person.id, software_id=software.id, role='SOFTWARE_MAINTAINER', status='SUSPENDED'),
        ]); db.commit()
        ids = {'principal': person.id, 'other': other.id, 'customer': customer.id, 'project': project.id, 'software': software.id}
    def route_db():
        with sessions() as db:
            yield db
    main.app.dependency_overrides[get_db] = route_db
    try:
        with TestClient(main.app) as client:
            yield client, sessions, ids, key, engine
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        if request.param == 'sqlite':
            engine.dispose()


def headers(key, **claims):
    return {'Authorization': 'Bearer '+signed_token(key, **claims)}


def private(response):
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert 'authorization' in response.headers['vary'].lower()


def test_self_summary_is_authenticated_minimal_and_read_only(identity_client):
    client, sessions, ids, key, _ = identity_client
    with sessions() as db:
        audit_before = db.scalar(select(func.count()).select_from(AuditEvent))
    response = client.get('/api/v1/security/me', headers=headers(key))
    assert response.status_code == 200
    private(response)
    body = response.json()
    assert body['principal'] == {'id': str(ids['principal']), 'principal_type': 'USER', 'display_name': '评审人 / Reviewer'}
    assert body['active_grant_counts'] == {'GLOBAL': 1, 'PROJECT': 1, 'SOFTWARE': 1}
    assert body['read_only_mode'] is True
    for secret in ['user-123', 'private@example.com', ISSUER, headers(key)['Authorization']]:
        assert secret not in response.text
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_before


@pytest.mark.parametrize('scope,role,scope_key', [('GLOBAL','AUDITOR',None), ('PROJECT','REVIEWER','project'), ('SOFTWARE','SOFTWARE_VIEWER','software')])
def test_own_active_grants_are_bounded_and_never_include_other_principals(identity_client, scope, role, scope_key):
    client, _, ids, key, _ = identity_client
    response = client.get('/api/v1/security/me/grants', params={'scope': scope, 'limit': 1}, headers=headers(key))
    assert response.status_code == 200
    private(response)
    body = response.json()
    assert body['principal_id'] == str(ids['principal'])
    assert body['scope'] == scope and body['total'] == 1 and body['next_offset'] is None
    assert body['items'][0]['role'] == role
    assert body['items'][0]['scope_id'] == (str(ids[scope_key]) if scope_key else None)
    assert str(ids['other']) not in response.text
    end = client.get('/api/v1/security/me/grants', params={'scope': scope, 'offset': 100000}, headers=headers(key))
    assert end.json()['total'] == 1 and end.json()['items'] == []


@pytest.mark.parametrize('query', ['scope=PROJECT&limit=0','scope=PROJECT&limit=101','scope=PROJECT&offset=-1','scope=PROJECT&offset=100001','scope=UNKNOWN','scope=PROJECT&principal_id=other','scope=PROJECT&status=SUSPENDED',''])
def test_grant_queries_fail_closed_and_are_not_cached(identity_client, query):
    client, _, _, key, _ = identity_client
    response = client.get('/api/v1/security/me/grants?'+query, headers=headers(key))
    assert response.status_code == 422
    private(response)


@pytest.mark.parametrize('path', ['/api/v1/security/me', '/api/v1/security/me/grants?scope=GLOBAL'])
def test_missing_token_and_disabled_auth_never_fall_back_to_demo(identity_client, monkeypatch, path):
    client, _, _, key, _ = identity_client
    response = client.get(path)
    assert response.status_code == 401 and response.headers['www-authenticate'] == 'Bearer'
    private(response)
    monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    monkeypatch.setattr(auth, 'jwks_client', lambda *_: pytest.fail('disabled auth must not contact provider'))
    response = client.get(path, headers=headers(key))
    assert response.status_code == 401 and response.json()['detail'] == 'oidc_not_enabled'
    private(response)
    assert client.get('/health/live').status_code == 200


@pytest.mark.parametrize('claims', [{'aud':'wrong'}, {'iss':'https://wrong.example.com'}, {'sub':'unknown'}, {'exp':datetime.now(timezone.utc)-timedelta(days=1)}])
def test_self_reads_reuse_real_signature_claim_and_local_identity_checks(identity_client, claims):
    client, _, _, key, _ = identity_client
    response = client.get('/api/v1/security/me', headers=headers(key, **claims))
    assert response.status_code == 401
    private(response)


def test_disabled_principal_and_suspended_grant_are_observed_on_next_request(identity_client):
    client, sessions, ids, key, _ = identity_client
    with sessions() as db:
        grant = db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id==ids['principal'], ProjectMembership.role=='REVIEWER'))
        grant.status = 'SUSPENDED'; db.commit()
    assert client.get('/api/v1/security/me', headers=headers(key)).json()['active_grant_counts']['PROJECT'] == 0
    with sessions() as db:
        db.get(SecurityPrincipal, ids['principal']).status = 'DISABLED'; db.commit()
    response = client.get('/api/v1/security/me', headers=headers(key))
    assert response.status_code == 401 and response.json()['detail'] == 'disabled_principal'


def test_signature_and_cross_principal_summary_filters_cannot_select_an_identity(identity_client):
    client, _, ids, key, _ = identity_client
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = client.get('/api/v1/security/me', headers=headers(wrong_key))
    assert response.status_code == 401
    private(response)
    response = client.get('/api/v1/security/me', params={'principal_id': str(ids['other'])}, headers=headers(key))
    assert response.status_code == 422
    private(response)


def test_identity_is_rechecked_after_token_resolution_before_grant_reads(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    original = main.authenticate_write_request
    def disable_after_authentication(request, settings):
        principal = original(request, settings)
        with sessions() as db:
            db.get(SecurityPrincipal, ids['principal']).status = 'DISABLED'
            db.commit()
        return principal
    monkeypatch.setattr(main, 'authenticate_write_request', disable_after_authentication)
    response = client.get('/api/v1/security/me/grants?scope=PROJECT', headers=headers(key))
    assert response.status_code == 401 and response.json()['detail'] == 'inactive_principal'
    private(response)


def test_service_identity_and_unassigned_identity_do_not_gain_demo_grants(identity_client):
    client, sessions, ids, key, _ = identity_client
    with sessions() as db:
        person = db.get(SecurityPrincipal, ids['principal'])
        person.principal_type = 'SERVICE'
        db.query(GlobalRoleAssignment).filter_by(principal_id=person.id).delete()
        db.query(ProjectMembership).filter_by(principal_id=person.id).delete()
        db.query(SoftwareMembership).filter_by(principal_id=person.id).delete()
        db.commit()
    body = client.get('/api/v1/security/me', headers=headers(key)).json()
    assert body['principal']['principal_type'] == 'SERVICE'
    assert body['active_grant_counts'] == {'GLOBAL': 0, 'PROJECT': 0, 'SOFTWARE': 0}
    assert client.get('/api/v1/security/me/grants?scope=GLOBAL', headers=headers(key)).json()['items'] == []


def test_growth_is_complete_bounded_and_has_constant_query_count(identity_client):
    client, sessions, ids, key, engine = identity_client
    calls = []
    def observed(*args): calls.append(args[2])
    event.listen(engine, 'before_cursor_execute', observed)
    try:
        client.get('/api/v1/security/me/grants?scope=PROJECT&limit=1', headers=headers(key))
        baseline = len(calls)
        with sessions() as db:
            for n in range(105):
                p = Project(customer_id=ids['customer'], project_code=f'G-{n}', name='Growth')
                db.add(p); db.flush()
                db.add(ProjectMembership(principal_id=ids['principal'], project_id=p.id, role='REVIEWER'))
            db.commit()
        calls.clear()
        first = client.get('/api/v1/security/me/grants?scope=PROJECT&limit=1', headers=headers(key)).json()
        assert len(calls) == baseline
        assert first['total'] == 106 and len(first['items']) == 1 and first['next_offset'] == 1
        seen = []
        for offset in range(0, 106, 25):
            page = client.get(f'/api/v1/security/me/grants?scope=PROJECT&limit=25&offset={offset}', headers=headers(key)).json()
            seen += [item['id'] for item in page['items']]
            assert page['total'] == 106
        assert len(seen) == len(set(seen)) == 106
    finally:
        event.remove(engine, 'before_cursor_execute', observed)
