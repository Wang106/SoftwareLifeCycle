"""Private, append-only declarations; never copy bytes or infer inheritance."""
import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models.core import Release, ApplicationReleaseDetail, ComponentDefinition, ReleaseComponent
from app.models.audit import AuditEvent
from app.models.revocation import ReleaseChainRevocation
from app.services.application_release_creation import (
    ApplicationReleaseCreationService, CreateApplicationRelease, CONTEXT_FIELDS as PARENT_FIELDS, digest, fail)
from app.services.audit import commit_with_audit

class DeclareApplicationComponent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    release_id: uuid.UUID
    component_definition_id: uuid.UUID
    base_component_id: uuid.UUID | None = None
    version: str = Field(strict=True, min_length=1, max_length=100)
    delta_type: Literal['ADDED', 'UNCHANGED', 'MODIFIED']
    reason: str = Field(strict=True, min_length=1, max_length=4000)
    expected_context_digest: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')

    @field_validator('request_id', 'release_id', 'component_definition_id', 'base_component_id', mode='before')
    @classmethod
    def canonical_uuid(cls, value, info):
        if value is None and info.field_name == 'base_component_id': return value
        return CreateApplicationRelease.canonical_uuid(value)

    @field_validator('version', 'reason')
    @classmethod
    def canonical_text(cls, value):
        return CreateApplicationRelease.canonical_text(value)

    @field_validator('version', 'reason')
    @classmethod
    def valid_unicode(cls, value, info):
        return CreateApplicationRelease.valid_unicode(value, info)

    @model_validator(mode='after')
    def declared_delta(self):
        if (self.base_component_id is None) != (self.delta_type == 'ADDED'):
            raise ValueError('ADDED requires no base; linked instances require UNCHANGED or MODIFIED')
        return self

CONTEXT_FIELDS = PARENT_FIELDS | {'release_id', 'release_version', 'release_status',
    'component_definition_id', 'component_code', 'component_name', 'base_component_id', 'base_component_version'}

