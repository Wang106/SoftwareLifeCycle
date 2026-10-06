"""Audited suspended-first global grants with serialized last-admin protection."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actor import resolve_actor
from app.api.membership_admin import active_admin
from app.api.principal_admin import AuditedRequest
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, SecurityPrincipal
from app.services.audit import AuditEventError, AuditEventService

router = APIRouter(prefix='/api/v1/security/admin/global-roles', tags=['global role administration'])


class RegisterGlobalRole(AuditedRequest):
    grant_id: uuid.UUID
    principal_id: uuid.UUID
    role: Literal['PLATFORM_ADMIN', 'AUDITOR']


class GlobalRoleStatusChange(AuditedRequest):
    expected_status: Literal['ACTIVE', 'SUSPENDED']
    status: Literal['ACTIVE', 'SUSPENDED']

    @model_validator(mode='after')
    def distinct_states(self):
        if self.expected_status == self.status:
            raise ValueError('A status transition is required')
        return self


def receipt(row, body, applied_status, replayed):
    return {'grant_id': row.id, 'scope': 'GLOBAL', 'principal_id': row.principal_id,
            'role': row.role, 'applied_status': applied_status, 'current_status': row.status,
            'replayed': replayed, 'audit_event_no': body.event_no}


def replay(db, body, administrator, row_id, event_type, payload):
    event = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
    if event is None:
        return False
    if (event.event_type != event_type or event.entity_type != 'GLOBAL_ROLE'
        or event.entity_id != row_id or event.entity_ref != str(row_id)
        or event.actor_principal_id != administrator.id or event.payload_json != payload):
        raise HTTPException(409, 'audit_event_conflict')
    return True


def recipient(db, principal_id):
    row = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == principal_id)
        .with_for_update().execution_options(populate_existing=True)).first()
    if row is None:
        raise HTTPException(404, 'principal_not_found')
    return row


def eligible(row):
    if row.status != 'ACTIVE':
        raise HTTPException(409, 'recipient_inactive')
    if row.issuer != settings.oidc_issuer_url:
        raise HTTPException(409, 'recipient_issuer_mismatch')


@router.post('')
def register_global_role(body: RegisterGlobalRole, request: Request, db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        target = recipient(db, body.principal_id)
        payload = {'grant_id': str(body.grant_id), 'principal_id': str(body.principal_id),
                   'role': body.role, 'status': 'SUSPENDED', 'reason': body.reason}
        repeated = replay(db, body, administrator, body.grant_id, 'GLOBAL_ROLE_REGISTERED', payload)
        if repeated:
            row = db.scalars(select(GlobalRoleAssignment).where(GlobalRoleAssignment.id == body.grant_id,
                GlobalRoleAssignment.principal_id == body.principal_id, GlobalRoleAssignment.role == body.role)
                .execution_options(populate_existing=True)).first()
            if row is None:
                raise HTTPException(409, 'global_role_registration_conflict')
        else:
            eligible(target)
            if db.scalar(select(GlobalRoleAssignment.id).where((GlobalRoleAssignment.id == body.grant_id) |
                ((GlobalRoleAssignment.principal_id == body.principal_id) & (GlobalRoleAssignment.role == body.role)))) is not None:
                raise HTTPException(409, 'global_role_registration_conflict')
            row = GlobalRoleAssignment(id=body.grant_id, principal_id=body.principal_id,
                                       role=body.role, status='SUSPENDED')
            db.add(row)
            db.flush()
            AuditEventService(db).record(event_no=body.event_no, event_type='GLOBAL_ROLE_REGISTERED',
                action='REGISTER', entity_type='GLOBAL_ROLE', entity_id=row.id, entity_ref=str(row.id),
                summary='Global role registered suspended', payload=payload, **resolve_actor(request).audit_fields())
        response = receipt(row, body, 'SUSPENDED', repeated)
        db.commit()
        return response
    except (IntegrityError, AuditEventError):
        db.rollback()
        raise HTTPException(409, 'global_role_registration_conflict')
    except Exception:
        db.rollback()
        raise


@router.post('/{grant_id}/status')
def change_global_role_status(grant_id: uuid.UUID, body: GlobalRoleStatusChange,
                              request: Request, db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        row = db.scalars(select(GlobalRoleAssignment).where(GlobalRoleAssignment.id == grant_id)
            .with_for_update().execution_options(populate_existing=True)).first()
        if row is None:
            raise HTTPException(404, 'global_role_not_found')
        target = recipient(db, row.principal_id)
        payload = {'grant_id': str(row.id), 'principal_id': str(row.principal_id), 'role': row.role,
            'expected_status': body.expected_status, 'status': body.status, 'reason': body.reason}
        repeated = replay(db, body, administrator, row.id, 'GLOBAL_ROLE_STATUS_CHANGED', payload)
        if not repeated:
            if row.status != body.expected_status:
                raise HTTPException(409, 'global_role_status_conflict')
            if body.status == 'ACTIVE':
                eligible(target)
            elif row.role == 'PLATFORM_ADMIN':
                # Count only grants that can authenticate in this configured issuer.
                # All API admin writers hold the transaction gate from active_admin.
                remaining = db.scalar(select(func.count()).select_from(GlobalRoleAssignment)
                    .join(SecurityPrincipal, SecurityPrincipal.id == GlobalRoleAssignment.principal_id)
                    .where(GlobalRoleAssignment.id != row.id, GlobalRoleAssignment.role == 'PLATFORM_ADMIN',
                           GlobalRoleAssignment.status == 'ACTIVE', SecurityPrincipal.status == 'ACTIVE',
                           SecurityPrincipal.issuer == settings.oidc_issuer_url))
                if not remaining:
                    raise HTTPException(409, 'last_active_admin_protected')
            row.status = body.status
            db.flush()
            AuditEventService(db).record(event_no=body.event_no, event_type='GLOBAL_ROLE_STATUS_CHANGED',
                action='SUSPEND' if body.status == 'SUSPENDED' else 'RESUME', entity_type='GLOBAL_ROLE',
                entity_id=row.id, entity_ref=str(row.id), summary=f'Global role {body.status.lower()}',
                payload=payload, **resolve_actor(request).audit_fields())
        response = receipt(row, body, body.status, repeated)
        db.commit()
        return response
    except (IntegrityError, AuditEventError):
        db.rollback()
        raise HTTPException(409, 'audit_event_conflict')
    except Exception:
        db.rollback()
        raise
