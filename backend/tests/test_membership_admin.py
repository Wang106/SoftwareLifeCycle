"""Signed admin status transitions: exact scope, replay, conflict and atomic audit."""
import uuid

import pytest
from sqlalchemy import func, select

from app import main
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg

ROOT = '/api/v1/security/admin/memberships'


def command(**patch):
    return {'event_no': 'ADM-'+uuid.uuid4().hex, 'expected_status': 'ACTIVE',
            'status': 'SUSPENDED', 'reason': 'Temporary access review', **patch}


def target(sessions, ids, scope):
    model = ProjectMembership if scope == 'PROJECT' else SoftwareMembership
    with sessions() as db:
        row = db.scalars(select(model).where(model.principal_id == ids['principal'], model.status == 'ACTIVE')).one()
        return row.id, model


def post(client, key, scope, identifier, value, **claims):
    return client.post(f'{ROOT}/{scope}/{identifier}/status', json=value, headers=headers(key, sub='other', **claims))


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_change_retry_resume_and_old_retry_do_not_reapply(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, scope)
    value = command()
    response = post(client, key, scope, identifier, value)
    assert response.status_code == 200, response.text
    private(response)
    assert response.json() == {'membership_id': str(identifier), 'scope': scope, 'applied_status': 'SUSPENDED',
        'current_status': 'SUSPENDED', 'replayed': False, 'audit_event_no': value['event_no']}
    assert post(client, key, scope, identifier, value).json()['replayed'] is True
    assert client.get('/api/v1/security/me/grants', params={'scope': scope}, headers=headers(key)).json()['total'] == 0
    resumed = command(expected_status='SUSPENDED', status='ACTIVE')
    assert post(client, key, scope, identifier, resumed).status_code == 200
    old = post(client, key, scope, identifier, value).json()
    assert old['replayed'] is True and old['applied_status'] == 'SUSPENDED' and old['current_status'] == 'ACTIVE'
    assert client.get('/api/v1/security/me/grants', params={'scope': scope}, headers=headers(key)).json()['total'] == 1
    with sessions() as db:
        assert db.get(model, identifier).status == 'ACTIVE'
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == identifier)).all()
        assert len(events) == 2
        assert all(e.actor_principal_id == ids['other'] and e.actor_display_name == 'Other' for e in events)
        assert events[0].payload_json['reason'] == value['reason']
        assert all(e.payload_json['principal_id'] == str(ids['principal']) for e in events)
        assert headers(key)['Authorization'] not in str([e.payload_json for e in events])


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
@pytest.mark.parametrize('field,value', [('status','ACTIVE'), ('reason','Different justification'), ('expected_status','SUSPENDED')])
def test_reused_event_with_changed_payload_conflicts(identity_client, monkeypatch, scope, field, value):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, _ = target(sessions, ids, scope)
    original = command()
    assert post(client, key, scope, identifier, original).status_code == 200
    changed = {**original, field: value}
    # Equal from/to is invalid regardless of event reuse.
    assert post(client, key, scope, identifier, changed).status_code in {409, 422}


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_nonadmin_and_removed_admin_cannot_mutate_or_replay(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, scope)
    value = command()
    for whom in ['user-123', 'unknown']:
        response = client.post(f'{ROOT}/{scope}/{identifier}/status', json=value, headers=headers(key, sub=whom))
        assert response.status_code == (403 if whom == 'user-123' else 401)
        private(response)
    assert post(client, key, scope, identifier, value).status_code == 200
    with sessions() as db:
        row = db.scalars(select(GlobalRoleAssignment).where(GlobalRoleAssignment.principal_id == ids['other'])).one()
        db.delete(row); db.commit()
    response = post(client, key, scope, identifier, value)
    assert response.status_code == 403 and response.json()['detail'] == 'platform_admin_required'
    with sessions() as db:
        assert db.get(model, identifier).status == 'SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_read_only_and_disabled_auth_are_independent_denials(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    identifier, model = target(sessions, ids, scope)
    response = post(client, key, scope, identifier, command())
    assert response.status_code == 403 and response.json()['detail'] == 'read_only_mode'
    private(response)
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    response = post(client, key, scope, identifier, command())
    assert response.status_code == 401 and response.json()['detail'] == 'oidc_not_enabled'
    private(response)
    with sessions() as db:
        assert db.get(model, identifier).status == 'ACTIVE'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize('patch', [{'extra':'untrusted'}, {'actor_name':'Spoofed'}, {'principal_id':str(uuid.uuid4())},
    {'event_no':'x'*51}, {'event_no':'bad event'}, {'reason':'   '}, {'reason':'x'*501},
    {'expected_status':'UNKNOWN'}, {'status':'UNKNOWN'}, {'status':'ACTIVE'}])
