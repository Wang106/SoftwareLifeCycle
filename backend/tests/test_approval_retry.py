"""Approval retry responses, step tokens, trusted actors and atomic failure paths."""
import uuid
from dataclasses import replace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from test_transactional_audit import controlled, approve
from test_impact_assessments import context
from test_command_audit import trusted_actor
from app.actor import ActorContext
from app.api.approvals import ApprovalActionRequest, ReleaseDecisionRequest, approval_action, create_release_decision
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep, ReleaseDecision
from app.models.audit import AuditEvent
from app.services.approval import ApprovalError, ApprovalService
from app.services.audit import AuditEventService


def counts(db):
    return {model: db.scalar(select(func.count()).select_from(model))
            for model in (ApprovalAction, ReleaseDecision, AuditEvent)}


def action_args(controlled, **kwargs):
    return dict(approval_no='APR', actor='Engineer', action='APPROVED', comment='Reviewed',
                request_id=uuid.uuid4(), expected_step_id=controlled[4][0].id, **kwargs)


def decision_args(**kwargs):
    values = dict(approval_no='APR', decision_no='RD', decided_by='Manager',
                  readiness_status='READY', decision='RELEASE', notes='Notes', request_id=uuid.uuid4())
    return {**values, **kwargs}


def test_action_replay_keeps_original_result_after_next_step_has_closed(controlled):
    db, _, _, approval, steps, *_ = controlled
    args = action_args(controlled)
    first = ApprovalService(db).act(**args)
    assert first.status == 'PENDING'
    ApprovalService(db).act('APR', 'Engineer', 'APPROVED', expected_step_id=steps[1].id)
    before = counts(db)
    retry = ApprovalService(db).act(**args)
    assert retry == first and retry.status == 'PENDING'
    assert db.get(ApprovalRequest, approval.id).status == 'APPROVED'
    assert counts(db) == before
    assert db.get(ApprovalAction, args['request_id']).step_id == args['expected_step_id']


@pytest.mark.parametrize('action', ['RETURNED', 'REJECTED'])
def test_terminal_action_is_replayable_once(controlled, action):
    db = controlled[0]; args = action_args(controlled); args['action'] = action
    first = ApprovalService(db).act(**args)
    before = counts(db)
    assert ApprovalService(db).act(**args) == first
    assert first.status == action and counts(db) == before
    with pytest.raises(ApprovalError, match='already closed'):
        ApprovalService(db).act(**{**args, 'request_id': uuid.uuid4()})


@pytest.mark.parametrize('field,value', [('actor', 'Different'), ('action', 'REJECTED'),
    ('comment', 'Other note'), ('expected_step_id', uuid.uuid4()), ('approval_no', 'OTHER')])
def test_action_conflicting_content_returns_conflict(controlled, field, value):
    db, release, snapshot, _, _, *_ = controlled
    args = action_args(controlled); ApprovalService(db).act(**args)
    if field == 'approval_no':
        db.add(ApprovalRequest(approval_no='OTHER', target_type='RELEASE',
            target_id=release.id, snapshot_id=snapshot.id, status='PENDING')); db.commit()
    before = counts(db)
    with pytest.raises(ApprovalError, match='request_id'):
        ApprovalService(db).act(**{**args, field: value})
    assert counts(db) == before


def test_step_token_rejects_stale_cross_approval_or_missing_tokens(controlled):
    db, _, _, approval, steps, *_ = controlled
    args = action_args(controlled)
    for token in (uuid.uuid4(), steps[1].id):
        with pytest.raises(ApprovalError, match='expected_step_id'):
            ApprovalService(db).act(**{**args, 'expected_step_id': token})
    with pytest.raises(ApprovalError, match='requires expected_step_id'):
        ApprovalService(db).act(**{**args, 'expected_step_id': None})
    ApprovalService(db).act(**args)
    before = counts(db)
    with pytest.raises(ApprovalError, match='expected_step_id'):
        ApprovalService(db).act(**{**args, 'request_id': uuid.uuid4()})
    assert counts(db) == before and steps[1].status == 'PENDING'
    # Legacy clients may intentionally act on the current step with no token/key.
    ApprovalService(db).act('APR', 'Engineer', 'APPROVED')
    assert approval.status == 'APPROVED'


