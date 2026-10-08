"""Private bounded principal projections; no credentials or provider identifiers."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.admin_grants import Empty, Page, page_result, require_admin_read
from app.core.config import settings
from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, SecurityPrincipal

router = APIRouter(prefix='/api/v1/security/admin/principals', tags=['administrator principal reads'])


class PrincipalFilters(Page):
    principal_id: uuid.UUID | None = None
    principal_type: Literal['USER', 'SERVICE'] | None = None
    status: Literal['ACTIVE', 'DISABLED'] | None = None


def principal_projection():
    # Historical/suspended administrator grants are protected by the status command.
    protected = select(GlobalRoleAssignment.id).where(
        GlobalRoleAssignment.principal_id == SecurityPrincipal.id,
        GlobalRoleAssignment.role == 'PLATFORM_ADMIN').exists()
    return select(SecurityPrincipal.id, SecurityPrincipal.principal_type,
        SecurityPrincipal.display_name, SecurityPrincipal.status, SecurityPrincipal.created_at,
        (SecurityPrincipal.issuer == settings.oidc_issuer_url).label('issuer_matches_configuration'),
        protected.label('admin_principal_protected'))


def principal_item(row):
    return {**dict(row), 'status_history_supported': True}


def exact_principal(db, principal_id):
    row = db.execute(principal_projection().where(SecurityPrincipal.id == principal_id)).mappings().first()
    if row is None:
        raise HTTPException(404, 'principal_not_found')
    return row


@router.get('')
def principal_catalog(request: Request, filters: Annotated[PrincipalFilters, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    stmt = principal_projection()
    if filters.principal_id is not None:
        stmt = stmt.where(SecurityPrincipal.id == filters.principal_id)
    if filters.principal_type is not None:
        stmt = stmt.where(SecurityPrincipal.principal_type == filters.principal_type)
    if filters.status is not None:
        stmt = stmt.where(SecurityPrincipal.status == filters.status)
    result = page_result(db, stmt, [SecurityPrincipal.id], filters)
    result['items'] = [principal_item(row) for row in result['items']]
    return result


@router.get('/{principal_id}')
def principal_detail(principal_id: uuid.UUID, request: Request,
                     filters: Annotated[Empty, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    return principal_item(exact_principal(db, principal_id))


def history_projection(principal_id):
    before = AuditEvent.payload_json['expected_status'].as_string()
    after = AuditEvent.payload_json['status'].as_string()
    reason = AuditEvent.payload_json['reason'].as_string()
    return select(AuditEvent.id, AuditEvent.event_no, AuditEvent.action, AuditEvent.occurred_at,
        AuditEvent.actor_principal_id, AuditEvent.actor_display_name,
        case((before.in_(['ACTIVE','DISABLED']), before), else_=None).label('expected_status'),
        case((after.in_(['ACTIVE','DISABLED']), after), else_=None).label('status'),
        func.substr(reason,1,500).label('reason'),
        case((func.length(reason)>500,True),else_=False).label('reason_truncated'))\
        .where(AuditEvent.entity_type == 'SECURITY_PRINCIPAL', AuditEvent.entity_id == principal_id,
               AuditEvent.entity_ref == str(principal_id), AuditEvent.event_type == 'PRINCIPAL_STATUS_CHANGED')


@router.get('/{principal_id}/history')
def principal_history(principal_id: uuid.UUID, request: Request,
                      filters: Annotated[Page, Query()], db: Session = Depends(get_db)):
    require_admin_read(request, db)
    current = exact_principal(db, principal_id)
    result = page_result(db, history_projection(principal_id), [AuditEvent.occurred_at.desc(),AuditEvent.id.desc()], filters)
    result.update({'principal_id':principal_id,'current_status':current['status'],
                   'coverage':'PRINCIPAL_STATUS_CHANGED_ONLY'})
    return result
