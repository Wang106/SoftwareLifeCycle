"""Audited status changes for existing exact project/software role assignments."""
from typing import Literal
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.actor import resolve_actor
from app.auth import AuthenticatedPrincipal
from app.api.browser_sessions import require_browser_session
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.services.audit import AuditEventError, AuditEventService

router = APIRouter(prefix='/api/v1/security/admin/memberships', tags=['membership administration'])
Scope = Literal['PROJECT', 'SOFTWARE']
Status = Literal['ACTIVE', 'SUSPENDED']

class MembershipStatusChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_no: str = Field(min_length=1, max_length=50, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')
    expected_status: Status
    status: Status
    reason: str = Field(min_length=5, max_length=500)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value):
        value = value.strip()
        if len(value) < 5 or any(ord(char) < 32 for char in value):
            raise ValueError('A printable reason of at least five characters is required')
        return value

    @model_validator(mode='after')
    def distinct_states(self):
        if self.expected_status == self.status:
            raise ValueError('A status transition is required')
        return self


def active_admin(request: Request, db: Session):
    if settings.read_only_mode:
        raise HTTPException(403, 'read_only_mode')
    if settings.auth_mode != 'oidc':
        raise HTTPException(401, 'oidc_not_enabled')
    principal = getattr(request.state, 'principal', None)
    if not isinstance(principal, AuthenticatedPrincipal):
        raise HTTPException(401, 'authenticated_principal_required')
    row = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == principal.id,
        SecurityPrincipal.issuer == principal.issuer, SecurityPrincipal.subject == principal.subject)
        .with_for_update()).first()
    if row is None or row.status != 'ACTIVE':
        raise HTTPException(401, 'inactive_principal')
    grant = db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.principal_id == row.id,
        GlobalRoleAssignment.role == 'PLATFORM_ADMIN').with_for_update())
    if grant is None:
        raise HTTPException(403, 'platform_admin_required')
    require_browser_session(request, db, row.id)
    return row


def result(row, scope, body, replayed):
    return {'membership_id': row.id, 'scope': scope, 'applied_status': body.status,
        'current_status': row.status, 'replayed': replayed, 'audit_event_no': body.event_no}


@router.post('/{scope}/{membership_id}/status')
def change_status(scope: Scope, membership_id: uuid.UUID, body: MembershipStatusChange,
                  request: Request, db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        model = ProjectMembership if scope == 'PROJECT' else SoftwareMembership
        row = db.scalars(select(model).where(model.id == membership_id).with_for_update()
                         .execution_options(populate_existing=True)).first()
        if row is None:
            raise HTTPException(404, 'membership_not_found')
        payload = {'scope': scope, 'membership_id': str(row.id), 'principal_id': str(row.principal_id),
            'scope_id': str(row.project_id if scope == 'PROJECT' else row.software_id), 'role': row.role,
            'expected_status': body.expected_status, 'status': body.status, 'reason': body.reason}
        existing = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
        if existing is not None:
            if (existing.event_type != 'MEMBERSHIP_STATUS_CHANGED' or existing.entity_type != scope+'_MEMBERSHIP'
                or existing.entity_id != row.id or existing.actor_principal_id != administrator.id
                or existing.payload_json != payload):
                raise HTTPException(409, 'audit_event_conflict')
            response = result(row, scope, body, True)
            db.commit()
            return response
        if row.status != body.expected_status:
            raise HTTPException(409, 'membership_status_conflict')
        recipient = db.get(SecurityPrincipal, row.principal_id)
        if body.status == 'ACTIVE' and (recipient is None or recipient.status != 'ACTIVE'):
            raise HTTPException(409, 'recipient_inactive')
        row.status = body.status
        db.flush()
        AuditEventService(db).record(event_no=body.event_no, event_type='MEMBERSHIP_STATUS_CHANGED',
            action='SUSPEND' if body.status == 'SUSPENDED' else 'RESUME', entity_type=scope+'_MEMBERSHIP',
            entity_id=row.id, entity_ref=str(row.id), summary=f'{scope.title()} membership {body.status.lower()}',
            payload=payload, **resolve_actor(request).audit_fields())
        response = result(row, scope, body, False)
        db.commit()
        return response
    except (IntegrityError, AuditEventError):
        db.rollback()
        raise HTTPException(409, 'audit_event_conflict')
    except Exception:
        db.rollback()
        raise
