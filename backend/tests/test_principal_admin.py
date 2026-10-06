"""Signed admin-only local identities, exact retries and atomic session invalidation."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid

import pytest
from sqlalchemy import func, select

from app import main
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg

ROOT = '/api/v1/security/admin/principals'


def admin(key, **claims):
    return headers(key, **{'sub': 'other', **claims})


def registration(**overrides):
    return {'event_no': 'PRINCIPAL-REGISTER', 'reason': 'Register approved local reference',
            'principal_id': str(uuid.uuid4()), 'subject': 'new-provider-subject',
            'principal_type': 'USER', 'display_name': '新用户 / New user', **overrides}


def transition(**overrides):
    return {'event_no': 'PRINCIPAL-DISABLE', 'expected_status': 'ACTIVE',
            'status': 'DISABLED', 'reason': 'Disable pending access review', **overrides}


def status_path(identifier):
    return ROOT+'/'+str(identifier)+'/status'


def event_count(db):
    return db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.event_type.in_(['PRINCIPAL_REGISTERED', 'PRINCIPAL_STATUS_CHANGED'])))


def add_session(db, identifier, token='copied-provider-token', *, expired=False, revoked=False):
    now = datetime.now(timezone.utc)
    row = BrowserSession(id=uuid.uuid4(), principal_id=identifier, token_digest=hashlib.sha256(token.encode()).hexdigest(),
        created_at=now-timedelta(minutes=10), expires_at=now+timedelta(seconds=-1 if expired else 240),
        revoked_at=now-timedelta(minutes=1) if revoked else None)
    db.add(row); db.flush()
    return row.id


@pytest.mark.parametrize('kind', ['USER', 'SERVICE'])
def test_registration_is_disabled_exact_configured_identity_without_grants(identity_client, monkeypatch, kind):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    body = registration(principal_type=kind)
    response = client.post(ROOT, json=body, headers=admin(key))
    assert response.status_code == 200, response.text
    private(response)
    assert response.json() == {'principal_id': body['principal_id'], 'applied_status': 'DISABLED',
        'current_status': 'DISABLED', 'replayed': False, 'audit_event_no': body['event_no'], 'revoked_browser_sessions': 0}
    with sessions() as db:
        row = db.get(SecurityPrincipal, uuid.UUID(body['principal_id']))
        assert (row.issuer, row.subject, row.principal_type, row.display_name, row.status, row.email) == (
            main.settings.oidc_issuer_url, body['subject'], kind, body['display_name'], 'DISABLED', None)
        for model in [GlobalRoleAssignment, ProjectMembership, SoftwareMembership, BrowserSession]:
            assert db.scalar(select(func.count()).select_from(model).where(model.principal_id == row.id)) == 0
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == body['event_no']))
        assert event.actor_principal_id is not None and event.entity_id == row.id
        assert event.entity_ref == str(row.id) and len(event.payload_json['request_digest']) == 64
        evidence = json.dumps(event.payload_json)
        assert body['subject'] not in evidence and row.issuer not in evidence and body['display_name'] not in evidence
    for secret in ['new-provider-subject', main.settings.oidc_issuer_url, body['display_name']]:
        assert secret not in response.text
    assert client.get('/api/v1/security/me', headers=headers(key, sub=body['subject'])).status_code == 401


def test_register_retry_after_enable_returns_history_without_disabling_again(identity_client, monkeypatch):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    body = registration()
    assert client.post(ROOT, json=body, headers=admin(key)).status_code == 200
    enable = transition(event_no='PRINCIPAL-ENABLE', expected_status='DISABLED', status='ACTIVE')
    assert client.post(status_path(body['principal_id']), json=enable, headers=admin(key)).status_code == 200
    retry = client.post(ROOT, json=body, headers=admin(key))
    assert retry.status_code == 200 and retry.json()['replayed'] is True
    assert retry.json()['applied_status'] == 'DISABLED' and retry.json()['current_status'] == 'ACTIVE'
    assert client.get('/api/v1/security/me', headers=headers(key, sub=body['subject'])).status_code == 200
    with sessions() as db:
        assert event_count(db) == 2


@pytest.mark.parametrize('field,value', [('subject','different'), ('display_name','Different'),
    ('principal_type','SERVICE'), ('reason','Different valid reason'), ('principal_id','random')])
def test_register_changed_request_is_conflict_not_update(identity_client, monkeypatch, field, value):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    body = registration()
    assert client.post(ROOT, json=body, headers=admin(key)).status_code == 200
    value = str(uuid.uuid4()) if value == 'random' else value
    response = client.post(ROOT, json={**body, field:value}, headers=admin(key))
    assert response.status_code == 409 and response.json()['detail'] == 'audit_event_conflict'
    private(response)
    with sessions() as db:
        assert event_count(db) == 1
        assert db.get(SecurityPrincipal, uuid.UUID(body['principal_id'])).subject == body['subject']


@pytest.mark.parametrize('duplicate', ['uuid','issuer_subject'])
def test_duplicate_identity_with_new_event_never_attaches_to_existing_row(identity_client, monkeypatch, duplicate):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    body = registration()
    assert client.post(ROOT, json=body, headers=admin(key)).status_code == 200
    second = {**body, 'event_no':'PRINCIPAL-OTHER'}
    second['subject' if duplicate == 'uuid' else 'principal_id'] = 'another' if duplicate == 'uuid' else str(uuid.uuid4())
    response = client.post(ROOT, json=second, headers=admin(key))
    assert response.status_code == 409 and response.json()['detail'] == 'principal_registration_conflict'
    with sessions() as db:
        assert event_count(db) == 1


@pytest.mark.parametrize('field,value', [('issuer','https://wrong.example.com'), ('email','email@example.com'),
    ('status','ACTIVE'), ('role','PLATFORM_ADMIN'), ('actor_name','spoofed'), ('subject',' space'),
    ('subject','tab\tvalue'), ('subject',''), ('subject','x'*501), ('display_name',' '),
    ('display_name','x'*201), ('principal_type','HUMAN'), ('principal_id','not-uuid'),
    ('reason','    '), ('reason','x'*501), ('reason','reason\x7f'), ('event_no','invalid key')])
def test_registration_validation_rejects_unsupported_or_ambiguous_input(identity_client, monkeypatch, field, value):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    response = client.post(ROOT, json=registration(**{field:value}), headers=admin(key))
    assert response.status_code == 422, response.text
    private(response)
    with sessions() as db:
        assert event_count(db) == 0


@pytest.mark.parametrize('operation', ['register','status'])
@pytest.mark.parametrize('denial', ['readonly','auth_disabled','anonymous','nonadmin','disabled_admin','revoked_cookie'])
def test_both_controls_fail_closed_and_never_mutate(identity_client, monkeypatch, operation, denial):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    auth_headers = admin(key)
    expected = 401
    if denial == 'readonly':
        monkeypatch.setattr(main.settings, 'read_only_mode', True); expected = 403
    elif denial == 'auth_disabled':
        monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    elif denial == 'anonymous': auth_headers = {}
    elif denial == 'nonadmin': auth_headers = headers(key); expected = 403
    elif denial == 'disabled_admin':
        with sessions() as db:
            db.get(SecurityPrincipal, ids['other']).status = 'DISABLED'; db.commit()
    elif denial == 'revoked_cookie': auth_headers['X-Browser-Session'] = str(uuid.uuid4())
    body = registration() if operation == 'register' else transition()
    path = ROOT if operation == 'register' else status_path(ids['principal'])
    response = client.post(path, json=body, headers=auth_headers)
    assert response.status_code == expected, response.text
    private(response)
    with sessions() as db:
        assert event_count(db) == 0 and db.get(SecurityPrincipal, ids['principal']).status == 'ACTIVE'


def test_disable_is_atomic_bounded_revoke_and_old_cookie_never_revives(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    user_headers = headers(key)
    token = user_headers['Authorization'].split(' ',1)[1]
    with sessions() as db:
        cookie = add_session(db, ids['principal'], token)
        expired = add_session(db, ids['principal'], expired=True)
        already_revoked = add_session(db, ids['principal'], revoked=True)
        other_cookie = add_session(db, ids['other'])
        old_revoked_time = db.get(BrowserSession, already_revoked).revoked_at
        grants = [(model, list(db.execute(select(model.id, model.status).where(model.principal_id == ids['principal']))))
                  for model in [ProjectMembership, SoftwareMembership]]
        db.commit()
    cookie_headers = {**user_headers, 'X-Browser-Session':str(cookie)}
    assert client.get('/api/v1/security/me', headers=cookie_headers).status_code == 200
    body = transition()
    response = client.post(status_path(ids['principal']), json=body, headers=admin(key))
    assert response.status_code == 200 and response.json()['revoked_browser_sessions'] == 2
    private(response)
    assert client.get('/api/v1/security/me', headers=user_headers).status_code == 401
    assert client.get('/api/v1/security/me', headers=cookie_headers).status_code == 401
    enable = transition(event_no='PRINCIPAL-ENABLE', expected_status='DISABLED', status='ACTIVE')
    assert client.post(status_path(ids['principal']), json=enable, headers=admin(key)).status_code == 200
    assert client.get('/api/v1/security/me', headers=user_headers).status_code == 200
    assert client.get('/api/v1/security/me', headers=cookie_headers).status_code == 401
    retry = client.post(status_path(ids['principal']), json=body, headers=admin(key))
    assert retry.status_code == 200 and retry.json()['replayed'] is True
    assert retry.json()['current_status'] == 'ACTIVE' and retry.json()['applied_status'] == 'DISABLED'
    assert retry.json()['revoked_browser_sessions'] == 2
    with sessions() as db:
        for identifier in [cookie, expired]: assert db.get(BrowserSession, identifier).revoked_at is not None
        assert db.get(BrowserSession, already_revoked).revoked_at == old_revoked_time
        assert db.get(BrowserSession, other_cookie).revoked_at is None
        for model, values in grants:
            assert list(db.execute(select(model.id,model.status).where(model.principal_id == ids['principal']))) == values
        assert event_count(db) == 2
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == body['event_no']))
        assert event.actor_principal_id == ids['other'] and event.payload_json['revoked_browser_sessions'] == 2
        assert token not in json.dumps(event.payload_json) and str(cookie) not in json.dumps(event.payload_json)


@pytest.mark.parametrize('target', ['self','other_admin','disabled_admin'])
def test_platform_admin_identities_are_protected_without_changes(identity_client, monkeypatch, target):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier = ids['other']
    if target != 'self':
        with sessions() as db:
            row = SecurityPrincipal(issuer=main.settings.oidc_issuer_url, subject='third-admin',
                principal_type='USER', display_name='Another administrator',
                status='DISABLED' if target == 'disabled_admin' else 'ACTIVE')
            db.add(row); db.flush(); identifier = row.id
            db.add(GlobalRoleAssignment(principal_id=row.id,role='PLATFORM_ADMIN')); db.commit()
    body = transition(expected_status='DISABLED', status='ACTIVE') if target == 'disabled_admin' else transition()
    response = client.post(status_path(identifier), json=body, headers=admin(key))
    assert response.status_code == 409 and response.json()['detail'] == 'admin_principal_protected'
    with sessions() as db:
        assert db.get(SecurityPrincipal,identifier).status == body['expected_status'] and event_count(db) == 0


@pytest.mark.parametrize('case', ['missing','stale','same','extra','long_reason','malformed_uuid'])
def test_status_preconditions_and_validation(identity_client, monkeypatch, case):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier = uuid.uuid4() if case == 'missing' else ids['principal']
    body = transition()
    expected = 422
    if case == 'missing': expected = 404
    elif case == 'stale': body.update(expected_status='DISABLED',status='ACTIVE'); expected = 409
    elif case == 'same': body['status'] = 'ACTIVE'
    elif case == 'extra': body['actor_principal_id'] = str(ids['other'])
    elif case == 'long_reason': body['reason'] = 'x'*501
    elif case == 'malformed_uuid': identifier = 'not-uuid'
    response = client.post(status_path(identifier), json=body, headers=admin(key))
    assert response.status_code == expected, response.text
    private(response)
    with sessions() as db: assert event_count(db) == 0


@pytest.mark.parametrize('operation', ['register','status'])
def test_audit_failure_rolls_back_identity_and_all_session_changes(identity_client, monkeypatch, operation):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    with sessions() as db:
        cookie = add_session(db, ids['principal']); db.commit()
    record = AuditEventService.record
    def fail(*args, **kwargs):
        record(*args, **kwargs)
        raise RuntimeError('deliberate audit failure')
    monkeypatch.setattr(AuditEventService,'record',fail)
    body = registration() if operation == 'register' else transition()
    path = ROOT if operation == 'register' else status_path(ids['principal'])
    with pytest.raises(RuntimeError,match='deliberate audit failure'):
        client.post(path,json=body,headers=admin(key))
    with sessions() as db:
        assert db.get(SecurityPrincipal, ids['principal']).status == 'ACTIVE'
        assert db.get(BrowserSession,cookie).revoked_at is None
        if operation == 'register': assert db.get(SecurityPrincipal,uuid.UUID(body['principal_id'])) is None
        assert event_count(db) == 0


@pytest.mark.parametrize('operation', ['register','status'])
def test_replay_requires_original_admin_and_exact_request(identity_client, monkeypatch, operation):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    with sessions() as db:
        db.add(GlobalRoleAssignment(principal_id=ids['principal'],role='PLATFORM_ADMIN')); db.commit()
    body = registration()
    assert client.post(ROOT,json=body,headers=admin(key)).status_code == 200
    path = ROOT
    if operation == 'status':
        path = status_path(body['principal_id'])
        body = transition(expected_status='DISABLED',status='ACTIVE')
        assert client.post(path,json=body,headers=admin(key)).status_code == 200
    response = client.post(path,json=body,headers=headers(key))
    assert response.status_code == 409 and response.json()['detail'] == 'audit_event_conflict'
    response = client.post(path,json={**body,'reason':'Changed valid reason'},headers=admin(key))
    assert response.status_code == 409


def test_cross_operation_event_collision_is_not_replay(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body = registration()
    assert client.post(ROOT,json=body,headers=admin(key)).status_code == 200
    response = client.post(status_path(ids['principal']),json=transition(event_no=body['event_no']),headers=admin(key))
    assert response.status_code == 409 and response.json()['detail'] == 'audit_event_conflict'
    response = client.post(ROOT,json=registration(event_no=body['event_no'],subject='another'),headers=admin(key))
    assert response.status_code == 409
    with sessions() as db:
        assert event_count(db) == 1 and db.get(SecurityPrincipal,ids['principal']).status == 'ACTIVE'


@pytest.mark.parametrize('kind',['USER','SERVICE'])
def test_nonadmin_user_and_service_can_enable_and_disable_without_role_changes(identity_client,monkeypatch,kind):
    client,sessions,_,key,_ = identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body = registration(principal_type=kind)
    assert client.post(ROOT,json=body,headers=admin(key)).status_code == 200
    enable = transition(event_no='ENABLE',expected_status='DISABLED',status='ACTIVE')
    assert client.post(status_path(body['principal_id']),json=enable,headers=admin(key)).status_code == 200
    assert client.get('/api/v1/security/me',headers=headers(key,sub=body['subject'])).status_code == 200
    disable = transition(event_no='DISABLE')
    assert client.post(status_path(body['principal_id']),json=disable,headers=admin(key)).status_code == 200
    assert client.get('/api/v1/security/me',headers=headers(key,sub=body['subject'])).status_code == 401
    with sessions() as db:
        assert event_count(db) == 3
        assert db.get(SecurityPrincipal,uuid.UUID(body['principal_id'])).principal_type == kind


@pytest.mark.parametrize('issuer',['','x'*501])
def test_direct_registration_rejects_unusable_configured_issuer(identity_client,monkeypatch,issuer):
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.auth import AuthenticatedPrincipal
    from app.api.principal_admin import RegisterPrincipal,register_principal
    _,sessions,ids,_,_ = identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    with sessions() as db:
        administrator = db.get(SecurityPrincipal,ids['other'])
        request = Request({'type':'http','headers':[]})
        request.state.principal = AuthenticatedPrincipal(administrator.id,administrator.issuer,administrator.subject,
            administrator.principal_type,administrator.display_name,None)
        monkeypatch.setattr(main.settings,'oidc_issuer_url',issuer)
        with pytest.raises(HTTPException) as caught:
            register_principal(RegisterPrincipal(**registration()),request,db)
        assert caught.value.status_code == 503 and caught.value.detail == 'configured_issuer_required'
        assert not db.in_transaction()
        assert event_count(db) == 0


@pytest.mark.parametrize('payload',[['unrelated'],{'revoked_browser_sessions':True},{'revoked_browser_sessions':-1}])
def test_unrelated_or_malformed_audit_evidence_is_a_clean_conflict(identity_client,monkeypatch,payload):
    client,sessions,ids,key,_ = identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    with sessions() as db:
        AuditEventService(db).record(event_no='PRINCIPAL-DISABLE',event_type='UNRELATED',action='READ',
            entity_type='OTHER',entity_id=ids['principal'],entity_ref=str(ids['principal']),
            summary='Unrelated evidence',payload=payload,actor_name='Historical actor')
        db.commit()
    response = client.post(status_path(ids['principal']),json=transition(),headers=admin(key))
    assert response.status_code == 409 and response.json()['detail'] == 'audit_event_conflict'
    private(response)
    with sessions() as db:
        assert db.get(SecurityPrincipal,ids['principal']).status == 'ACTIVE' and event_count(db) == 0