@pytest.mark.parametrize('kind', ['action', 'decision'])
@pytest.mark.parametrize('case', ['principal', 'declaration', 'display_name', 'mode', 'legacy'])
def test_actor_binding_and_legacy_rows_cannot_be_claimed(controlled, kind, case):
    db = controlled[0]
    actor = trusted_actor(db, 'writer', 'Trusted Actor')
    args = action_args(controlled) if kind == 'action' else decision_args()
    if kind == 'decision': approve(controlled)
    run = ApprovalService(db).act if kind == 'action' else ApprovalService(db).create_release_decision
    if case == 'legacy':
        legacy = {**args, 'request_id': None}
        run(**legacy, actor_context=actor)
        model = ApprovalAction if kind == 'action' else ReleaseDecision
        args['request_id'] = db.scalar(select(model)).id
    else: run(**args, actor_context=actor)
    if case == 'principal': actor = trusted_actor(db, 'other', 'Trusted Actor')
    elif case == 'declaration': actor = replace(actor, declared_name='changed')
    elif case == 'display_name': actor = replace(actor, display_name='Renamed')
    elif case == 'mode': actor = ActorContext.legacy('Trusted Actor')
    before = counts(db)
    with pytest.raises(ApprovalError, match='request_id'):
        run(**args, actor_context=actor)
    assert counts(db) == before


def test_release_decision_replays_original_snapshot_after_approval_state_changes(controlled):
    db, _, _, approval, *_ = controlled
    approve(controlled); args = decision_args()
    row = ApprovalService(db).create_release_decision(**args)
    before = counts(db)
    approval.status = 'CANCELLED'; approval.snapshot_id = None; db.commit()
    retry = ApprovalService(db).create_release_decision(**args)
    assert retry.id == row.id and retry.snapshot_id == row.snapshot_id
    assert counts(db) == before
    with pytest.raises(ApprovalError, match='approved request'):
        ApprovalService(db).create_release_decision(**decision_args(decision_no='NEW'))


@pytest.mark.parametrize('field,value', [('decision_no', 'RD-OTHER'), ('decided_by', 'Other'),
    ('readiness_status', 'BLOCKED'), ('decision', 'HOLD'), ('notes', 'Changed'), ('approval_no', 'OTHER')])
def test_decision_payload_conflicts(controlled, field, value):
    db, release, snapshot, *_ = controlled
    approve(controlled); args = decision_args()
    ApprovalService(db).create_release_decision(**args)
    if field == 'approval_no':
        db.add(ApprovalRequest(approval_no='OTHER', target_type='RELEASE', target_id=release.id,
                              snapshot_id=snapshot.id, status='APPROVED')); db.commit()
    before = counts(db)
    with pytest.raises(ApprovalError, match='request_id'):
        ApprovalService(db).create_release_decision(**{**args, field: value})
    assert counts(db) == before


def test_decision_numbers_keep_history_and_duplicate_rejection(controlled):
    db = controlled[0]; approve(controlled)
    args = decision_args(); ApprovalService(db).create_release_decision(**args)
    with pytest.raises(ApprovalError, match='number already exists'):
        ApprovalService(db).create_release_decision(**{**args, 'request_id': uuid.uuid4()})
    with pytest.raises(ApprovalError, match='number already exists'):
        ApprovalService(db).create_release_decision(**{**args, 'request_id': None})
    later = ApprovalService(db).create_release_decision(**decision_args(decision_no='RD-HOLD', decision='HOLD'))
    assert later.decision == 'HOLD' and counts(db)[ReleaseDecision] == 2


