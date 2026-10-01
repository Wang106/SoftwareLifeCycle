"""Resolve trusted write actors while retaining legacy request declarations."""

from dataclasses import dataclass
import uuid

from fastapi import Request

from app.auth import AuthenticatedPrincipal
from app.authorization import AuthorizationError
from app.core.config import settings


@dataclass(frozen=True)
class ActorContext:
    name: str
    principal_id: uuid.UUID | None
    display_name: str | None
    declared_name: str | None
    source: str

    @classmethod
    def legacy(cls, declared_name: str | None):
        declared = declared_name.strip() if declared_name and declared_name.strip() else None
        return cls(
            name=declared or "Not recorded",
            principal_id=None,
            display_name=None,
            declared_name=declared,
            source="REQUEST_DECLARED" if declared else "NOT_PROVIDED",
        )

    def audit_fields(self) -> dict:
        return {
            "actor_name": self.name,
            "actor_principal_id": self.principal_id,
            "actor_display_name": self.display_name,
            "declared_actor_name": self.declared_name,
        }


def resolve_actor(request: Request | None, declared_name: str | None = None) -> ActorContext:
    if settings.auth_mode != "oidc":
        return ActorContext.legacy(declared_name)
    principal = getattr(request.state, "principal", None) if request is not None else None
    if not isinstance(principal, AuthenticatedPrincipal):
        raise AuthorizationError("authenticated_principal_required")
    display_name = principal.display_name.strip()
    effective_name = (display_name or principal.subject).strip()[:120]
    declared = declared_name.strip() if declared_name and declared_name.strip() else None
    return ActorContext(
        name=effective_name,
        principal_id=principal.id,
        display_name=display_name or principal.subject,
        declared_name=declared,
        source="AUTHENTICATED_PRINCIPAL",
    )


def audit_actor_matches(event, actor: ActorContext) -> bool:
    return (
        event.actor_name == actor.name
        and event.actor_principal_id == actor.principal_id
        and event.actor_display_name == actor.display_name
        and event.declared_actor_name == actor.declared_name
    )


def idempotent_actor_matches(event, actor: ActorContext) -> bool:
    """Legacy retries keep old behavior; authenticated retries require the same principal/declaration."""
    return actor.principal_id is None or (event is not None and audit_actor_matches(event, actor))
