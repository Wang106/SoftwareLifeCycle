"""Private administrator grant projections and exact membership status history."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedPrincipal
from app.api.browser_sessions import require_browser_session
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.core import Project, SoftwareProduct
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.security_roles import GLOBAL_ROLES, PROJECT_ROLES, SOFTWARE_ROLES

router = APIRouter(prefix='/api/v1/security/admin/grants', tags=['administrator grant reads'])
Scope = Literal['GLOBAL', 'PROJECT', 'SOFTWARE']
Status = Literal['ACTIVE', 'SUSPENDED']


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Page(Empty):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


class GrantFilters(Page):
    scope: Scope
    principal_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    role: str | None = Field(None, min_length=1, max_length=40)
    status: Status | None = None
    principal_status: Literal['ACTIVE', 'DISABLED'] | None = None

    @model_validator(mode='after')
    def exact_scope_filters(self):
        roles = {'GLOBAL': GLOBAL_ROLES, 'PROJECT': PROJECT_ROLES, 'SOFTWARE': SOFTWARE_ROLES}[self.scope]
        if self.role is not None and self.role not in roles:
            raise ValueError('Role must belong to the selected scope')
        if self.scope == 'GLOBAL' and self.scope_id is not None:
            raise ValueError('Global grants have no scope_id')
        return self


def require_admin_read(request: Request, db: Session):
    # Reads remain available to authenticated admins in read-only environments.
    if settings.auth_mode != 'oidc':
        raise HTTPException(401, 'oidc_not_enabled')
    principal = getattr(request.state, 'principal', None)
    if not isinstance(principal, AuthenticatedPrincipal):
        raise HTTPException(401, 'authenticated_principal_required')
    current = db.scalar(select(SecurityPrincipal.id).where(SecurityPrincipal.id == principal.id,
        SecurityPrincipal.issuer == principal.issuer, SecurityPrincipal.subject == principal.subject,
        SecurityPrincipal.status == 'ACTIVE'))
    if current is None:
        raise HTTPException(401, 'inactive_principal')
    if db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.principal_id == current,
        GlobalRoleAssignment.role == 'PLATFORM_ADMIN', GlobalRoleAssignment.status == 'ACTIVE')) is None:
        raise HTTPException(403, 'platform_admin_required')
    require_browser_session(request, db, current)


def grant_projection(scope):
    model = {'GLOBAL': GlobalRoleAssignment, 'PROJECT': ProjectMembership, 'SOFTWARE': SoftwareMembership}[scope]
    fields = [model.id, model.role, model.created_at, model.status,
        SecurityPrincipal.id.label('principal_id'), SecurityPrincipal.principal_type,
        SecurityPrincipal.display_name, SecurityPrincipal.status.label('principal_status')]
    if scope != 'GLOBAL':
        target = Project if scope == 'PROJECT' else SoftwareProduct
        target_id = model.project_id if scope == 'PROJECT' else model.software_id
        code = Project.project_code if scope == 'PROJECT' else SoftwareProduct.code
        fields += [target_id.label('scope_id'), code.label('scope_code'), target.name.label('scope_name')]
    stmt = select(*fields).select_from(model).join(SecurityPrincipal, SecurityPrincipal.id == model.principal_id)
    if scope != 'GLOBAL':
        stmt = stmt.join(target, target.id == target_id)
    return model, stmt


def grant_item(row, scope):
    row = dict(row)
    status = row.get('status')
    return {'id': row['id'], 'scope': scope, 'role': row['role'], 'status': status,
        'created_at': row['created_at'], 'effective': row['principal_status'] == 'ACTIVE' and status == 'ACTIVE',
        'principal': {'id': row['principal_id'], 'principal_type': row['principal_type'],
                      'display_name': row['display_name'], 'status': row['principal_status']},
        'target': None if scope == 'GLOBAL' else {'id': row['scope_id'], 'code': row['scope_code'], 'name': row['scope_name']},
        'status_history_supported': True}


def exact_grant(db, scope, grant_id):
    model, stmt = grant_projection(scope)
    row = db.execute(stmt.where(model.id == grant_id)).mappings().first()
    if row is None:
        raise HTTPException(404, 'grant_not_found')
    return row


def page_result(db, stmt, order, filters):
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = [dict(row) for row in db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).mappings()]
    return {'total': count, 'limit': filters.limit, 'offset': filters.offset,
            'next_offset': filters.offset+filters.limit if filters.offset+filters.limit < count else None,
            'items': items}


@router.get('')
def grant_catalog(request: Request, filters: Annotated[GrantFilters, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    model, stmt = grant_projection(filters.scope)
    if filters.principal_id is not None:
        stmt = stmt.where(model.principal_id == filters.principal_id)
    if filters.scope_id is not None:
        stmt = stmt.where((model.project_id if filters.scope == 'PROJECT' else model.software_id) == filters.scope_id)
    if filters.role is not None:
        stmt = stmt.where(model.role == filters.role)
    if filters.status is not None:
        stmt = stmt.where(model.status == filters.status)
    if filters.principal_status is not None:
        stmt = stmt.where(SecurityPrincipal.status == filters.principal_status)
    result = page_result(db, stmt, [model.id], filters)
    result['scope'] = filters.scope
    result['items'] = [grant_item(row, filters.scope) for row in result['items']]
    return result


@router.get('/{scope}/{grant_id}')
def grant_detail(scope: Scope, grant_id: uuid.UUID, request: Request,
                 filters: Annotated[Empty, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    return grant_item(exact_grant(db, scope, grant_id), scope)


def history_projection(scope, grant_id):
    statuses = ('ACTIVE', 'SUSPENDED')
    before = AuditEvent.payload_json['expected_status'].as_string()
    after = AuditEvent.payload_json['status'].as_string()
    reason = AuditEvent.payload_json['reason'].as_string()
    return select(AuditEvent.id, AuditEvent.event_no, AuditEvent.action, AuditEvent.occurred_at,
        AuditEvent.actor_principal_id, AuditEvent.actor_display_name,
        case((before.in_(statuses), before), else_=None).label('expected_status'),
        case((after.in_(statuses), after), else_=None).label('status'),
        func.substr(reason, 1, 500).label('reason'),
        case((func.length(reason) > 500, True), else_=False).label('reason_truncated'))\
        .where(AuditEvent.entity_id == grant_id, AuditEvent.entity_ref == str(grant_id),
               AuditEvent.entity_type == ('GLOBAL_ROLE' if scope == 'GLOBAL' else scope+'_MEMBERSHIP'),
               AuditEvent.event_type == ('GLOBAL_ROLE_STATUS_CHANGED' if scope == 'GLOBAL' else 'MEMBERSHIP_STATUS_CHANGED'))


@router.get('/{scope}/{grant_id}/history')
def grant_history(scope: Scope, grant_id: uuid.UUID, request: Request,
                  filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    current = exact_grant(db, scope, grant_id)
    result = page_result(db, history_projection(scope, grant_id), [AuditEvent.occurred_at.desc(), AuditEvent.id.desc()], filters)
    result.update({'scope': scope, 'grant_id': grant_id, 'current_status': current['status'],
                   'coverage': 'GLOBAL_ROLE_STATUS_CHANGED_ONLY' if scope == 'GLOBAL' else 'MEMBERSHIP_STATUS_CHANGED_ONLY'})
    return result
