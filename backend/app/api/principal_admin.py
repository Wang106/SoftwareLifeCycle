"""Local identity registration and status; never provision provider accounts or roles."""
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actor import resolve_actor
from app.api.membership_admin import active_admin
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, SecurityPrincipal
from app.services.audit import AuditEventService

router = APIRouter(prefix='/api/v1/security/admin/principals', tags=['principal administration'])
Status = Literal['ACTIVE', 'DISABLED']


class AuditedRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_no: str = Field(min_length=1, max_length=50, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')
    reason: str = Field(min_length=5, max_length=500)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value):
        value = value.strip()
        if len(value) < 5 or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('A printable reason of at least five characters is required')
        return value


class RegisterPrincipal(AuditedRequest):
    principal_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=500)
    principal_type: Literal['USER', 'SERVICE']
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator('subject', 'display_name')
    @classmethod
    def printable_exact_value(cls, value):
        # Provider subjects are opaque: reject ambiguous whitespace, never normalize.
        if value != value.strip() or not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('A bounded printable value without surrounding whitespace is required')
        return value


class PrincipalStatusChange(AuditedRequest):
    expected_status: Status
    status: Status

    @model_validator(mode='after')
    def distinct_states(self):
        if self.expected_status == self.status:
            raise ValueError('A status transition is required')
        return self


def registration_payload(body, issuer):
    canonical = json.dumps({'issuer': issuer, **body.model_dump(mode='json', exclude={'event_no'})},
                           ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    # Preserve exact retry binding without duplicating issuer, subject or name in audit.
    return {'principal_id': str(body.principal_id), 'principal_type': body.principal_type,
            'status': 'DISABLED', 'reason': body.reason,
            'request_digest': hashlib.sha256(canonical.encode()).hexdigest()}


def matches(event, administrator, identifier, event_type, payload):
    return (event.event_type == event_type and event.entity_type == 'SECURITY_PRINCIPAL'
            and event.entity_id == identifier and event.entity_ref == str(identifier)
            and event.actor_principal_id == administrator.id and event.payload_json == payload)


def result(row, status, body, replayed, revoked=0):
    return {'principal_id': row.id, 'applied_status': status, 'current_status': row.status,
            'replayed': replayed, 'audit_event_no': body.event_no,
            'revoked_browser_sessions': revoked}


@router.post('')
def register_principal(body: RegisterPrincipal, request: Request, db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        issuer = settings.oidc_issuer_url
        if not issuer or len(issuer) > 500:
            raise HTTPException(503, 'configured_issuer_required')
        payload = registration_payload(body, issuer)
        existing = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
        if existing is not None:
            if not matches(existing, administrator, body.principal_id, 'PRINCIPAL_REGISTERED', payload):
                raise HTTPException(409, 'audit_event_conflict')
            row = db.get(SecurityPrincipal, body.principal_id)
            if row is None:
                raise HTTPException(409, 'principal_registration_conflict')
            response = result(row, 'DISABLED', body, True)
            db.commit()
            return response
        if db.scalar(select(SecurityPrincipal.id).where(
                (SecurityPrincipal.id == body.principal_id) |
                ((SecurityPrincipal.issuer == issuer) & (SecurityPrincipal.subject == body.subject)))):
            raise HTTPException(409, 'principal_registration_conflict')
        row = SecurityPrincipal(id=body.principal_id, issuer=issuer, subject=body.subject,
            principal_type=body.principal_type, display_name=body.display_name, status='DISABLED')
        db.add(row)
        db.flush()
        AuditEventService(db).record(event_no=body.event_no, event_type='PRINCIPAL_REGISTERED',
            action='REGISTER', entity_type='SECURITY_PRINCIPAL', entity_id=row.id, entity_ref=str(row.id),
            summary='Local principal registered disabled without grants', payload=payload,
            **resolve_actor(request).audit_fields())
        response = result(row, 'DISABLED', body, False)
        db.commit()
        return response
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'principal_registration_conflict')
    except Exception:
        db.rollback()
        raise


@router.post('/{principal_id}/status')
def change_principal_status(principal_id: uuid.UUID, body: PrincipalStatusChange,
                            request: Request, db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        # Avoid actor->target cycles between administrators. All platform-admin
        # identities, including self and disabled admins, require a recovery policy.
        if db.scalar(select(GlobalRoleAssignment.id).where(
                GlobalRoleAssignment.principal_id == principal_id,
                GlobalRoleAssignment.role == 'PLATFORM_ADMIN')):
            raise HTTPException(409, 'admin_principal_protected')
        row = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == principal_id)
                         .with_for_update().execution_options(populate_existing=True)).first()
        if row is None:
            raise HTTPException(404, 'principal_not_found')
        # Recheck for unsupported out-of-band changes before changing state.
        if db.scalar(select(GlobalRoleAssignment.id).where(
                GlobalRoleAssignment.principal_id == principal_id,
                GlobalRoleAssignment.role == 'PLATFORM_ADMIN')):
            raise HTTPException(409, 'admin_principal_protected')
        payload = {'principal_id': str(row.id), 'expected_status': body.expected_status,
                   'status': body.status, 'reason': body.reason}
        existing = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
        if existing is not None:
            stored = existing.payload_json or {}
            if not isinstance(stored, dict):
                raise HTTPException(409, 'audit_event_conflict')
            revoked = stored.get('revoked_browser_sessions')
            if (not isinstance(revoked, int) or isinstance(revoked, bool) or revoked < 0
                    or not matches(existing, administrator, row.id, 'PRINCIPAL_STATUS_CHANGED',
                                   {**payload, 'revoked_browser_sessions': revoked})):
                raise HTTPException(409, 'audit_event_conflict')
            response = result(row, body.status, body, True, revoked)
            db.commit()
            return response
        if row.status != body.expected_status:
            raise HTTPException(409, 'principal_status_conflict')
        revoked = 0
        if body.status == 'DISABLED':
            # Own-session create/revoke share this principal lock. Re-enabling the
            # identity must never revive a copied cookie registered before disable.
            revoked = db.execute(update(BrowserSession).where(BrowserSession.principal_id == row.id,
                BrowserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc))
                .execution_options(synchronize_session=False)).rowcount
        row.status = body.status
        db.flush()
        AuditEventService(db).record(event_no=body.event_no, event_type='PRINCIPAL_STATUS_CHANGED',
            action='DISABLE' if body.status == 'DISABLED' else 'ENABLE', entity_type='SECURITY_PRINCIPAL',
            entity_id=row.id, entity_ref=str(row.id), summary=f'Local principal {body.status.lower()}',
            payload={**payload, 'revoked_browser_sessions': revoked}, **resolve_actor(request).audit_fields())
        response = result(row, body.status, body, False, revoked)
        db.commit()
        return response
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'audit_event_conflict')
    except Exception:
        db.rollback()
        raise
