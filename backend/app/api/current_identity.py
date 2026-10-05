"""Private, authenticated self context for a future provider-backed browser session."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.core.db import get_db
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership

router = APIRouter(prefix='/api/v1/security/me', tags=['current identity'])


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


class GrantPage(Empty):
    scope: Literal['GLOBAL', 'SOFTWARE', 'PROJECT']
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def current_principal(request: Request, db: Session):
    principal = getattr(request.state, 'principal', None)
    if not isinstance(principal, AuthenticatedPrincipal):
        raise HTTPException(401, 'authenticated_principal_required', headers={'WWW-Authenticate': 'Bearer'})
    # Recheck in the read transaction: middleware authentication is not a cached grant.
    row = db.execute(select(SecurityPrincipal.id, SecurityPrincipal.principal_type, SecurityPrincipal.display_name)
        .where(SecurityPrincipal.id == principal.id, SecurityPrincipal.issuer == principal.issuer,
               SecurityPrincipal.subject == principal.subject, SecurityPrincipal.status == 'ACTIVE')).mappings().first()
    if row is None:
        raise HTTPException(401, 'inactive_principal', headers={'WWW-Authenticate': 'Bearer'})
    return dict(row)


def grants(principal_id: uuid.UUID, scope: str):
    model = {'GLOBAL': GlobalRoleAssignment, 'PROJECT': ProjectMembership, 'SOFTWARE': SoftwareMembership}[scope]
    fields = [model.id, model.role, model.created_at]
    if scope == 'PROJECT':
        fields.append(model.project_id.label('scope_id'))
    elif scope == 'SOFTWARE':
        fields.append(model.software_id.label('scope_id'))
    stmt = select(*fields).where(model.principal_id == principal_id)
    if scope != 'GLOBAL':
        stmt = stmt.where(model.status == 'ACTIVE')
    return stmt


def total(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


@router.get('')
def identity_summary(request: Request, filters: Annotated[Empty, Query()], db: Session = Depends(get_db)):
    principal = current_principal(request, db)
    return {'principal': principal, 'read_only_mode': settings.read_only_mode,
            'active_grant_counts': {scope: total(db, grants(principal['id'], scope)) for scope in ('GLOBAL', 'PROJECT', 'SOFTWARE')}}


@router.get('/grants')
def identity_grants(request: Request, filters: Annotated[GrantPage, Query()], db: Session = Depends(get_db)):
    principal = current_principal(request, db)
    stmt = grants(principal['id'], filters.scope)
    count = total(db, stmt)
    items = [dict(row) for row in db.execute(stmt.order_by(stmt.selected_columns.id).limit(filters.limit).offset(filters.offset)).mappings()]
    for item in items:
        item.setdefault('scope_id', None)
    return {'principal_id': principal['id'], 'scope': filters.scope, 'total': count,
            'limit': filters.limit, 'offset': filters.offset,
            'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < count else None,
            'items': items}
