"""Strict two-person production authorization approval; immutable audit-only evidence."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.actor import resolve_actor
from app.auth import AuthenticatedPrincipal
from app.api.browser_sessions import require_browser_session
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, Customer, Project
from app.models.distribution import SoftwareAuthorization
from app.models.security import SecurityPrincipal, ProjectMembership, BrowserSession
from app.models.snapshot import ReleaseSnapshot
from app.services.admin_lock import admin_write_gate
from app.services.audit import commit_with_audit
from app.services.command_retry import atomic_command
from app.services.distribution import DistributionError
from app.services.release_decision import effective_release_decision
from app.services.revocation import lock_chain, ensure_chain_active


def fail(code, status=409):
    raise HTTPException(status, code)


class AuthorizationApprovalService:
    def __init__(self, db):
        self.db = db

    def _load(self, number, request, *, write):
        if settings.auth_mode != 'oidc':
            fail('oidc_not_enabled', 401)
        if write and settings.read_only_mode:
            fail('read_only_mode', 403)
        principal = getattr(request.state, 'principal', None)
        if not isinstance(principal, AuthenticatedPrincipal):
            fail('authenticated_principal_required', 401)
        admin_write_gate(self.db)
        actor = self.db.scalar(select(SecurityPrincipal).where(SecurityPrincipal.id == principal.id,
            SecurityPrincipal.issuer == principal.issuer, SecurityPrincipal.subject == principal.subject)
            .with_for_update().execution_options(populate_existing=True))
        if actor is None or actor.status != 'ACTIVE':
            fail('inactive_principal', 401)
        if actor.principal_type != 'USER':
            fail('user_principal_required', 403)
        sid = require_browser_session(request, self.db, actor.id)
        if sid is not None:
            self.db.scalar(select(BrowserSession).where(BrowserSession.id == sid).with_for_update()
                           .execution_options(populate_existing=True))
            require_browser_session(request, self.db, actor.id)
        row = self.db.scalar(select(SoftwareAuthorization).where(SoftwareAuthorization.authorization_no == number))
        if row is None:
            fail('authorization_not_found', 404)
        project_id = row.project_id
        membership = self.db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id == actor.id,
            ProjectMembership.project_id == project_id, ProjectMembership.role == 'PRODUCTION_AUTHORITY',
            ProjectMembership.status == 'ACTIVE').with_for_update().execution_options(populate_existing=True))
        if membership is None:
            fail('production_authority_required', 403)
        chain = lock_chain(self.db, 'AUTHORIZATION', row.id, DistributionError)
        row = chain.authorization
        if row is None or row.authorization_no != number or row.project_id != project_id:
            fail('authorization_context_changed')
        if not chain.package or not chain.distribution or row.release_id != chain.release.id or \
                row.distribution_id != chain.distribution.id or chain.distribution.delivery_package_id != chain.package.id or \
                chain.package.release_id != chain.release.id:
            fail('authorization_chain_mismatch')
        creation = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-PA-'+row.id.hex))
        expected = {'release_id': str(row.release_id), 'snapshot_id': str(row.snapshot_id),
            'distribution_id': str(row.distribution_id), 'distribution_no': chain.distribution.distribution_no,
            'delivery_package_id': str(chain.package.id), 'package_no': chain.package.package_no,
            'revision': chain.package.revision, 'customer_id': str(row.customer_id), 'project_id': str(row.project_id),
            'site_code': row.site_code, 'line_code': row.line_code, 'purpose': row.purpose,
            'batch_limit': row.batch_limit, 'status': 'DRAFT', 'actor_source': 'AUTHENTICATED_PRINCIPAL'}
        if (creation is None or creation.event_type != 'AUTHORIZATION' or creation.action != 'CREATED' or
                creation.entity_type != 'SOFTWARE_AUTHORIZATION' or creation.entity_id != row.id or
                creation.entity_ref != row.authorization_no or creation.actor_principal_id is None or
                creation.declared_actor_name is not None or creation.detail != row.restriction_note or
                any(creation.payload_json.get(k) != v for k, v in expected.items())):
            fail('trusted_creator_required')
        original_request = creation.payload_json.get('request')
        expected_request = {k: expected[k] for k in ('release_id', 'distribution_id', 'customer_id', 'project_id',
            'site_code', 'line_code', 'purpose', 'batch_limit')}
        expected_request.update(authorization_no=row.authorization_no, restriction_note=row.restriction_note)
        if original_request is not None and original_request != expected_request:
            fail('trusted_creator_required')
        if creation.actor_principal_id == actor.id:
            fail('creator_cannot_approve', 403)
        return row, chain, creation, actor

    def _context(self, row, chain, creation):
        ensure_chain_active(self.db, 'AUTHORIZATION', row.id, DistributionError)
        decision = effective_release_decision(self.db, row.release_id)
        if not decision or decision.decision != 'RELEASE' or decision.snapshot_id != row.snapshot_id:
            fail('released_snapshot_required')
        snapshot = self.db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.id == row.snapshot_id)
            .with_for_update().execution_options(populate_existing=True))
        if snapshot is None or snapshot.release_id != row.release_id or snapshot.status != 'FROZEN':
            fail('frozen_snapshot_required')
        if (chain.package.snapshot_id != row.snapshot_id or chain.package.purpose != row.purpose or
                chain.package.status not in ('READY', 'APPROVED') or
                chain.distribution.status not in ('READY', 'SENT', 'ACKNOWLEDGED')):
            fail('authorization_chain_ineligible')
        detail = self.db.get(ApplicationReleaseDetail, row.release_id)
        customer = self.db.get(Customer, row.customer_id)
        project = self.db.get(Project, row.project_id)
        if (not detail or detail.customer_id != row.customer_id or detail.project_id != row.project_id or
                not customer or not project or project.customer_id != customer.id or
                chain.distribution.recipient_type != 'CUSTOMER' or chain.distribution.recipient_code != customer.code or
                chain.package.recipient_type != 'CUSTOMER' or chain.package.recipient_code != customer.code):
            fail('authorization_scope_mismatch')
        context = {'authorization_id': str(row.id), 'authorization_no': row.authorization_no,
            'release_id': str(row.release_id), 'snapshot_id': str(row.snapshot_id), 'release_decision_id': str(decision.id),
            'distribution_id': str(chain.distribution.id), 'delivery_package_id': str(chain.package.id),
            'package_revision': chain.package.revision, 'customer_id': str(row.customer_id),
            'project_id': str(row.project_id), 'site_code': row.site_code, 'line_code': row.line_code,
            'purpose': row.purpose, 'batch_limit': row.batch_limit, 'restriction_note': row.restriction_note,
            'creation_event_id': str(creation.id), 'creator_principal_id': str(creation.actor_principal_id)}
        digest = hashlib.sha256(json.dumps({'version': 1, 'context': context}, ensure_ascii=False,
                                          sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'version': 1, 'context': context, 'context_digest': digest}

    def context(self, authorization_no, request):
        try:
            row, chain, creation, _actor = self._load(authorization_no, request, write=False)
            if row.status != 'DRAFT':
                fail('authorization_not_draft')
            return self._context(row, chain, creation)
        finally:
            self.db.rollback()  # GET reserves nothing and releases all bounded read locks.

    def approve(self, authorization_no, request, request_id, expected_context_digest, reason):
        with atomic_command(self.db, DistributionError):
            if (not isinstance(request_id, uuid.UUID) or not isinstance(expected_context_digest, str) or
                    len(expected_context_digest) != 64 or any(c not in '0123456789abcdef' for c in expected_context_digest) or
                    not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000 or reason != reason.strip()):
                fail('invalid_approval_request', 422)
            row, chain, creation, actor = self._load(authorization_no, request, write=True)
            command = {'authorization_id': str(row.id), 'authorization_no': row.authorization_no,
                       'expected_context_digest': expected_context_digest, 'reason': reason}
            event_no = 'EVT-PAA-'+request_id.hex
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == event_no))
            if event is not None:
                if (event.event_type != 'AUTHORIZATION_APPROVED' or event.action != 'APPROVED' or
                        event.entity_type != 'SOFTWARE_AUTHORIZATION' or event.entity_id != row.id or
                        event.entity_ref != row.authorization_no or event.actor_principal_id != actor.id or
                        event.payload_json.get('request') != command):
                    fail('approval_request_conflict')
                receipt = event.payload_json['receipt']
                self.db.commit()
                return receipt
            if row.status != 'DRAFT':
                fail('authorization_not_draft')
            context = self._context(row, chain, creation)
            if context['context_digest'] != expected_context_digest:
                fail('approval_context_conflict')
            now = datetime.now(timezone.utc)
            receipt = {'authorization_id': str(row.id), 'authorization_no': row.authorization_no,
                'request_id': str(request_id), 'audit_event_no': event_no, 'applied_status': 'APPROVED',
                'approved_at': now.isoformat(), 'creator_principal_id': str(creation.actor_principal_id),
                'approver_principal_id': str(actor.id), 'expected_context_digest': expected_context_digest, 'reason': reason}
            row.status = 'APPROVED'
            row.approved_at = now
            commit_with_audit(self.db, lambda: dict(event_no=event_no,event_type='AUTHORIZATION_APPROVED',
                action='APPROVED',entity_type='SOFTWARE_AUTHORIZATION',entity_id=row.id,entity_ref=row.authorization_no,
                **resolve_actor(request).audit_fields(),summary='Production authorization approved by a different project authority',
                occurred_at=now,payload={'version':1,'request':command,'context':context['context'],
                                         'receipt':receipt,'actor_source':'AUTHENTICATED_PRINCIPAL'}))
            return receipt
