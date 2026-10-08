"""Private principal reads: disabled discovery, exact history and bounded SQL."""
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import event, func, select

from app import auth, main
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, SecurityPrincipal
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg
from test_principal_admin import registration, transition

ROOT = '/api/v1/security/admin/principals'


def admin(key, **claims):
    return headers(key, **{'sub': 'other', **claims})


def history_event(db, identifier, **overrides):
    return AuditEventService(db).record(**{
        'event_no': 'HIST-'+uuid.uuid4().hex,
        'event_type': 'PRINCIPAL_STATUS_CHANGED', 'action': 'DISABLE',
        'entity_type': 'SECURITY_PRINCIPAL', 'entity_id': identifier,
        'entity_ref': str(identifier), 'actor_name': 'Historical administrator',
        'summary': 'Principal status history',
        'payload': {'expected_status': 'ACTIVE', 'status': 'DISABLED', 'reason': 'Review access'},
        **overrides})


def test_catalog_detail_minimal_private_and_no_read_audit(identity_client):
    client, sessions, ids, key, _ = identity_client
    with sessions() as db:
        baseline_events = db.scalar(select(func.count()).select_from(AuditEvent))
    response = client.get(ROOT, headers=admin(key))
    assert response.status_code == 200, response.text
    private(response)
    body = response.json()
    assert body['total'] == 2 and body['next_offset'] is None
    assert [v['id'] for v in body['items']] == sorted(str(v) for v in [ids['principal'], ids['other']])
    for item in body['items']:
        assert set(item) == {'id', 'principal_type', 'display_name', 'status', 'created_at',
            'issuer_matches_configuration', 'admin_principal_protected', 'status_history_supported'}
        assert item['issuer_matches_configuration'] is True
        assert item['status_history_supported'] is True
        assert item['admin_principal_protected'] is (item['id'] == str(ids['other']))
        detail = client.get(ROOT+'/'+item['id'], headers=admin(key))
        assert detail.status_code == 200 and detail.json() == item
        private(detail)
    for secret in ['private@example.com', 'user-123', main.settings.oidc_issuer_url, admin(key)['Authorization']]:
        assert secret not in response.text
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == baseline_events


@pytest.mark.parametrize('kind', ['USER', 'SERVICE'])
def test_new_disabled_ungranted_identity_is_discoverable(identity_client, monkeypatch, kind):
    client, sessions, _, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    with sessions() as db:
        baseline_events = db.scalar(select(func.count()).select_from(AuditEvent))
    body = registration(principal_type=kind)
    assert client.post(ROOT, json=body, headers=admin(key)).status_code == 200
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    response = client.get(ROOT, params={'principal_id': body['principal_id'], 'status': 'DISABLED',
        'principal_type': kind}, headers=admin(key))
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 1
    item = response.json()['items'][0]
    assert item['id'] == body['principal_id'] and item['admin_principal_protected'] is False
    detail = client.get(ROOT+'/'+body['principal_id'], headers=admin(key))
    assert detail.json() == item
    history = client.get(ROOT+'/'+body['principal_id']+'/history', headers=admin(key))
    assert history.status_code == 200 and history.json()['total'] == 0
    assert history.json()['current_status'] == 'DISABLED'
    assert history.json()['coverage'] == 'PRINCIPAL_STATUS_CHANGED_ONLY'
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == baseline_events+1
        assert db.scalar(select(func.count()).select_from(GlobalRoleAssignment).where(
            GlobalRoleAssignment.principal_id == uuid.UUID(body['principal_id']))) == 0


def test_pagination_filters_and_out_of_range_are_exact(identity_client):
    client, _, ids, key, _ = identity_client
    identifiers = []
    for offset in range(2):
        result = client.get(ROOT, params={'limit': 1, 'offset': offset}, headers=admin(key)).json()
        assert result['total'] == 2 and result['next_offset'] == (1 if offset == 0 else None)
        identifiers.append(result['items'][0]['id'])
    assert identifiers == sorted(set(identifiers))
    body = client.get(ROOT, params={'offset': 100000}, headers=admin(key)).json()
    assert body['total'] == 2 and body['items'] == [] and body['next_offset'] is None
    assert client.get(ROOT, params={'principal_id': str(ids['principal'])}, headers=admin(key)).json()['total'] == 1
    for params in [{'principal_id': str(uuid.uuid4())}, {'principal_type': 'SERVICE'}, {'status': 'DISABLED'}]:
        assert client.get(ROOT, params=params, headers=admin(key)).json()['total'] == 0


