"""Intranet Entra ID pilot: access follows a pre-registered company mailbox.

Generic OIDC still uses the token subject. This module runs only when
INTRANET_PILOT is enabled. It does not contact Microsoft. An oid in the token
may be copied into an audit event; it never selects or rejects the account.
"""
import hashlib
import re
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

NIL_TENANT = "00000000-0000-0000-0000-000000000000"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ISSUER = re.compile(
    r"^https://login\.microsoftonline\.com/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/v2\.0$"
)
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_LOCAL = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}$")
PENDING = "pending-email:"


def parse_email_domains(value: str) -> list[str]:
    parts = [item.strip().lower() for item in (value or "").split(",") if item.strip()]
    if any(not _DOMAIN.fullmatch(part) for part in parts) or len(parts) != len(set(parts)):
        raise ValueError("OIDC_EMAIL_DOMAINS must be unique exact DNS names")
    return parts


def tenant_id(issuer: str) -> str:
    match = _ISSUER.fullmatch(issuer or "")
    if match is None:
        raise ValueError("INTRANET_PILOT issuer must be https://login.microsoftonline.com/<tenant-id>/v2.0")
    tenant = match.group(1)
    if tenant == NIL_TENANT:
        raise ValueError("INTRANET_PILOT tenant id is still a placeholder")
    return tenant


def derived_urls(issuer: str) -> dict[str, str]:
    tenant = tenant_id(issuer)
    return {
        "jwks": f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        "discovery": f"{issuer}/.well-known/openid-configuration",
        "authorization": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    }


def pending_subject(email: str) -> str:
    return PENDING + email


def _placeholder(value: str) -> bool:
    lowered = (value or "").lower()
    return "replace_me" in lowered or "example.invalid" in lowered or NIL_TENANT in lowered


def _https(name: str, value: str) -> None:
    parsed = urlsplit(value or "")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError(f"{name} must be an HTTPS URL without credentials, query or fragment")


def validate_pilot(settings) -> None:
    if settings.auth_mode != "oidc":
        raise ValueError("INTRANET_PILOT requires AUTH_MODE=oidc")
    if settings.seed_on_startup or settings.seed_zfi_demo:
        raise ValueError("INTRANET_PILOT refuses demo seed")
    domains = parse_email_domains(settings.oidc_email_domains)
    if not domains:
        raise ValueError("INTRANET_PILOT requires OIDC_EMAIL_DOMAINS")
    issuer = settings.oidc_issuer_url or ""
    urls = derived_urls(issuer)
    audience = (settings.oidc_audience or "").lower()
    client = (settings.oidc_client_id or "").lower()
    if not _UUID.fullmatch(audience) or audience != client or audience == NIL_TENANT:
        raise ValueError("INTRANET_PILOT audience and client id must be the same Entra application id")
    for name, value in (
        ("OIDC_JWKS_URL", settings.oidc_jwks_url),
        ("OIDC_AUTHORIZATION_URL", settings.oidc_authorization_url),
        ("OIDC_TOKEN_URL", settings.oidc_token_url),
    ):
        _https(name, value or "")
    if settings.oidc_jwks_url != urls["jwks"]:
        raise ValueError("INTRANET_PILOT JWKS URL must be the Entra discovery v2.0 keys URL for this tenant")
    if settings.oidc_authorization_url != urls["authorization"] or settings.oidc_token_url != urls["token"]:
        raise ValueError("INTRANET_PILOT authorization and token URLs must be the Entra v2.0 endpoints for this tenant")
    email = normalize_mailbox(settings.intranet_pilot_bootstrap_email, domains)
    if _placeholder(issuer) or _placeholder(audience) or _placeholder(email) or any(_placeholder(item) for item in domains):
        raise ValueError("INTRANET_PILOT still contains placeholder identity values")
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if not origins:
        raise ValueError("INTRANET_PILOT requires an internal HTTPS CORS origin")
    for origin in origins:
        _https("CORS_ORIGINS", origin)
        if urlsplit(origin).path not in ("", "/"):
            raise ValueError("INTRANET_PILOT CORS origin must not include a path")
        if _placeholder(origin) or "softwarelifecycle.whf969.com" in origin.lower():
            raise ValueError("INTRANET_PILOT CORS must be the internal application origin")
    settings.intranet_pilot_bootstrap_email = email


