import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import auth
from app.auth import AuthenticationError
from app.core.config import Settings
from app.core.db import Base
from app.models.security import SecurityPrincipal


ISSUER = "https://identity.example.com"
AUDIENCE = "software-lifecycle-api"


def oidc_settings(**overrides):
    values = {
        "auth_mode": "oidc",
        "oidc_issuer_url": ISSUER,
        "oidc_audience": AUDIENCE,
        "oidc_jwks_url": f"{ISSUER}/.well-known/jwks.json",
        "oidc_leeway_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def signed_token(private_key, **claim_overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "sub": "user-123",
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def request(authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request({"type": "http", "method": "POST", "path": "/api/v1/resources", "headers": headers})


def test_oidc_configuration_is_complete_https_and_asymmetric_only():
    assert oidc_settings().oidc_algorithm_list == ["RS256"]
    with pytest.raises(ValueError, match="OIDC mode requires"):
        Settings(auth_mode="oidc")
    with pytest.raises(ValueError, match="HTTPS URL"):
        oidc_settings(oidc_jwks_url="http://identity.example.com/keys")
    with pytest.raises(ValueError, match="asymmetric"):
        oidc_settings(oidc_algorithms="HS256")


def test_bearer_header_is_strict():
    assert auth.bearer_token(request("Bearer abc.def.ghi")) == "abc.def.ghi"
    for value in (None, "Basic abc", "Bearer", "Bearer token with spaces"):
        with pytest.raises(AuthenticationError, match="missing_bearer_token"):
            auth.bearer_token(request(value))


def test_oidc_token_validates_signature_issuer_audience_and_required_claims(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    monkeypatch.setattr(
        auth,
        "jwks_client",
        lambda *_: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
        ),
    )

    claims = auth.decode_oidc_token(signed_token(private_key), oidc_settings())
    assert claims["sub"] == "user-123"

    for invalid in (
        signed_token(private_key, aud="another-api"),
        signed_token(private_key, iss="https://untrusted.example.com"),
        signed_token(private_key, exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
    ):
        with pytest.raises(AuthenticationError, match="invalid_bearer_token"):
            auth.decode_oidc_token(invalid, oidc_settings())


def test_authenticated_token_must_resolve_to_an_active_local_principal(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[SecurityPrincipal.__table__])
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    principal_id = uuid.uuid4()
    with sessions() as db:
        db.add(
            SecurityPrincipal(
                id=principal_id,
                issuer=ISSUER,
                subject="user-123",
                principal_type="USER",
                display_name="Reviewer",
                status="ACTIVE",
            )
        )
        db.commit()
    monkeypatch.setattr(auth, "SessionLocal", sessions)
    monkeypatch.setattr(
        auth,
        "decode_oidc_token",
        lambda *_: {"iss": ISSUER, "sub": "user-123"},
    )

    incoming = request("Bearer token")
    principal = auth.authenticate_write_request(incoming, oidc_settings())
    assert principal.id == principal_id
    assert incoming.state.principal == principal

    with sessions() as db:
        row = db.get(SecurityPrincipal, principal_id)
        row.status = "DISABLED"
        db.commit()
    with pytest.raises(AuthenticationError, match="disabled_principal"):
        auth.authenticate_write_request(request("Bearer token"), oidc_settings())

    monkeypatch.setattr(
        auth,
        "decode_oidc_token",
        lambda *_: {"iss": ISSUER, "sub": "unknown"},
    )
    with pytest.raises(AuthenticationError, match="unknown_principal"):
        auth.authenticate_write_request(request("Bearer token"), oidc_settings())
