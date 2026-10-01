"""OIDC bearer-token validation and fail-closed local principal resolution."""

from dataclasses import dataclass
from functools import lru_cache
import uuid

import jwt
from fastapi import Request
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.security import SecurityPrincipal


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    id: uuid.UUID
    issuer: str
    subject: str
    principal_type: str
    display_name: str
    email: str | None


def bearer_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    scheme, separator, token = value.partition(" ")
    token = token.strip()
    if separator != " " or scheme.lower() != "bearer" or not token or any(ch.isspace() for ch in token):
        raise AuthenticationError("missing_bearer_token")
    if len(token) > 16384:
        raise AuthenticationError("invalid_bearer_token")
    return token


@lru_cache(maxsize=8)
def jwks_client(url: str, timeout: int):
    return jwt.PyJWKClient(url, timeout=timeout, lifespan=300)


def decode_oidc_token(token: str, settings: Settings) -> dict:
    if settings.auth_mode != "oidc":
        raise AuthenticationError("oidc_not_enabled")
    try:
        signing_key = jwks_client(
            settings.oidc_jwks_url,
            settings.oidc_jwks_timeout_seconds,
        ).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.oidc_algorithm_list,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
            leeway=settings.oidc_leeway_seconds,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise AuthenticationError("invalid_bearer_token") from exc
    subject = claims.get("sub")
    issuer = claims.get("iss")
    if not isinstance(subject, str) or not subject.strip() or not isinstance(issuer, str):
        raise AuthenticationError("invalid_bearer_token")
    return claims


def authenticate_write_request(request: Request, settings: Settings) -> AuthenticatedPrincipal:
    claims = decode_oidc_token(bearer_token(request), settings)
    with SessionLocal() as db:
        row = db.scalars(
            select(SecurityPrincipal).where(
                SecurityPrincipal.issuer == claims["iss"],
                SecurityPrincipal.subject == claims["sub"],
            )
        ).first()
        if row is None:
            raise AuthenticationError("unknown_principal")
        if row.status != "ACTIVE":
            raise AuthenticationError("disabled_principal")
        principal = AuthenticatedPrincipal(
            id=row.id,
            issuer=row.issuer,
            subject=row.subject,
            principal_type=row.principal_type,
            display_name=row.display_name,
            email=row.email,
        )
    request.state.principal = principal
    return principal