def normalize_mailbox(value: str, domains: list[str]) -> str:
    mailbox = (value or "").strip().lower()
    local, separator, domain = mailbox.partition("@")
    if (not separator or "@" in local or not _LOCAL.fullmatch(local) or domain not in domains):
        raise ValueError("company mailbox must use a configured domain")
    return mailbox


def presented_mailboxes(claims: dict, domains: list[str]) -> set[str]:
    from app.auth import AuthenticationError
    if claims.get("email_verified") is False:
        raise AuthenticationError("email_domain_rejected")
    found = set()
    for key in ("preferred_username", "email"):
        if key not in claims or claims[key] is None:
            continue
        raw = claims[key]
        if not isinstance(raw, str):
            raise AuthenticationError("email_domain_rejected")
        try:
            found.add(normalize_mailbox(raw, domains))
        except ValueError:
            raise AuthenticationError("email_domain_rejected") from None
    if not found:
        raise AuthenticationError("email_domain_rejected")
    return found


def observe_oid(db: Session, row, claims: dict) -> None:
    """Record oid for traceability. Absence or a later change does not affect access."""
    from sqlalchemy import select
    from app.models.audit import AuditEvent
    from app.services.audit import AuditEventService
    oid = claims.get("oid")
    if not isinstance(oid, str) or not _UUID.fullmatch(oid) or oid == NIL_TENANT:
        return
    digest = hashlib.sha256(f"{row.id}:{oid}".encode()).hexdigest()[:32]
    event_no = f"OBS{digest}"
    if db.scalars(select(AuditEvent).where(AuditEvent.event_no == event_no)).first() is not None:
        return
    tid = claims.get("tid") if isinstance(claims.get("tid"), str) else None
    AuditEventService(db).record(
        event_no=event_no, event_type="ENTRA_OID_OBSERVED", action="OBSERVE",
        entity_type="SECURITY_PRINCIPAL", entity_id=row.id, entity_ref=str(row.id),
        actor_name="EntraEmailTrace", actor_principal_id=row.id, actor_display_name=row.display_name,
        summary="Observed Entra oid for a registered mailbox; not used for access",
        payload={"principal_id": str(row.id), "oid": oid, "tid": tid, "authorizes": False},
    )


def resolve_pilot_principal(db: Session, claims: dict, settings):
    """Grant the pre-registered mailbox. oid is not an access key."""
    from sqlalchemy import func, select
    from app.auth import AuthenticationError
    from app.models.security import SecurityPrincipal
    if claims.get("iss") != settings.oidc_issuer_url:
        raise AuthenticationError("untrusted_tenant")
    tenant = tenant_id(settings.oidc_issuer_url)
    if claims.get("tid") != tenant:
        raise AuthenticationError("untrusted_tenant")
    mailboxes = presented_mailboxes(claims, parse_email_domains(settings.oidc_email_domains))
    issuer = settings.oidc_issuer_url
    rows = db.scalars(select(SecurityPrincipal).where(
        SecurityPrincipal.issuer == issuer,
        func.lower(SecurityPrincipal.email).in_(list(mailboxes)),
    ).with_for_update()).all()
    matches = [row for row in rows if (row.email or "").strip().lower() in mailboxes]
    if not matches:
        raise AuthenticationError("unregistered_email")
    if len(matches) != 1:
        raise AuthenticationError("email_registration_ambiguous")
    row = matches[0]
    if row.subject != pending_subject((row.email or "").strip().lower()):
        raise AuthenticationError("unregistered_email")
    if row.status != "ACTIVE":
        raise AuthenticationError("disabled_principal")
    try:
        observe_oid(db, row, claims)
    except Exception:
        db.rollback()
    return row
