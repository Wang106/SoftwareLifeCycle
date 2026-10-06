"""Offline privileged operator protocol; no HTTP route or startup invocation."""
from datetime import datetime, timezone
import hashlib
import json
import os
import socket
from typing import Literal
import uuid

from pydantic import Field, field_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.principal_admin import AuditedRequest
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, SecurityPrincipal
from app.services.admin_lock import admin_write_gate
from app.services.audit import AuditEventError, AuditEventService


class OperatorError(ValueError):
    pass


class OperatorRequest(AuditedRequest):
    target_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    approval_ref: str = Field(min_length=5, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]*$')
    acknowledge_privileged_change: Literal[True]
    expected_effective_admin_count: Literal[0]
    principal_id: uuid.UUID
    grant_id: uuid.UUID

    @field_validator('acknowledge_privileged_change', mode='before')
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError('Explicit boolean confirmation required')
        return value

    @field_validator('expected_effective_admin_count', mode='before')
    @classmethod
    def exact_zero(cls, value):
        if type(value) is not int or value != 0:
            raise ValueError('Exact zero administrator expectation required')
        return value


class BootstrapAdmin(OperatorRequest):
    subject: str = Field(min_length=1, max_length=500)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator('subject', 'display_name')
    @classmethod
    def exact_printable(cls, value):
        if value != value.strip() or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Bounded printable exact identity values required')
        return value


class RecoverAdmin(OperatorRequest):
    expected_principal_status: Literal['ACTIVE', 'DISABLED']
    expected_grant_status: Literal['ACTIVE', 'SUSPENDED']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def preconditions():
    # Fail before opening a database connection in the CLI.
    if not settings.admin_operator_enabled:
        raise OperatorError('operator_disabled')
    if settings.read_only_mode:
        raise OperatorError('read_only_mode')
    if settings.auth_mode != 'oidc' or not settings.oidc_issuer_url or not settings.oidc_audience or not settings.oidc_jwks_url:
        raise OperatorError('configured_oidc_required')


def database_context(db):
    url = db.get_bind().url
    try:
        revisions = list(db.scalars(text('SELECT version_num FROM alembic_version')))
        if revisions != [settings.required_db_revision]:
            raise OperatorError('operator_schema_not_ready')
        if db.get_bind().dialect.name == 'postgresql':
            database, schema, role = db.execute(text('SELECT current_database(), current_schema(), current_user')).one()
            coherent = db.scalar(text("""SELECT count(*) FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relkind IN ('r','p')
                AND c.oid = ANY(ARRAY[to_regclass('alembic_version'),to_regclass('security_principals'),
                    to_regclass('global_role_assignments'),to_regclass('browser_sessions'),to_regclass('audit_events')])"""))
            if coherent != 5:
                raise OperatorError('operator_schema_not_ready')
        else:
            # Sequential service tests only. The executable CLI requires PostgreSQL.
            database, schema, role = url.database, 'main', 'sqlite-test'
    except SQLAlchemyError:
        raise OperatorError('operator_schema_not_ready') from None
    target = digest({'host': url.host, 'port': url.port, 'database': database, 'schema': schema,
                     'database_role': role, 'driver': url.drivername, 'issuer': settings.oidc_issuer_url,
                     'audience': settings.oidc_audience, 'jwks': settings.oidc_jwks_url,
                     'algorithms': settings.oidc_algorithms})
    # Infrastructure process identity, deliberately NOT a verified human/OIDC actor.
    context = digest({'uid': os.geteuid(), 'host': socket.gethostname(), 'database_role': role})
    return target, context


def effective_admins(db):
    return db.scalar(select(func.count()).select_from(GlobalRoleAssignment)
        .join(SecurityPrincipal, SecurityPrincipal.id == GlobalRoleAssignment.principal_id)
        .where(GlobalRoleAssignment.role == 'PLATFORM_ADMIN', GlobalRoleAssignment.status == 'ACTIVE',
               SecurityPrincipal.status == 'ACTIVE', SecurityPrincipal.issuer == settings.oidc_issuer_url))


def plan(db):
    preconditions()
    target, _ = database_context(db)
    effective = effective_admins(db)
    historical = db.scalar(select(func.count()).select_from(GlobalRoleAssignment)
                          .where(GlobalRoleAssignment.role == 'PLATFORM_ADMIN'))
    return {'target_fingerprint': target, 'schema_revision': settings.required_db_revision,
            'issuer_fingerprint': digest(settings.oidc_issuer_url), 'effective_admin_count': effective,
            'admin_assignment_count': historical, 'bootstrap_available': historical == 0,
            'recovery_available': effective == 0 and historical > 0,
            'authorization_source': 'LOCAL_OPERATOR_PROCESS_NOT_OIDC_HUMAN'}


def receipt(principal, grant, body, repeated, revoked):
    return {'principal_id': principal.id, 'grant_id': grant.id, 'role': 'PLATFORM_ADMIN',
            'applied_principal_status': 'ACTIVE', 'applied_grant_status': 'ACTIVE',
            'current_principal_status': principal.status, 'current_grant_status': grant.status,
            'replayed': repeated, 'revoked_browser_sessions': revoked, 'audit_event_no': body.event_no}


