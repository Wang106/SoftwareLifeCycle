"""Audited, suspended-first exact project/software role registration."""
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actor import resolve_actor
from app.api.membership_admin import active_admin, Scope
from app.api.principal_admin import AuditedRequest
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.core import Project, SoftwareProduct
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.security_roles import PROJECT_ROLES, SOFTWARE_ROLES
from app.services.audit import AuditEventError, AuditEventService

router = APIRouter(prefix='/api/v1/security/admin/memberships', tags=['membership administration'])
Role = Literal['PROJECT_VIEWER', 'CONTRIBUTOR', 'REVIEWER', 'RELEASE_AUTHORITY',
    'DISTRIBUTION_AUTHORITY', 'PRODUCTION_AUTHORITY', 'PRODUCTION_OPERATOR',
    'SOFTWARE_VIEWER', 'SOFTWARE_MAINTAINER']


class RegisterMembership(AuditedRequest):
    membership_id: uuid.UUID
    principal_id: uuid.UUID
    scope_id: uuid.UUID
    role: Role


def admin_recipient(db, identifier):
    return db.scalar(select(GlobalRoleAssignment.id).where(
        GlobalRoleAssignment.principal_id == identifier,
        GlobalRoleAssignment.role == 'PLATFORM_ADMIN')) is not None


def result(row, scope, body, replayed):
    return {'membership_id': row.id, 'scope': scope, 'principal_id': row.principal_id,
        'scope_id': body.scope_id, 'role': row.role, 'applied_status': 'SUSPENDED',
        'current_status': row.status, 'replayed': replayed, 'audit_event_no': body.event_no}


@router.post('/{scope}')
def register_membership(scope: Scope, body: RegisterMembership, request: Request,
                        db: Session = Depends(get_db)):
    try:
        administrator = active_admin(request, db)
        if body.role not in (PROJECT_ROLES if scope == 'PROJECT' else SOFTWARE_ROLES):
            raise HTTPException(422, 'role_scope_mismatch')
        # Actor->recipient lock order is shared with principal status controls.
        # Admin recipients could create actor/recipient cycles and are deferred to
        # the global-admin lifecycle policy, including self-scoped assignments.
        if admin_recipient(db, body.principal_id):
            raise HTTPException(409, 'admin_recipient_protected')
        recipient = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == body.principal_id)
            .with_for_update().execution_options(populate_existing=True)).first()
        if recipient is None:
            raise HTTPException(404, 'principal_not_found')
        if admin_recipient(db, recipient.id):
            raise HTTPException(409, 'admin_recipient_protected')
        model = ProjectMembership if scope == 'PROJECT' else SoftwareMembership
        scope_column = model.project_id if scope == 'PROJECT' else model.software_id
        payload = {'scope': scope, 'membership_id': str(body.membership_id),
            'principal_id': str(body.principal_id), 'scope_id': str(body.scope_id),
            'role': body.role, 'status': 'SUSPENDED', 'reason': body.reason}
        existing = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
        if existing is not None:
            if (existing.event_type != 'MEMBERSHIP_REGISTERED' or existing.entity_type != scope+'_MEMBERSHIP'
                or existing.entity_id != body.membership_id or existing.entity_ref != str(body.membership_id)
                or existing.actor_principal_id != administrator.id or existing.payload_json != payload):
                raise HTTPException(409, 'audit_event_conflict')
            row = db.scalars(select(model).where(model.id == body.membership_id,
                model.principal_id == body.principal_id, scope_column == body.scope_id,
                model.role == body.role).execution_options(populate_existing=True)).first()
            if row is None:
                raise HTTPException(409, 'membership_registration_conflict')
            response = result(row, scope, body, True)
            db.commit()
            return response
        if recipient.status != 'ACTIVE':
            raise HTTPException(409, 'recipient_inactive')
        if recipient.issuer != settings.oidc_issuer_url:
            raise HTTPException(409, 'recipient_issuer_mismatch')
        target = Project if scope == 'PROJECT' else SoftwareProduct
        if db.scalar(select(target.id).where(target.id == body.scope_id)) is None:
            raise HTTPException(404, 'scope_target_not_found')
        if db.scalar(select(model.id).where((model.id == body.membership_id) |
                ((model.principal_id == body.principal_id) & (scope_column == body.scope_id) &
                 (model.role == body.role)))) is not None:
            raise HTTPException(409, 'membership_registration_conflict')
        row = model(id=body.membership_id, principal_id=body.principal_id, role=body.role,
            status='SUSPENDED', **({'project_id': body.scope_id} if scope == 'PROJECT' else {'software_id': body.scope_id}))
        db.add(row)
        db.flush()
        AuditEventService(db).record(event_no=body.event_no, event_type='MEMBERSHIP_REGISTERED',
            action='REGISTER', entity_type=scope+'_MEMBERSHIP', entity_id=row.id, entity_ref=str(row.id),
            summary=f'{scope.title()} membership registered suspended', payload=payload,
            **resolve_actor(request).audit_fields())
        response = result(row, scope, body, False)
        db.commit()
        return response
    except (IntegrityError, AuditEventError):
        db.rollback()
        raise HTTPException(409, 'membership_registration_conflict')
    except Exception:
        db.rollback()
        raise