class ApplicationComponentDeclarationService(ApplicationReleaseCreationService):
    def _actor(self, request, write):
        if write and settings.read_only_mode: fail('read_only_mode', 403)
        if not settings.application_component_declaration_enabled: fail('asrc_disabled', 403)
        return super()._actor(request, write)

    def _context(self, release_id, definition_id, base_id, actor, *, fresh):
        candidate = self.db.execute(select(ApplicationReleaseDetail.project_id,
            ApplicationReleaseDetail.standard_base_release_id).where(ApplicationReleaseDetail.release_id == release_id)).one_or_none()
        if candidate is None: fail('asrc_release_not_found', 404)
        project_id, standard_id = candidate
        if release_id == standard_id: fail('asrc_parent_binding_conflict')
        # Existing snapshot/revoke writers lock their owning Release, never an ASR's
        # baseline. Acquire the two Release rows in deterministic UUID order before
        # any detail/definition locks. PR227 only locks the baseline Release.
        for key in sorted((release_id, standard_id), key=str): self._locked(Release, key)
        ctx = self._parents(project_id, standard_id, actor, fresh=fresh)
        row = self._locked(Release, release_id)
        detail = self._locked(ApplicationReleaseDetail, release_id, ApplicationReleaseDetail.release_id)
        if (row is None or detail is None or row.release_type != 'APPLICATION' or
            detail.project_id != project_id or detail.standard_base_release_id != standard_id or
            str(detail.customer_id) != ctx['customer_id'] or str(row.customer_scope_id) != ctx['customer_id'] or
            str(row.software_id) != ctx['software_id']): fail('asrc_parent_binding_conflict')
        definition = self._locked(ComponentDefinition, definition_id)
        if definition is None: fail('asrc_definition_not_found', 404)
        base = self._locked(ReleaseComponent, base_id) if base_id else None
        if base_id and (base is None or base.release_id != standard_id or base.component_definition_id != definition_id):
            fail('asrc_base_component_conflict')
        if fresh:
            if row.status != 'DRAFT': fail('asrc_release_not_draft')
            if self.db.scalar(select(ReleaseChainRevocation.id).where(ReleaseChainRevocation.release_id == row.id)) is not None:
                fail('asrc_release_revoked')
            if not definition.is_active: fail('asrc_definition_inactive')
        return {**ctx, 'release_id':str(row.id), 'release_version':row.version, 'release_status':row.status,
            'component_definition_id':str(definition.id), 'component_code':definition.code, 'component_name':definition.name,
            'base_component_id':str(base.id) if base else None, 'base_component_version':base.version if base else None}

    def context(self, release_id, component_definition_id, base_component_id, request):
        try:
            actor = self._actor(request, False)
            ctx = self._context(release_id, component_definition_id, base_component_id, actor, fresh=True)
            return {'version':1, 'context':ctx, 'context_digest':digest(ctx)}
        finally: self.db.rollback()

    def _result(self, command, ctx, actor_id, created_at):
        return {**command, **{k:ctx[k] for k in ('project_id','customer_id','software_id',
            'standard_base_release_id','standard_base_version','standard_base_status')},
            'component_id':command['request_id'], 'applied_status':'DRAFT',
            'audit_event_no':'EVT-ASRC-'+uuid.UUID(command['request_id']).hex,
            'actor_principal_id':str(actor_id), 'created_at':created_at}

    def _evidence(self, event, request_id, actor, command=None, *, bound_actor=True):
        # Existing declaration/recovery calls stay actor-bound. The private,
        # non-HTTP upload coordinator may validate a collaborator's declaration
        # only after authenticating the current reader, whose exact current scope
        # is still checked by _context below. Historical authors need not retain
        # their grants for another authorized contributor to use the component.
        try:
            payload = event.payload_json
            if (event.event_no != 'EVT-ASRC-'+request_id.hex or event.event_type != 'APPLICATION_COMPONENT_DECLARED' or
                event.action != 'CREATED' or event.entity_type != 'RELEASE_COMPONENT' or event.entity_id != request_id or
                event.entity_ref != str(request_id) or event.actor_principal_id is None or
                (bound_actor and event.actor_principal_id != actor.id) or event.declared_actor_name is not None or
                not isinstance(payload,dict) or set(payload) != {'version','request','context','receipt','actor_source'} or
                type(payload['version']) is not int or payload['version'] != 1 or payload['actor_source'] != 'AUTHENTICATED_PRINCIPAL'):
                fail('asrc_request_conflict')
            original = DeclareApplicationComponent.model_validate(payload['request']).model_dump(mode='json')
            ctx, result = payload['context'], payload['receipt']
            if (original != payload['request'] or original['request_id'] != str(request_id) or
                (command is not None and command != original) or not isinstance(ctx,dict) or set(ctx) != CONTEXT_FIELDS or
                any(not isinstance(v,str) for k,v in ctx.items() if k not in ('base_component_id','base_component_version')) or
                any(v is not None and not isinstance(v,str) for k,v in ctx.items() if k in ('base_component_id','base_component_version')) or
                digest(ctx) != original['expected_context_digest'] or event.detail != original['reason'] or
                any(ctx[k] != original[k] for k in ('release_id','component_definition_id','base_component_id')) or ctx['release_status'] != 'DRAFT'):
                fail('asrc_request_conflict')
            occurred = event.occurred_at.replace(tzinfo=event.occurred_at.tzinfo or timezone.utc)
            stamped = datetime.fromisoformat(result['created_at'])
            if stamped.tzinfo is None or stamped != occurred or result != self._result(original,ctx,event.actor_principal_id,result['created_at']):
                fail('asrc_request_conflict')
            current = self._context(uuid.UUID(original['release_id']), uuid.UUID(original['component_definition_id']),
                uuid.UUID(original['base_component_id']) if original['base_component_id'] else None, actor, fresh=False)
            if any(current[k] != ctx[k] for k in ('release_id','project_id','customer_id','software_id','standard_base_release_id','component_definition_id','base_component_id')):
                fail('asrc_parent_binding_conflict')
            row = self.db.get(ReleaseComponent,request_id,populate_existing=True)
            if row is None or any((str(getattr(row,k)) if getattr(row,k) is not None else None) != original[k]
                for k in ('release_id','component_definition_id','base_component_id','version','delta_type')):
                fail('asrc_request_conflict')
            return dict(result)
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError): fail('asrc_request_conflict')

    def receipt(self, request_id, request):
        try:
            actor = self._actor(request,False)
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-ASRC-'+request_id.hex))
            if event is None:
                if self.db.get(ReleaseComponent,request_id) is not None: fail('asrc_request_conflict')
                fail('asrc_receipt_not_found',404)
            return self._evidence(event,request_id,actor)
        finally: self.db.rollback()

    def create(self, *, request, **values):
        try:
            try: body = DeclareApplicationComponent(**values)
            except ValidationError: fail('invalid_asrc_request',422)
            command = body.model_dump(mode='json')
            actor = self._actor(request,True)
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-ASRC-'+body.request_id.hex))
            if event is not None:
                result = self._evidence(event,body.request_id,actor,command)
                self.db.rollback(); return result,False
            if self.db.get(ReleaseComponent,body.request_id) is not None: fail('asrc_request_conflict')
            ctx = self._context(body.release_id,body.component_definition_id,body.base_component_id,actor,fresh=True)
            if digest(ctx) != body.expected_context_digest: fail('asrc_context_conflict')
            self.db.add(ReleaseComponent(id=body.request_id,release_id=body.release_id,
                component_definition_id=body.component_definition_id,base_component_id=body.base_component_id,
                version=body.version,delta_type=body.delta_type))
            self.db.flush()
            now = datetime.now(timezone.utc)
            result = self._result(command,ctx,actor.id,now.isoformat())
            commit_with_audit(self.db,lambda:dict(event_no=result['audit_event_no'],event_type='APPLICATION_COMPONENT_DECLARED',
                action='CREATED',entity_type='RELEASE_COMPONENT',entity_id=body.request_id,entity_ref=str(body.request_id),
                actor_name=actor.display_name[:120],actor_principal_id=actor.id,actor_display_name=actor.display_name,
                declared_actor_name=None,summary='Application component declared without artifacts',detail=body.reason,occurred_at=now,
                payload={'version':1,'request':command,'context':ctx,'receipt':result,'actor_source':'AUTHENTICATED_PRINCIPAL'}))
            return result,True
        except IntegrityError:
            self.db.rollback(); fail('asrc_request_conflict')
        except Exception:
            self.db.rollback(); raise
