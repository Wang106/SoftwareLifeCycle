import uuid

from starlette.requests import Request

from app import actor
from app.auth import AuthenticatedPrincipal


def request_with(principal):
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    request.state.principal = principal
    return request


def test_oidc_actor_uses_authenticated_identity_and_retains_declaration(monkeypatch):
    principal = AuthenticatedPrincipal(
        id=uuid.uuid4(),
        issuer="https://identity.example.com",
        subject="reviewer-1",
        principal_type="USER",
        display_name="Trusted Reviewer",
        email="reviewer@example.com",
    )
    monkeypatch.setattr(actor.settings, "auth_mode", "oidc")
    resolved = actor.resolve_actor(request_with(principal), "Claimed Manager")

    assert resolved.name == "Trusted Reviewer"
    assert resolved.principal_id == principal.id
    assert resolved.display_name == principal.display_name
    assert resolved.declared_name == "Claimed Manager"
    assert resolved.source == "AUTHENTICATED_PRINCIPAL"


def test_disabled_mode_preserves_legacy_declared_actor(monkeypatch):
    monkeypatch.setattr(actor.settings, "auth_mode", "disabled")
    resolved = actor.resolve_actor(None, " Engineer ")
    assert resolved.name == resolved.declared_name == "Engineer"
    assert resolved.principal_id is None
    assert resolved.source == "REQUEST_DECLARED"


def test_long_principal_display_name_keeps_full_audit_value(monkeypatch):
    display_name = "A" * 150
    principal = AuthenticatedPrincipal(
        id=uuid.uuid4(),
        issuer="https://identity.example.com",
        subject="service-1",
        principal_type="SERVICE",
        display_name=display_name,
        email=None,
    )
    monkeypatch.setattr(actor.settings, "auth_mode", "oidc")
    resolved = actor.resolve_actor(request_with(principal))
    assert resolved.name == "A" * 120
    assert resolved.display_name == display_name
