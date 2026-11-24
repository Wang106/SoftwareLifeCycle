"""Intranet Entra mailbox binding. No network and no real tenant."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import AuthenticationError
from app.core.config import Settings
from app.core.db import Base
from app.intranet_pilot import (
    derived_urls, pending_subject, presented_mailboxes, resolve_pilot_principal,
)
from app.models.security import SecurityPrincipal

ROOT = Path(__file__).resolve().parents[2]
TENANT = "11111111-2222-4333-8444-555555555555"
CLIENT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
OID = "99999999-8888-4777-8666-555555555555"


def pilot(**overrides):
    urls = derived_urls(ISSUER)
    values = {
        "intranet_pilot": True,
        "auth_mode": "oidc",
        "read_only_mode": False,
        "seed_on_startup": False,
        "seed_zfi_demo": False,
        "oidc_issuer_url": ISSUER,
        "oidc_audience": CLIENT,
        "oidc_client_id": CLIENT,
        "oidc_jwks_url": urls["jwks"],
        "oidc_authorization_url": urls["authorization"],
        "oidc_token_url": urls["token"],
        "oidc_email_domains": "corp.example",
        "intranet_pilot_bootstrap_email": "admin@corp.example",
        "cors_origins": "https://app.corp.example",
        "oidc_leeway_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_default_configuration_leaves_the_pilot_off():
    settings = Settings(_env_file=None)
    assert settings.intranet_pilot is False
    assert settings.auth_mode == "disabled"
    assert settings.seed_on_startup is False


def test_pilot_rejects_placeholders_seed_and_public_origin():
    with pytest.raises(ValueError, match="placeholder"):
        text = (ROOT / "deploy/intranet-pilot.env.example").read_text()
        values = {}
        for line in text.splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
        Settings(_env_file=None, intranet_pilot=True, auth_mode="oidc", read_only_mode=False,
                 seed_on_startup=False, oidc_issuer_url=values["OIDC_ISSUER_URL"],
                 oidc_audience=values["OIDC_AUDIENCE"], oidc_client_id=values["OIDC_CLIENT_ID"],
                 oidc_jwks_url=values["OIDC_JWKS_URL"], oidc_authorization_url=values["OIDC_AUTHORIZATION_URL"],
                 oidc_token_url=values["OIDC_TOKEN_URL"], oidc_email_domains=values["OIDC_EMAIL_DOMAINS"],
                 intranet_pilot_bootstrap_email=values["INTRANET_PILOT_BOOTSTRAP_EMAIL"],
                 cors_origins=values["CORS_ORIGINS"])
    with pytest.raises(ValueError, match="demo seed"):
        pilot(seed_on_startup=True)
    with pytest.raises(ValueError, match="AUTH_MODE"):
        pilot(auth_mode="disabled")
    with pytest.raises(ValueError, match="CORS"):
        pilot(cors_origins="https://softwarelifecycle.whf969.com")
    overlay = (ROOT / "docker-compose.intranet-pilot.yml").read_text()
    assert 'AUTH_MODE: oidc' in overlay and 'SEED_ON_STARTUP: "false"' in overlay
    assert "INTRANET_PILOT: \"true\"" in overlay
    guide = (ROOT / "docs/intranet-pilot-guide.md").read_text()
    assert "/auth/callback" in guide and "App Roles" in guide and "overage" in guide
    assert "00000000-0000-0000-0000-000000000000" not in guide or "占位" in guide


def test_observed_oid_is_audit_only():
    recorded = {}
    class Query:
        def first(self):
            return None
    class Database:
        def scalars(self, _statement):
            return Query()
    class Service:
        def __init__(self, _db):
            pass
        def record(self, **kwargs):
            recorded.update(kwargs)
    import app.services.audit as audit
    import app.intranet_pilot as pilot_module
    original = audit.AuditEventService
    audit.AuditEventService = Service
    try:
        row = type("Row", (), {"id": uuid.uuid4(), "display_name": "Admin"})()
        pilot_module.observe_oid(Database(), row, {"oid": OID, "tid": TENANT})
        pilot_module.observe_oid(Database(), row, {"oid": "not-an-oid"})
    finally:
        audit.AuditEventService = original
    assert recorded["event_type"] == "ENTRA_OID_OBSERVED"
    assert recorded["payload"]["authorizes"] is False
    assert recorded["payload"]["oid"] == OID


def test_mailbox_match_is_case_insensitive_and_domain_limited():
    domains = ["corp.example"]
    assert presented_mailboxes({"preferred_username": "Admin@Corp.Example"}, domains) == {"admin@corp.example"}
    with pytest.raises(AuthenticationError, match="email_domain_rejected"):
        presented_mailboxes({"email": "person@gmail.com"}, domains)
    with pytest.raises(AuthenticationError, match="email_domain_rejected"):
        presented_mailboxes({"email": "person@corp.example", "email_verified": False}, domains)


def claims(oid=OID, email="person@corp.example", tid=TENANT):
    now = datetime.now(timezone.utc)
    return {"iss": ISSUER, "sub": "pairwise-subject", "aud": CLIENT, "tid": tid, "oid": oid,
            "preferred_username": email, "iat": now, "exp": now + timedelta(minutes=5)}


def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[SecurityPrincipal.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_mailbox(sessions, email, status="ACTIVE"):
    identifier = uuid.uuid4()
    with sessions() as db:
        db.add(SecurityPrincipal(id=identifier, issuer=ISSUER, subject=pending_subject(email), email=email,
                                 principal_type="USER", display_name="Colleague", status=status))
        db.commit()
    return identifier


def test_registered_mailbox_authorizes_without_binding_oid(monkeypatch):
    seen = []
    monkeypatch.setattr("app.intranet_pilot.observe_oid", lambda _db, row, token: seen.append((row.subject, token.get("oid"))))
    sessions = database()
    settings = pilot()
    identifier = add_mailbox(sessions, "person@corp.example")
    original = pending_subject("person@corp.example")
    with sessions() as db:
        row = resolve_pilot_principal(db, claims(), settings)
        assert row.id == identifier
        assert row.subject == original
        db.commit()
    other = "12121212-3434-4545-8686-787878787878"
    with sessions() as db:
        again = resolve_pilot_principal(db, claims(email="Person@corp.example", oid=other), settings)
        assert again.id == identifier
        assert again.subject == original
    assert seen == [(original, OID), (original, other)]
    with pytest.raises(AuthenticationError, match="unregistered_email"):
        with sessions() as db:
            resolve_pilot_principal(db, claims(email="other@corp.example", oid="13131313-1313-4131-8131-131313131313"), settings)
    with pytest.raises(AuthenticationError, match="untrusted_tenant"):
        with sessions() as db:
            resolve_pilot_principal(db, claims(tid="22222222-2222-4222-8222-222222222222"), settings)
    with pytest.raises(AuthenticationError, match="unregistered_email"):
        with sessions() as db:
            resolve_pilot_principal(db, claims(email="renamed@corp.example"), settings)
    with pytest.raises(AuthenticationError, match="disabled_principal"):
        disabled = add_mailbox(sessions, "quiet@corp.example", status="DISABLED")
        assert disabled
        with sessions() as db:
            resolve_pilot_principal(db, claims(email="quiet@corp.example", oid="14141414-1414-4141-8141-141414141414"), settings)