def test_protection_includes_suspended_admin_assignment_and_issuer_flag_is_only_information(identity_client):
    client, sessions, _, key, _ = identity_client
    with sessions() as db:
        row = SecurityPrincipal(issuer='https://old-provider.example.com', subject='private-foreign-subject',
            principal_type='SERVICE', display_name='Historical administrator', status='DISABLED', email='secret@foreign.test')
        db.add(row); db.flush(); identifier = row.id
        db.add(GlobalRoleAssignment(principal_id=identifier, role='PLATFORM_ADMIN', status='SUSPENDED'))
        db.commit()
    response = client.get(ROOT+'/'+str(identifier), headers=admin(key))
    assert response.status_code == 200, response.text
    assert response.json()['issuer_matches_configuration'] is False
    assert response.json()['admin_principal_protected'] is True
    for secret in ['old-provider', 'private-foreign-subject', 'secret@foreign.test']:
        assert secret not in response.text


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'offset=-1', 'offset=100001',
    'principal_id=bad', 'principal_type=BOT', 'status=SUSPENDED', 'issuer=private', 'subject=other', 'email=private'])
def test_invalid_unknown_catalog_query_is_rejected_privately(identity_client, query):
    client, _, _, key, _ = identity_client
    response = client.get(ROOT+'?'+query, headers=admin(key))
    assert response.status_code == 422
    private(response)


@pytest.mark.parametrize('suffix', ['', '/'+str(uuid.uuid4()), '/'+str(uuid.uuid4())+'/history'])
def test_all_reads_require_current_admin_with_no_demo_fallback(identity_client, monkeypatch, suffix):
    client, sessions, ids, key, _ = identity_client
    for authorization, expected in [({}, 401), (headers(key), 403), (admin(key, aud='wrong'), 401),
                                    (admin(key, sub='unknown'), 401)]:
        response = client.get(ROOT+suffix, headers=authorization)
        assert response.status_code == expected, response.text
        private(response)
    with sessions() as db:
        row = db.scalar(select(GlobalRoleAssignment).where(GlobalRoleAssignment.principal_id == ids['other']))
        row.status = 'SUSPENDED'; db.commit()
    assert client.get(ROOT+suffix, headers=admin(key)).status_code == 403
    monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    monkeypatch.setattr(auth, 'jwks_client', lambda *_: pytest.fail('No disabled-mode provider call'))
    response = client.get(ROOT+suffix, headers=admin(key))
    assert response.status_code == 401 and response.json()['detail'] == 'oidc_not_enabled'
    private(response)


@pytest.mark.parametrize('suffix', ['', '/principal', '/principal/history'])
def test_current_principal_and_token_bound_session_checked(identity_client, suffix):
    client, sessions, ids, key, _ = identity_client
    path = ROOT+suffix.replace('principal', str(ids['principal']))
    for extra in [{'X-Browser-Session': str(uuid.uuid4())}, {'X-Browser-Session': 'not-uuid'}]:
        response = client.get(path, headers={**admin(key), **extra})
        assert response.status_code == 401
        private(response)
    authorization = admin(key)
    response = client.post('/api/v1/security/me/browser-sessions', headers=authorization,
        json={'id': str(uuid.uuid4()), 'expires_at': int(datetime.now(timezone.utc).timestamp())+30})
    assert response.status_code == 200, response.text
    session_id = response.json()['id']
    assert client.get(path, headers={**authorization, 'X-Browser-Session': session_id}).status_code == 200
    changed_token = {**admin(key, jti='different-token'), 'X-Browser-Session': session_id}
    assert client.get(path, headers=changed_token).status_code == 401
    with sessions() as db:
        db.get(SecurityPrincipal, ids['other']).status = 'DISABLED'; db.commit()
    response = client.get(path, headers=admin(key))
    assert response.status_code == 401 and response.json()['detail'] == 'disabled_principal'


def test_detail_history_not_found_and_strict_queries(identity_client):
    client, _, ids, key, _ = identity_client
    for suffix in ['', '/history']:
        response = client.get(ROOT+'/'+str(uuid.uuid4())+suffix, headers=admin(key))
        assert response.status_code == 404 and response.json()['detail'] == 'principal_not_found'
        private(response)
        assert client.get(ROOT+'/bad'+suffix, headers=admin(key)).status_code == 422
    assert client.get(ROOT+'/'+str(ids['principal'])+'?status=ACTIVE', headers=admin(key)).status_code == 422
    for query in ['limit=101', 'offset=-1', 'status=ACTIVE', 'event_type=PRINCIPAL_REGISTERED']:
        assert client.get(ROOT+'/'+str(ids['principal'])+'/history?'+query, headers=admin(key)).status_code == 422