def test_invalid_body_has_no_effect(identity_client, monkeypatch, patch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, 'PROJECT')
    response = post(client, key, 'PROJECT', identifier, command(**patch))
    assert response.status_code == 422
    private(response)
    with sessions() as db:
        assert db.get(model, identifier).status == 'ACTIVE'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_missing_wrong_scope_and_stale_state_fail_closed(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, _ = target(sessions, ids, scope)
    assert post(client, key, scope, uuid.uuid4(), command()).status_code == 404
    other_scope = 'SOFTWARE' if scope == 'PROJECT' else 'PROJECT'
    assert post(client, key, other_scope, identifier, command()).status_code == 404
    assert post(client, key, scope, identifier, command(expected_status='SUSPENDED', status='ACTIVE')).status_code == 409
    assert post(client, key, 'GLOBAL', identifier, command()).status_code == 422
    assert post(client, key, scope, identifier, command()).status_code == 200
    assert post(client, key, scope, identifier, command()).status_code == 409


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_inactive_recipient_cannot_be_resumed_but_can_be_suspended(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, scope)
    with sessions() as db:
        db.get(SecurityPrincipal, ids['principal']).status = 'DISABLED'; db.commit()
    assert post(client, key, scope, identifier, command()).status_code == 200
    response = post(client, key, scope, identifier, command(expected_status='SUSPENDED', status='ACTIVE'))
    assert response.status_code == 409 and response.json()['detail'] == 'recipient_inactive'
    with sessions() as db:
        assert db.get(model, identifier).status == 'SUSPENDED'


@pytest.mark.parametrize('scope', ['PROJECT', 'SOFTWARE'])
def test_audit_failure_rolls_back_status(identity_client, monkeypatch, scope):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, scope)
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService, 'record', fail)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        post(client, key, scope, identifier, command())
    with sessions() as db:
        assert db.get(model, identifier).status == 'ACTIVE'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_event_is_bound_to_target_and_administrator(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, _ = target(sessions, ids, 'PROJECT')
    value = command()
    assert post(client, key, 'PROJECT', identifier, value).status_code == 200
    software, _ = target(sessions, ids, 'SOFTWARE')
    assert post(client, key, 'SOFTWARE', software, value).status_code == 409
    with sessions() as db:
        db.add(GlobalRoleAssignment(principal_id=ids['principal'], role='PLATFORM_ADMIN')); db.commit()
    response = client.post(f'{ROOT}/PROJECT/{identifier}/status', json=value, headers=headers(key))
    assert response.status_code == 409 and response.json()['detail'] == 'audit_event_conflict'


def test_admin_controls_validate_claims_and_revoked_browser_session(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    identifier, model = target(sessions, ids, 'PROJECT')
    for claim in [{'aud':'wrong'}, {'iss':'https://wrong.example.com'}, {'sub':'unknown'}]:
        authorization = headers(key, **{'sub':'other', **claim})
        response = client.post(f'{ROOT}/PROJECT/{identifier}/status', json=command(), headers=authorization)
        assert response.status_code == 401
        private(response)
    authorization = headers(key, sub='other')
    authorization['X-Browser-Session'] = str(uuid.uuid4())
    response = client.post(f'{ROOT}/PROJECT/{identifier}/status', json=command(), headers=authorization)
    assert response.status_code == 401 and response.json()['detail'] == 'invalid_browser_session'
    with sessions() as db:
        assert db.get(model, identifier).status == 'ACTIVE'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_security_admin_is_not_a_read_only_session_exception(identity_client):
    client, _, _, key, _ = identity_client
    for suffix in ['', '/PROJECT/invalid/status', '/GLOBAL/'+str(uuid.uuid4())+'/status']:
        response = client.post(ROOT+suffix, json=command(), headers=headers(key, sub='other'))
        assert response.status_code == 403 and response.json()['detail'] == 'read_only_mode'
        private(response)