@pytest.mark.parametrize('kind', ['action', 'decision'])
@pytest.mark.parametrize('failure', ['validation', 'flush', 'audit_after_flush', 'commit'])
def test_every_failure_rolls_back_and_key_can_be_reused(controlled, monkeypatch, kind, failure):
    db, _, _, approval, steps, *_ = controlled
    if kind == 'decision': approve(controlled)
    args = action_args(controlled) if kind == 'action' else decision_args()
    run = ApprovalService(db).act if kind == 'action' else ApprovalService(db).create_release_decision
    if failure == 'validation':
        if kind == 'action': args['expected_step_id'] = steps[1].id
        else: approval.status = 'PENDING'; db.commit()
    before = counts(db)
    with monkeypatch.context() as patch:
        if failure == 'flush':
            def fail(*a, **kw): raise IntegrityError('injected', {}, Exception('failure'))
            patch.setattr(db, 'flush', fail)
        elif failure == 'commit':
            def fail(*a, **kw): raise RuntimeError('commit failure')
            patch.setattr(db, 'commit', fail)
        elif failure == 'audit_after_flush':
            original = AuditEventService.record
            def fail(*a, **kw):
                original(*a, **kw)
                raise RuntimeError('audit failure')
            patch.setattr(AuditEventService, 'record', fail)
        with pytest.raises((RuntimeError, ApprovalError)): run(**args)
    assert counts(db) == before
    if kind == 'action':
        assert steps[0].status == 'PENDING' and steps[1].status == 'WAITING'
    if failure == 'validation':
        if kind == 'action': args['expected_step_id'] = steps[0].id
        else: approval.status = 'APPROVED'; db.commit()
    run(**args)
    assert counts(db)[AuditEvent] == before[AuditEvent] + 1


def test_http_shapes_status_and_validation_remain_compatible(controlled):
    db, _, _, _, steps, *_ = controlled
    key = uuid.uuid4(); payload = ApprovalActionRequest(actor='Engineer', action='APPROVED',
        request_id=key, expected_step_id=steps[0].id)
    first = approval_action('APR', payload, db)
    approval_action('APR', ApprovalActionRequest(actor='Engineer', action='APPROVED'), db)
    assert approval_action('APR', payload, db) == first == {'approval_no': 'APR', 'status': 'PENDING'}
    rd = ReleaseDecisionRequest(decision_no='RD', decided_by='Manager', readiness_status='READY',
                                decision='RELEASE', request_id=uuid.uuid4())
    assert create_release_decision('APR', rd, db) == create_release_decision('APR', rd, db)
    with pytest.raises(HTTPException) as exc:
        create_release_decision('APR', rd.model_copy(update={'notes': 'changed'}), db)
    assert exc.value.status_code == 409
    with pytest.raises(ValidationError):
        ApprovalActionRequest(actor='E', action='APPROVED', request_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        ApprovalActionRequest(actor='E', action='APPROVED', request_id='invalid', expected_step_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        ReleaseDecisionRequest(decision_no='D', decided_by='M', readiness_status='READY', decision='RELEASE', request_id='bad')


@pytest.mark.parametrize('kind,role', [('action', 'REVIEWER'), ('decision', 'RELEASE_AUTHORITY')])
def test_oidc_replay_still_requires_exact_active_role_and_binds_declaration(controlled, monkeypatch, kind, role):
    from app.core.config import settings
    from app.authorization import AuthorizationError
    from app.models.security import ProjectMembership, SecurityPrincipal
    from test_authorization import authenticated_request
    db = controlled[0]; project = controlled[-1]
    if kind == 'decision': approve(controlled)
    actor = trusted_actor(db, role, 'Authenticated Writer')
    principal = db.get(SecurityPrincipal, actor.principal_id)
    request = authenticated_request(principal)
    grant = ProjectMembership(principal_id=principal.id, project_id=project.id, role=role, status='ACTIVE')
    if kind == 'action':
        payload = ApprovalActionRequest(actor='Declared reviewer', action='APPROVED',
            request_id=uuid.uuid4(), expected_step_id=controlled[4][0].id)
        call = lambda: approval_action('APR', payload, db, request)
    else:
        payload = ReleaseDecisionRequest(decision_no='RD', decided_by='Declared manager',
            decision='RELEASE', readiness_status='READY', request_id=uuid.uuid4())
        call = lambda: create_release_decision('APR', payload, db, request)
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    before = counts(db)
    with pytest.raises(AuthorizationError): call()
    assert counts(db) == before
    db.add(grant); db.commit()
    first = call(); after = counts(db); assert call() == first and counts(db) == after
    event = db.scalar(select(AuditEvent).where(AuditEvent.actor_principal_id == actor.principal_id))
    assert event.actor_name == 'Authenticated Writer'
    assert event.declared_actor_name == (payload.actor if kind == 'action' else payload.decided_by)
    grant.status = 'SUSPENDED'; db.commit()
    with pytest.raises(AuthorizationError): call()
    assert counts(db) == after
