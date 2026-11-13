"""One atomic empty application DRAFT. No copied artifacts, snapshot or approval."""
import hashlib
import json
import uuid
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, or_, and_
from sqlalchemy.exc import IntegrityError

from app.auth import AuthenticatedPrincipal
from app.api.browser_sessions import require_browser_session
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.core import (Release, StandardReleaseDetail, ApplicationReleaseDetail,
                             Project, Customer, SoftwareProduct)
from app.models.security import SecurityPrincipal, BrowserSession, ProjectMembership, SoftwareMembership
from app.models.revocation import ReleaseChainRevocation
from app.services.admin_lock import admin_write_gate
from app.services.audit import commit_with_audit


class CreateApplicationRelease(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    project_id: uuid.UUID
    standard_base_release_id: uuid.UUID
    version: str = Field(strict=True, min_length=1, max_length=100)
    release_notes: str | None = Field(default=None, strict=True, max_length=4000)
    reason: str = Field(strict=True, min_length=1, max_length=4000)
    expected_context_digest: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')

    @field_validator('request_id', 'project_id', 'standard_base_release_id', mode='before')
    @classmethod
    def canonical_uuid(cls, value):
        if not isinstance(value, uuid.UUID):
            if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                raise ValueError('canonical lowercase UUID required')
        if uuid.UUID(str(value)).int == 0:
            raise ValueError('nonzero UUID required')
        return value

    @field_validator('version', 'reason')
    @classmethod
    def canonical_text(cls, value):
        if value != value.strip() or not value:
            raise ValueError('canonical nonempty text required')
        return value

    @field_validator('version', 'reason', 'release_notes')
    @classmethod
    def valid_unicode(cls, value, info):
        if value is not None:
            allowed = '' if info.field_name == 'version' else '\n\t'
            if any(unicodedata.category(char) == 'Cs' or
                   (unicodedata.category(char) == 'Cc' and char not in allowed) for char in value):
                raise ValueError('unsupported control character or Unicode surrogate')
        return value


def fail(code, status=409):
    raise HTTPException(status, code)


def digest(context):
    return hashlib.sha256(json.dumps({'version': 1, 'context': context}, ensure_ascii=False,
                                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()


CONTEXT_FIELDS = {'project_id', 'project_code', 'project_name', 'customer_id', 'customer_code',
                  'customer_name', 'software_id', 'software_code', 'software_name',
                  'standard_base_release_id', 'standard_base_version', 'standard_base_status'}


class ApplicationReleaseCreationService:
    def __init__(self, db):
        self.db = db

    def _locked(self, model, key, field=None):
        return self.db.scalar(select(model).where((field if field is not None else model.id) == key)
            .with_for_update().execution_options(populate_existing=True))

    def _actor(self, request, write):
        if write and settings.read_only_mode:
            fail('read_only_mode', 403)
        if settings.auth_mode != 'oidc':
            fail('oidc_not_enabled', 401)
        principal = getattr(request.state, 'principal', None)
        if not isinstance(principal, AuthenticatedPrincipal):
            fail('authenticated_principal_required', 401)
        # Same first lock as every administrator writer. No grant can change underneath
        # the domain transaction. Browser revocation locks this principal first too.
        admin_write_gate(self.db)
        actor = self._locked(SecurityPrincipal, principal.id)
        if (actor is None or actor.status != 'ACTIVE' or actor.issuer != principal.issuer or
                actor.subject != principal.subject or actor.issuer != settings.oidc_issuer_url):
            fail('inactive_principal', 401)
        if actor.principal_type != 'USER':
            fail('user_principal_required', 403)
        sid = require_browser_session(request, self.db, actor.id)
        if sid is not None:
            self._locked(BrowserSession, sid)
            require_browser_session(request, self.db, actor.id)
        return actor

    def _scope(self, actor, project_id, software_id):
        project = self.db.scalar(select(ProjectMembership).where(
            ProjectMembership.principal_id == actor.id, ProjectMembership.project_id == project_id,
            ProjectMembership.role == 'CONTRIBUTOR').with_for_update().execution_options(populate_existing=True))
        software = list(self.db.scalars(select(SoftwareMembership).where(
            SoftwareMembership.principal_id == actor.id, SoftwareMembership.software_id == software_id,
            SoftwareMembership.role.in_(('SOFTWARE_VIEWER', 'SOFTWARE_MAINTAINER')))
            .order_by(SoftwareMembership.id).with_for_update().execution_options(populate_existing=True)))
        if project is None or project.status != 'ACTIVE':
            fail('project_contributor_required', 403)
        if not any(row.status == 'ACTIVE' for row in software):
            fail('software_visibility_required', 403)

    def _parents(self, project_id, standard_id, actor, *, fresh):
        # Resolve the candidate without trusting cached ORM state, authorize that exact
        # software, then lock/re-read it. Existing chain writers take Release first.
        software_id = self.db.scalar(select(Release.software_id).where(Release.id == standard_id))
        if software_id is None:
            fail('standard_release_not_found', 404)
        self._scope(actor, project_id, software_id)
        standard = self._locked(Release, standard_id)
        if standard is None or standard.software_id != software_id:
            fail('asr_parent_binding_conflict')
        project = self._locked(Project, project_id)
        if project is None:
            fail('project_not_found', 404)
        customer = self._locked(Customer, project.customer_id)
        software = self._locked(SoftwareProduct, software_id)
        detail = self._locked(StandardReleaseDetail, standard_id, StandardReleaseDetail.release_id)
        if standard.release_type != 'STANDARD' or detail is None or customer is None or software is None:
            fail('asr_parent_binding_conflict')
        if fresh:
            if any(row.status != 'ACTIVE' for row in (project, customer, software)):
                fail('asr_parent_inactive')
            if standard.status == 'REVOKED' or self.db.scalar(select(ReleaseChainRevocation.id).where(
                    ReleaseChainRevocation.release_id == standard.id)) is not None:
                fail('standard_release_revoked')
        return {'project_id': str(project.id), 'project_code': project.project_code, 'project_name': project.name,
                'customer_id': str(customer.id), 'customer_code': customer.code, 'customer_name': customer.name,
                'software_id': str(software.id), 'software_code': software.code, 'software_name': software.name,
                'standard_base_release_id': str(standard.id), 'standard_base_version': standard.version,
                'standard_base_status': standard.status}

    def context(self, project_id, standard_base_release_id, request):
        try:
            actor = self._actor(request, False)
            ctx = self._parents(project_id, standard_base_release_id, actor, fresh=True)
            return {'version': 1, 'context': ctx, 'context_digest': digest(ctx)}
        finally:
            self.db.rollback()

    def _result(self, command, ctx, actor_id, created_at):
        return {**{k: command[k] for k in ('request_id', 'project_id', 'standard_base_release_id',
                    'version', 'release_notes', 'reason', 'expected_context_digest')},
                **{k: ctx[k] for k in ('customer_id', 'software_id', 'standard_base_version', 'standard_base_status')},
                'release_id': command['request_id'], 'release_type': 'APPLICATION', 'applied_status': 'DRAFT',
                'audit_event_no': 'EVT-ASR-'+uuid.UUID(command['request_id']).hex,
                'actor_principal_id': str(actor_id), 'created_at': created_at}

    def _evidence(self, event, request_id, actor, command=None):
        """Validate the complete immutable envelope, never synthesize an old success."""
        try:
            payload = event.payload_json
            if (event.event_no != 'EVT-ASR-'+request_id.hex or event.event_type != 'APPLICATION_RELEASE_CREATED' or
                    event.action != 'CREATED' or event.entity_type != 'RELEASE' or event.entity_id != request_id or
                    event.entity_ref != str(request_id) or event.actor_principal_id != actor.id or
                    event.declared_actor_name is not None or not isinstance(payload, dict) or
                    set(payload) != {'version', 'request', 'context', 'receipt', 'actor_source'} or
                    type(payload['version']) is not int or payload['version'] != 1 or
                    payload['actor_source'] != 'AUTHENTICATED_PRINCIPAL'):
                fail('asr_request_conflict')
            original = CreateApplicationRelease.model_validate(payload['request']).model_dump(mode='json')
            ctx, result = payload['context'], payload['receipt']
            if (original != payload['request'] or original['request_id'] != str(request_id) or
                    (command is not None and original != command) or not isinstance(ctx, dict) or
                    set(ctx) != CONTEXT_FIELDS or not all(isinstance(v, str) for v in ctx.values()) or
                    digest(ctx) != original['expected_context_digest'] or event.detail != original['reason']):
                fail('asr_request_conflict')
            for key in ('project_id','customer_id','software_id','standard_base_release_id'):
                if str(uuid.UUID(ctx[key])) != ctx[key]: fail('asr_request_conflict')
            if any(ctx[k] != original[k] for k in ('project_id','standard_base_release_id')):
                fail('asr_request_conflict')
            occurred = event.occurred_at.replace(tzinfo=event.occurred_at.tzinfo or timezone.utc)
            stamped = datetime.fromisoformat(result['created_at'])
            if stamped.tzinfo is None or stamped != occurred or result != self._result(original, ctx, actor.id, result['created_at']):
                fail('asr_request_conflict')
            # Scope comes exclusively from validated original evidence, never a supplied
            # customer/software or a newly selected client context.
            current = self._parents(uuid.UUID(ctx['project_id']), uuid.UUID(ctx['standard_base_release_id']), actor, fresh=False)
            if any(current[k] != ctx[k] for k in ('project_id','customer_id','software_id','standard_base_release_id')):
                fail('asr_parent_binding_conflict')
            row = self.db.get(Release, request_id, populate_existing=True)
            detail = self.db.get(ApplicationReleaseDetail, request_id, populate_existing=True)
            if (row is None or detail is None or row.release_type != 'APPLICATION' or
                    str(row.customer_scope_id) != ctx['customer_id'] or str(row.software_id) != ctx['software_id'] or
                    row.version != original['version'] or row.release_notes != original['release_notes'] or
                    str(detail.customer_id) != ctx['customer_id'] or str(detail.project_id) != ctx['project_id'] or
                    str(detail.standard_base_release_id) != ctx['standard_base_release_id'] or
                    detail.previous_application_release_id is not None):
                fail('asr_request_conflict')
            return dict(result)
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            fail('asr_request_conflict')

    def receipt(self, request_id, request):
        try:
            actor = self._actor(request, False)
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-ASR-'+request_id.hex))
            if event is None:
                if self.db.get(Release, request_id) is not None: fail('asr_request_conflict')
                fail('asr_receipt_not_found', 404)
            return self._evidence(event, request_id, actor)
        finally:
            self.db.rollback()

    def create(self, *, request, **values):
        try:
            try: body = CreateApplicationRelease(**values)
            except ValidationError: fail('invalid_asr_request', 422)
            command = body.model_dump(mode='json')
            actor = self._actor(request, True)
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-ASR-'+body.request_id.hex))
            if event is not None:
                result = self._evidence(event, body.request_id, actor, command)
                self.db.rollback()
                return result, False
            if self.db.get(Release, body.request_id) is not None:
                fail('asr_request_conflict')
            ctx = self._parents(body.project_id, body.standard_base_release_id, actor, fresh=True)
            if digest(ctx) != body.expected_context_digest:
                fail('asr_context_conflict')
            customer_id, software_id = uuid.UUID(ctx['customer_id']), uuid.UUID(ctx['software_id'])
            # Includes legacy NULL-scope rows; do not backfill or normalize them.
            duplicate = self.db.scalar(select(Release.id).outerjoin(ApplicationReleaseDetail,
                ApplicationReleaseDetail.release_id == Release.id).where(Release.software_id == software_id,
                Release.release_type == 'APPLICATION', Release.version == body.version,
                or_(Release.customer_scope_id == customer_id,
                    and_(Release.customer_scope_id.is_(None), ApplicationReleaseDetail.customer_id == customer_id))).limit(1))
            if duplicate is not None: fail('asr_version_conflict')
            now = datetime.now(timezone.utc)
            row = Release(id=body.request_id, software_id=software_id, customer_scope_id=customer_id,
                release_type='APPLICATION', version=body.version, status='DRAFT',
                release_notes=body.release_notes, created_at=now)
            self.db.add(row); self.db.flush()
            self.db.add(ApplicationReleaseDetail(release_id=row.id, customer_id=customer_id,
                project_id=body.project_id, standard_base_release_id=body.standard_base_release_id))
            result = self._result(command, ctx, actor.id, now.isoformat())
            commit_with_audit(self.db, lambda: dict(event_no=result['audit_event_no'],
                event_type='APPLICATION_RELEASE_CREATED', action='CREATED', entity_type='RELEASE',
                entity_id=row.id, entity_ref=str(row.id), actor_name=actor.display_name[:120],
                actor_principal_id=actor.id, actor_display_name=actor.display_name, declared_actor_name=None,
                summary='Empty application release draft created', detail=body.reason, occurred_at=now,
                payload={'version':1, 'request':command, 'context':ctx, 'receipt':result,
                         'actor_source':'AUTHENTICATED_PRINCIPAL'}))
            return result, True
        except IntegrityError:
            self.db.rollback()
            fail('asr_request_or_version_conflict')
        except Exception:
            self.db.rollback()
            raise