def apply(db, body: BootstrapAdmin | RecoverAdmin):
    try:
        preconditions()
        admin_write_gate(db)
        target, operator = database_context(db)
        if target != body.target_fingerprint:
            raise OperatorError('operator_target_mismatch')
        operation = 'BOOTSTRAP' if isinstance(body, BootstrapAdmin) else 'RECOVER'
        binding = {'operation': operation, 'issuer': settings.oidc_issuer_url, **body.model_dump(mode='json')}
        request_digest = digest(binding)
        event = db.scalars(select(AuditEvent).where(AuditEvent.event_no == body.event_no)).first()
        if event is not None:
            payload = event.payload_json
            if (event.event_type != 'ADMIN_OPERATOR_'+operation or event.entity_type != 'GLOBAL_ROLE'
                or event.entity_id != body.grant_id or event.entity_ref != str(body.grant_id)
                or event.actor_principal_id is not None or event.actor_name != 'LocalOperator/'+operator[:20]
                or payload.get('request_digest') != request_digest or payload.get('operator_context') != operator):
                raise OperatorError('operator_replay_conflict')
            principal = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == body.principal_id,
                SecurityPrincipal.issuer == settings.oidc_issuer_url).with_for_update()
                .execution_options(populate_existing=True)).first()
            grant = db.scalars(select(GlobalRoleAssignment).where(GlobalRoleAssignment.id == body.grant_id,
                GlobalRoleAssignment.principal_id == body.principal_id, GlobalRoleAssignment.role == 'PLATFORM_ADMIN')
                .with_for_update().execution_options(populate_existing=True)).first()
            if principal is None or grant is None:
                raise OperatorError('operator_replay_state_missing')
            response = receipt(principal, grant, body, True, payload['revoked_browser_sessions'])
            db.commit()
            return response
        if effective_admins(db) != 0:
            raise OperatorError('effective_admin_exists')
        revoked = 0
        if operation == 'BOOTSTRAP':
            if db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.role == 'PLATFORM_ADMIN').limit(1)):
                raise OperatorError('historical_admin_requires_recovery')
            if db.scalar(select(SecurityPrincipal.id).where((SecurityPrincipal.id == body.principal_id) |
                ((SecurityPrincipal.issuer == settings.oidc_issuer_url) & (SecurityPrincipal.subject == body.subject)))):
                raise OperatorError('operator_principal_conflict')
            if db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.id == body.grant_id)):
                raise OperatorError('operator_grant_conflict')
            principal = SecurityPrincipal(id=body.principal_id, issuer=settings.oidc_issuer_url,
                subject=body.subject, principal_type='USER', display_name=body.display_name, status='ACTIVE')
            db.add(principal); db.flush()
            grant = GlobalRoleAssignment(id=body.grant_id, principal_id=principal.id, role='PLATFORM_ADMIN', status='ACTIVE')
            db.add(grant)
        else:
            principal = db.scalars(select(SecurityPrincipal).where(SecurityPrincipal.id == body.principal_id)
                .with_for_update().execution_options(populate_existing=True)).first()
            if principal is None:
                raise OperatorError('operator_principal_not_found')
            if principal.issuer != settings.oidc_issuer_url or principal.principal_type != 'USER':
                raise OperatorError('operator_recipient_ineligible')
            grant = db.scalars(select(GlobalRoleAssignment).where(GlobalRoleAssignment.id == body.grant_id,
                GlobalRoleAssignment.principal_id == principal.id, GlobalRoleAssignment.role == 'PLATFORM_ADMIN')
                .with_for_update().execution_options(populate_existing=True)).first()
            if grant is None:
                raise OperatorError('operator_existing_admin_grant_required')
            if principal.status != body.expected_principal_status or grant.status != body.expected_grant_status:
                raise OperatorError('operator_status_conflict')
            principal.status = 'ACTIVE'; grant.status = 'ACTIVE'
            revoked = db.execute(update(BrowserSession).where(BrowserSession.principal_id == principal.id,
                BrowserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc))).rowcount
        db.flush()
        payload = {'principal_id': str(principal.id), 'grant_id': str(grant.id), 'operation': operation,
            'applied_principal_status': 'ACTIVE', 'applied_grant_status': 'ACTIVE',
            'request_digest': request_digest, 'operator_context': operator,
            'authorization_source': 'LOCAL_OPERATOR_PROCESS_NOT_OIDC_HUMAN',
            'approval_ref': body.approval_ref, 'reason': body.reason, 'revoked_browser_sessions': revoked}
        if operation == 'RECOVER':
            payload.update(expected_principal_status=body.expected_principal_status,
                           expected_grant_status=body.expected_grant_status)
        AuditEventService(db).record(event_no=body.event_no, event_type='ADMIN_OPERATOR_'+operation,
            action=operation, entity_type='GLOBAL_ROLE', entity_id=grant.id, entity_ref=str(grant.id),
            actor_name='LocalOperator/'+operator[:20], actor_principal_id=None,
            summary='Offline local administrator '+operation.lower(), payload=payload)
        response = receipt(principal, grant, body, False, revoked)
        db.commit()
        return response
    except (IntegrityError, AuditEventError):
        db.rollback()
        raise OperatorError('operator_write_conflict') from None
    except Exception:
        db.rollback()
        raise
