import inspect

from app.main import app
from app.security_roles import ALL_ROLES
from app.write_contracts import WRITE_CONTRACTS, SESSION_CONTROL_CONTRACTS, ADMIN_CONTROL_CONTRACTS


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def registered_write_routes():
    return {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set()) - SAFE_METHODS
    }


def test_every_registered_write_route_has_exactly_one_reviewed_contract():
    assert not set(WRITE_CONTRACTS) & set(SESSION_CONTROL_CONTRACTS)
    assert not set(ADMIN_CONTROL_CONTRACTS) & (set(WRITE_CONTRACTS) | set(SESSION_CONTROL_CONTRACTS))
    assert set(WRITE_CONTRACTS) | set(SESSION_CONTROL_CONTRACTS) | set(ADMIN_CONTROL_CONTRACTS) == registered_write_routes()


def test_current_write_contracts_remain_non_public_and_explicitly_protected():
    assert WRITE_CONTRACTS
    for contract in WRITE_CONTRACTS.values():
        assert contract.public_exposure == "READ_ONLY_BLOCKED"
        assert contract.authentication == "OIDC_WHEN_ENABLED"
        assert contract.authorization == "SCOPED_WHEN_OIDC"
        assert contract.actor_binding in {"AUTHENTICATED_WHEN_OIDC", "NO_ACTOR_SINK"}
        if contract.audit == "ATOMIC_APPEND":
            assert contract.actor_binding == "AUTHENTICATED_WHEN_OIDC"
        else:
            assert contract.actor_binding == "NO_ACTOR_SINK"
        assert contract.actor_source in {"NONE", "DECLARED_OPTIONAL", "DECLARED_REQUIRED"}
        assert contract.audit in {"NONE", "ATOMIC_APPEND"}
        assert contract.idempotency in {"NONE", "REQUEST_ID"}
        assert contract.concurrency in {"NONE", "ROW_LOCK"}
        assert contract.planned_roles
        assert contract.planned_roles <= ALL_ROLES
        assert contract.known_gap.strip()


def test_every_write_route_invokes_a_scoped_authorization_guard():
    for route in app.routes:
        if any((method, route.path) in WRITE_CONTRACTS for method in getattr(route, "methods", set())):
            assert "authorize_" in inspect.getsource(route.endpoint), route.path


def test_every_audited_write_route_resolves_a_trusted_actor():
    routes = {
        (method, route.path): route
        for route in app.routes
        for method in getattr(route, "methods", set()) - SAFE_METHODS
    }
    for key, contract in WRITE_CONTRACTS.items():
        if contract.audit == "ATOMIC_APPEND":
            assert "resolve_actor" in inspect.getsource(routes[key].endpoint), key


def test_session_controls_have_explicit_self_authentication_and_atomic_audit_contracts():
    assert len(SESSION_CONTROL_CONTRACTS) == 2
    for contract in SESSION_CONTROL_CONTRACTS.values():
        assert contract.authentication == 'OIDC_REQUIRED'
        assert contract.authorization == 'ACTIVE_USER_SELF_AND_TOKEN'
        assert contract.public_exposure == 'AUTHENTICATED_METADATA_ONLY'
        assert contract.audit == 'ATOMIC_APPEND'
        assert contract.concurrency == 'PRINCIPAL_ROW_LOCK'
    for route in app.routes:
        if any((method, route.path) in SESSION_CONTROL_CONTRACTS for method in getattr(route, 'methods', set())):
            assert 'active_user' in inspect.getsource(route.endpoint)
            assert 'audit(' in inspect.getsource(route.endpoint)


def test_admin_status_contract_is_independently_authenticated_audited_and_read_only_blocked():
    assert len(ADMIN_CONTROL_CONTRACTS) == 3
    for contract in ADMIN_CONTROL_CONTRACTS.values():
        assert contract.authentication == 'OIDC_REQUIRED'
        assert contract.authorization == 'ACTIVE_PLATFORM_ADMIN'
        assert contract.public_exposure == 'READ_ONLY_BLOCKED'
        assert contract.audit == 'ATOMIC_APPEND'
        assert contract.idempotency == 'EVENT_NO_EXACT_REQUEST_AND_ADMIN'
    assert {key[1]: value.precondition for key, value in ADMIN_CONTROL_CONTRACTS.items()} == {
        '/api/v1/security/admin/memberships/{scope}/{membership_id}/status': 'EXPECTED_MEMBERSHIP_STATUS',
        '/api/v1/security/admin/principals': 'CONFIGURED_ISSUER_AND_NEW_UUID_AND_SUBJECT',
        '/api/v1/security/admin/principals/{principal_id}/status': 'EXPECTED_PRINCIPAL_STATUS_AND_NO_PLATFORM_ADMIN_GRANT',
    }
    for route in app.routes:
        if any((method, route.path) in ADMIN_CONTROL_CONTRACTS for method in getattr(route, 'methods', set())):
            source = inspect.getsource(route.endpoint)
            assert 'active_admin(' in source and 'resolve_actor(' in source
            assert 'AuditEventService(db).record' in source
