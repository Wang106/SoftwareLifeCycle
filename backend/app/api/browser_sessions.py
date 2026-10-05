"""Own-session lifecycle, independently guarded from business commands."""
from datetime import datetime, timezone
import hashlib
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticatedPrincipal, bearer_token
from app.actor import resolve_actor
from app.core.db import get_db
from app.models.security import BrowserSession, SecurityPrincipal
from app.services.audit import AuditEventService

router = APIRouter(prefix='/api/v1/security/me/browser-sessions', tags=['browser sessions'])
MAX_ACTIVE_SESSIONS = 16


def token_digest(request):
    return hashlib.sha256(bearer_token(request).encode()).hexdigest()


def active_user(request: Request, db: Session):
    principal = getattr(request.state, 'principal', None)
    if not isinstance(principal, AuthenticatedPrincipal):
        raise HTTPException(401, 'authenticated_principal_required')
    # Serialize create/revoke and recheck ACTIVE/type in the same transaction.
    row = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == principal.id,
        SecurityPrincipal.issuer == principal.issuer, SecurityPrincipal.subject == principal.subject).with_for_update()).first()
    if row is None or row.status != 'ACTIVE':
        raise HTTPException(401, 'inactive_principal')
    if row.principal_type != 'USER':
        raise HTTPException(403, 'user_principal_required')
    return row


def require_browser_session(request, db, principal_id):
    supplied = request.headers.get('x-browser-session')
    if supplied is None:
        return None  # Ordinary bearer/API self reads have no browser-session claim.
    try:
        identifier = uuid.UUID(supplied)
    except (ValueError, AttributeError):
        raise HTTPException(401, 'invalid_browser_session')
    row = db.scalar(select(BrowserSession.id).where(BrowserSession.id == identifier,
        BrowserSession.principal_id == principal_id, BrowserSession.token_digest == token_digest(request),
        BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > datetime.now(timezone.utc)))
    if row is None:
        raise HTTPException(401, 'invalid_browser_session')
    return identifier


class CreateSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: uuid.UUID
    expires_at: int = Field(strict=True, gt=0)


def stamp(row):
    expires = row.expires_at
    if expires.tzinfo is None:  # SQLite has no timezone-aware column implementation.
        expires = expires.replace(tzinfo=timezone.utc)
    return int(expires.timestamp())


def audit(db, request, row, action):
    AuditEventService(db).record(event_no=f'EVT-BS{action[0]}-{row.id.hex}',
        event_type=f'BROWSER_SESSION_{action}', action=action, entity_type='BROWSER_SESSION',
        entity_id=row.id, entity_ref=str(row.id), summary=f'Browser session {action.lower()}',
        payload={'expires_at': stamp(row)}, **resolve_actor(request).audit_fields())


@router.post('')
def create_session(body: CreateSession, request: Request, db: Session = Depends(get_db)):
    principal = active_user(request, db)
    now = datetime.now(timezone.utc)
    expiry = getattr(request.state, 'token_expires', None)
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry) or expiry <= now.timestamp():
        raise HTTPException(401, 'invalid_token_expiry')
    if body.expires_at <= now.timestamp() or body.expires_at > min(math.floor(expiry), math.floor(now.timestamp()) + 900):
        raise HTTPException(422, 'invalid_session_expiry')
    digest = token_digest(request)
    existing = db.get(BrowserSession, body.id)
    if existing is not None:
        if existing.principal_id != principal.id or existing.token_digest != digest or stamp(existing) != body.expires_at or existing.revoked_at is not None:
            raise HTTPException(409, 'session_id_conflict')
        return {'id': existing.id, 'expires_at': stamp(existing)}
    count = db.scalar(select(func.count()).select_from(BrowserSession).where(BrowserSession.principal_id == principal.id,
        BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > now))
    if count >= MAX_ACTIVE_SESSIONS:
        raise HTTPException(429, 'active_session_limit', headers={'Retry-After': '900'})
    row = BrowserSession(id=body.id, principal_id=principal.id, token_digest=digest, created_at=now,
        expires_at=datetime.fromtimestamp(body.expires_at, timezone.utc))
    try:
        db.add(row); db.flush(); audit(db, request, row, 'CREATED'); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'session_id_conflict')
    except Exception:
        db.rollback(); raise
    return {'id': row.id, 'expires_at': stamp(row)}


@router.post('/{session_id}/revoke')
def revoke_session(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    principal = active_user(request, db)
    row = db.get(BrowserSession, session_id)
    if row is None or row.principal_id != principal.id or row.token_digest != token_digest(request):
        raise HTTPException(404, 'session_not_found')
    if row.revoked_at is None:
        try:
            row.revoked_at = datetime.now(timezone.utc); db.flush(); audit(db, request, row, 'REVOKED'); db.commit()
        except Exception:
            db.rollback(); raise
    return {'id': row.id, 'status': 'revoked'}
