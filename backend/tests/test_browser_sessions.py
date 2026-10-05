"""Browser-session revocation: real signed bearer, ownership, expiry and atomic audit."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import func, select

from app import main
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, SecurityPrincipal
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg

ROOT = '/api/v1/security/me/browser-sessions'


def body(**patch):
    return {'id': str(uuid.uuid4()), 'expires_at': int(datetime.now(timezone.utc).timestamp()) + 120, **patch}


def register(client, key):
    authorization = headers(key)
    value = body()
    response = client.post(ROOT, json=value, headers=authorization)
    assert response.status_code == 200, response.text
    private(response)
    return value, authorization


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_registration_revoke_and_copied_session_replay(identity_client):
    client, sessions, ids, key, _ = identity_client
    value, authorization = register(client, key)
    sid = value['id']; bound = {**authorization, 'X-Browser-Session': sid}
    assert client.post(ROOT, json=value, headers=authorization).json() == value
    response = client.get('/api/v1/security/me', headers=bound)
    assert response.status_code == 200 and response.json()['browser_session_id'] == sid
    assert 'x-browser-session' in response.headers['vary'].lower()
    assert client.get('/api/v1/security/me/grants?scope=GLOBAL', headers=bound).status_code == 200
    for _ in range(2):
        response = client.post(ROOT+'/'+sid+'/revoke', headers=authorization)
        assert response.status_code == 200 and response.json() == {'id': sid, 'status': 'revoked'}
        private(response)
    for path in ['/api/v1/security/me', '/api/v1/security/me/grants?scope=GLOBAL']:
        response = client.get(path, headers=bound)
        assert response.status_code == 401 and response.json()['detail'] == 'invalid_browser_session'
        private(response)
    # This revokes the registered browser session, not the provider's bearer token.
    assert client.get('/api/v1/security/me', headers=authorization).status_code == 200
    assert client.post(ROOT, json=value, headers=authorization).status_code == 409
    with sessions() as db:
        row = db.get(BrowserSession, uuid.UUID(sid))
        assert row.revoked_at and len(row.token_digest) == 64
        assert authorization['Authorization'].split(' ', 1)[1] != row.token_digest
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row.id)).all()
        assert {e.event_type for e in events} == {'BROWSER_SESSION_CREATED', 'BROWSER_SESSION_REVOKED'}
        assert len(events) == 2
        assert all(e.actor_principal_id == ids['principal'] and e.payload_json == {'expires_at': value['expires_at']} for e in events)
        assert authorization['Authorization'] not in str([e.payload_json for e in events])


def test_session_is_bound_to_exact_token_and_current_principal(identity_client):
    client, _, _, key, _ = identity_client
    value, authorization = register(client, key)
    for different in [headers(key, jti='new-token'), headers(key, sub='other')]:
        assert client.get('/api/v1/security/me', headers={**different, 'X-Browser-Session': value['id']}).status_code == 401
        assert client.post(ROOT+'/'+value['id']+'/revoke', headers=different).status_code == 404
        assert client.post(ROOT, json=value, headers=different).status_code == 409
    for sid in ['', 'malformed', str(uuid.uuid4())]:
        assert client.get('/api/v1/security/me', headers={**authorization, 'X-Browser-Session': sid}).status_code == 401


def test_expired_session_fails_even_with_live_bearer(identity_client):
    client, sessions, _, key, _ = identity_client
    value, authorization = register(client, key)
    with sessions() as db:
        row = db.get(BrowserSession, uuid.UUID(value['id']))
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get('/api/v1/security/me', headers={**authorization, 'X-Browser-Session': value['id']}).status_code == 401
    assert client.post(ROOT+'/'+value['id']+'/revoke', headers=authorization).status_code == 200


@pytest.mark.parametrize('patch', [{'expires_at': True}, {'expires_at': '9999999999'}, {'expires_at': -1}, {'expires_at': 1}, {'expires_at': 9999999999}, {'id': 'invalid'}, {'extra': 'forbidden'}])
def test_registration_rejects_bad_expiry_or_body_without_side_effects(identity_client, patch):
    client, sessions, _, key, _ = identity_client
    response = client.post(ROOT, json=body(**patch), headers=headers(key))
    assert response.status_code == 422
    private(response)
    with sessions() as db:
        assert count(db, BrowserSession) == 0


def test_session_lifetime_is_limited_by_token_and_fifteen_minutes(identity_client):
    client, _, _, key, _ = identity_client
    now = int(datetime.now(timezone.utc).timestamp())
    for expiry, token_expiry in [(now+400, now+300), (now+950, now+1200)]:
        response = client.post(ROOT, json=body(expires_at=expiry), headers=headers(key, exp=token_expiry))
        assert response.status_code == 422


def test_active_session_quota_and_revocation_releases_capacity(identity_client):
    client, sessions, _, key, _ = identity_client
    values = []
    authorization = headers(key)
    for _ in range(16):
        value = body(); values.append(value)
        assert client.post(ROOT, json=value, headers=authorization).status_code == 200
    response = client.post(ROOT, json=body(), headers=authorization)
    assert response.status_code == 429 and response.headers['retry-after'] == '900'
    assert client.post(ROOT, json=values[0], headers=authorization).status_code == 200
    assert client.post(ROOT+'/'+values[0]['id']+'/revoke', headers=authorization).status_code == 200
    assert client.post(ROOT, json=body(), headers=authorization).status_code == 200
    with sessions() as db:
        assert count(db, BrowserSession) == 17


def test_control_routes_require_oidc_and_active_user_in_read_only_mode(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    paths = [ROOT, ROOT+'/'+str(uuid.uuid4())+'/revoke']
    for path in paths:
        response = client.post(path, json=body())
        assert response.status_code == 401
        private(response)
    with sessions() as db:
        db.get(SecurityPrincipal, ids['principal']).principal_type = 'SERVICE'; db.commit()
    for path in paths:
        response = client.post(path, json=body(), headers=headers(key))
        assert response.status_code == 403 and response.json()['detail'] == 'user_principal_required'
        private(response)
    monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    for path in paths:
        response = client.post(path, json=body(), headers=headers(key))
        assert response.status_code == 401 and response.json()['detail'] == 'oidc_not_enabled'
        private(response)
    # The narrow exception never opens business writes or malformed control paths.
    assert client.post('/api/v1/commands/snapshots', json={}).status_code == 403
    assert client.post(ROOT+'/invalid/revoke').status_code == 403


@pytest.mark.parametrize('operation', ['create', 'revoke'])
def test_audit_failure_rolls_back_session_change(identity_client, monkeypatch, operation):
    client, sessions, _, key, _ = identity_client
    value, authorization = register(client, key) if operation == 'revoke' else (body(), headers(key))
    with sessions() as db:
        before = count(db, AuditEvent)
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService, 'record', fail)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        client.post(ROOT if operation == 'create' else ROOT+'/'+value['id']+'/revoke', json=value if operation == 'create' else None, headers=authorization)
    with sessions() as db:
        row = db.get(BrowserSession, uuid.UUID(value['id']))
        assert (row is None) if operation == 'create' else row.revoked_at is None
        assert count(db, AuditEvent) == before