def test_real_transitions_history_excludes_registration_and_inexact_audit(identity_client, monkeypatch):
    client, sessions, ids, key, _ = identity_client
    monkeypatch.setattr(main.settings, 'read_only_mode', False)
    for before, after in [('ACTIVE', 'DISABLED'), ('DISABLED', 'ACTIVE')]:
        response = client.post(ROOT+'/'+str(ids['principal'])+'/status', headers=admin(key),
            json=transition(event_no='STATUS-'+uuid.uuid4().hex, expected_status=before, status=after))
        assert response.status_code == 200, response.text
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    with sessions() as db:
        for overrides in [{'entity_id': uuid.uuid4()}, {'entity_type': 'PROJECT_MEMBERSHIP'},
            {'entity_ref': 'wrong'}, {'event_type': 'PRINCIPAL_REGISTERED'}]:
            history_event(db, ids['principal'], **overrides)
        db.commit()
    response = client.get(ROOT+'/'+str(ids['principal'])+'/history?limit=1', headers=admin(key))
    assert response.status_code == 200, response.text
    private(response)
    body = response.json()
    assert body['total'] == 2 and body['next_offset'] == 1 and body['current_status'] == 'ACTIVE'
    assert body['principal_id'] == str(ids['principal'])
    item = body['items'][0]
    assert item['action'] == 'ENABLE' and item['expected_status'] == 'DISABLED' and item['status'] == 'ACTIVE'
    assert item['actor_principal_id'] == str(ids['other']) and item['actor_display_name'] == 'Other'
    assert item['reason'] == 'Disable pending access review' and item['reason_truncated'] is False
    second = client.get(ROOT+'/'+str(ids['principal'])+'/history?limit=1&offset=1', headers=admin(key)).json()
    assert second['items'][0]['action'] == 'DISABLE' and second['next_offset'] is None


def test_history_sql_projection_truncation_ties_and_malformed_unused_payload(identity_client):
    client, sessions, ids, key, _ = identity_client
    timestamp = datetime.now(timezone.utc)
    identifiers = []
    with sessions() as db:
        for index in range(3):
            row = history_event(db, ids['principal'], occurred_at=timestamp,
                payload={'expected_status': 'UNKNOWN', 'status': 'DISABLED', 'reason': 'x'*2000,
                    'raw': 'z'*100000, 'token': 'private-token', 'revoked_browser_sessions': 'bad-integer'})
            identifiers.append(row.id)
        db.commit()
    response = client.get(ROOT+'/'+str(ids['principal'])+'/history?limit=2', headers=admin(key))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['total'] == 3 and body['next_offset'] == 2
    assert [v['id'] for v in body['items']] == [str(v) for v in sorted(identifiers, reverse=True)[:2]]
    assert all(v['reason'] == 'x'*500 and v['reason_truncated'] is True and v['expected_status'] is None for v in body['items'])
    assert len(response.content) < 2400
    for secret in ['private-token', 'z'*1000, 'payload_json', 'revoked_browser_sessions']:
        assert secret not in response.text


def test_growth_has_fixed_queries_and_no_orm_history_or_grants(identity_client):
    client, sessions, ids, key, engine = identity_client
    with sessions() as db:
        baseline_events = db.scalar(select(func.count()).select_from(AuditEvent))
    queries = []
    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        queries.append(statement)
    def forbid_graph(*args, **kwargs):
        pytest.fail('Private principal reads must not load ORM grants or audit payloads')
    def read():
        before = len(queries)
        catalog = client.get(ROOT+'?limit=1', headers=admin(key))
        detail = client.get(ROOT+'/'+str(ids['principal']), headers=admin(key))
        history = client.get(ROOT+'/'+str(ids['principal'])+'/history?limit=1', headers=admin(key))
        assert catalog.status_code == detail.status_code == history.status_code == 200
        return catalog.json(), history.json(), len(queries)-before
    event.listen(engine, 'before_cursor_execute', capture)
    for model in [GlobalRoleAssignment, AuditEvent]:
        event.listen(model, 'load', forbid_graph)
    try:
        initial_catalog, initial_history, initial_count = read()
        with sessions() as db:
            for index in range(110):
                db.add(SecurityPrincipal(issuer='https://growth.example.com', subject=str(index),
                    principal_type='SERVICE', display_name='Growth person', status='DISABLED'))
                history_event(db, ids['principal'], payload={'reason': 'Growth audit', 'unreturned': 'x'*10000})
            db.commit()
        catalog, history, grown_count = read()
        assert catalog['total'] == initial_catalog['total']+110
        assert history['total'] == initial_history['total']+110
        assert len(catalog['items']) == len(history['items']) == 1
        assert initial_count == grown_count == 15
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == baseline_events+110
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
        for model in [GlobalRoleAssignment, AuditEvent]:
            event.remove(model, 'load', forbid_graph)
