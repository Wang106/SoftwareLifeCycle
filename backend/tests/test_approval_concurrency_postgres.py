"""Approval transitions on real PostgreSQL, using isolated migrated schemas."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_command_concurrency_postgres import pg, count, overlapping_commands
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep, ReleaseDecision
from app.models.audit import AuditEvent
from app.models.snapshot import ReleaseSnapshot
from app.services.approval import ApprovalError, ApprovalService
from app.services.audit import AuditEventService


@pytest.fixture
def approvals(pg):
    engine, ids = pg
    with Session(engine, expire_on_commit=False) as db:
        snapshot = db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == ids['release']))
        requests = [ApprovalRequest(approval_no=f'APR-{n}', target_type='RELEASE',
            target_id=ids['release'], snapshot_id=snapshot.id, status='PENDING') for n in (1, 2)]
        db.add_all(requests); db.flush()
        steps = [[ApprovalStep(approval_request_id=row.id, step_order=n, role_name='Review',
            status='PENDING' if n == 1 else 'WAITING') for n in (1, 2)] for row in requests]
        db.add_all(steps[0] + steps[1]); db.commit()
        ids = {**ids, 'approvals': [row.id for row in requests],
               'steps': [[row.id for row in group] for group in steps]}
    return engine, ids


def ready(engine, ids):
    with Session(engine) as db:
        for approval_id in ids['approvals']:
            db.get(ApprovalRequest, approval_id).status = 'APPROVED'
        for group in ids['steps']:
            for step_id in group: db.get(ApprovalStep, step_id).status = 'APPROVED'
        db.commit()


def decide(db, key=None, approval_no='APR-1', decision_no='RD', notes=None):
    return ApprovalService(db).create_release_decision(approval_no, decision_no, 'Manager',
        'READY', 'RELEASE', notes=notes, request_id=key)


@pytest.mark.parametrize('same_key', [False, True])
def test_same_step_competition_or_identical_replay_never_advances_next_step(approvals, monkeypatch, same_key):
    engine, ids = approvals; first_key = uuid.uuid4(); second_key = first_key if same_key else uuid.uuid4()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: ApprovalService(db).act('APR-1', 'Engineer', 'APPROVED',
            request_id=first_key, expected_step_id=ids['steps'][0][0]),
        lambda db: ApprovalService(db).act('APR-1', 'Engineer', 'APPROVED',
            request_id=second_key, expected_step_id=ids['steps'][0][0]))
    assert first[0] == 'ok' and second[0] == ('ok' if same_key else 'conflict')
    if not same_key: assert 'expected_step_id' in second[1]
    with Session(engine) as db:
        assert count(db, ApprovalAction) == count(db, AuditEvent, entity_type='APPROVAL_REQUEST') == 1
        assert db.get(ApprovalStep, ids['steps'][0][0]).status == 'APPROVED'
        assert db.get(ApprovalStep, ids['steps'][0][1]).status == 'PENDING'
        assert db.get(ApprovalRequest, ids['approvals'][0]).status == 'PENDING'


@pytest.mark.parametrize('action', ['RETURNED', 'REJECTED'])
def test_terminal_concurrent_replay_has_one_action_and_event(approvals, monkeypatch, action):
    engine, ids = approvals; key = uuid.uuid4()
    def act(db):
        return ApprovalService(db).act('APR-1', 'Engineer', action,
            request_id=key, expected_step_id=ids['steps'][0][0])
    results = overlapping_commands(engine, monkeypatch, act, act)
    assert all(row[0] == 'ok' for row in results)
    with Session(engine) as db:
        assert count(db, ApprovalAction) == count(db, AuditEvent, entity_type='APPROVAL_REQUEST') == 1
        assert db.get(ApprovalRequest, ids['approvals'][0]).status == action
        assert db.get(ApprovalStep, ids['steps'][0][1]).status == 'WAITING'


def test_concurrent_different_action_same_key_conflicts(approvals, monkeypatch):
    engine, ids = approvals; key = uuid.uuid4()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: ApprovalService(db).act('APR-1', 'Engineer', 'APPROVED', request_id=key,
                                          expected_step_id=ids['steps'][0][0]),
        lambda db: ApprovalService(db).act('APR-1', 'Engineer', 'REJECTED', request_id=key,
                                          expected_step_id=ids['steps'][0][0]))
    assert first[0] == 'ok' and second[0] == 'conflict' and 'request_id' in second[1]
    with Session(engine) as db:
        assert count(db, ApprovalAction) == 1
        assert db.get(ApprovalStep, ids['steps'][0][1]).status == 'PENDING'


@pytest.mark.parametrize('changed', [False, True])
def test_concurrent_decision_replay_or_payload_conflict(approvals, monkeypatch, changed):
    engine, ids = approvals; ready(engine, ids); key = uuid.uuid4()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: decide(db, key),
        lambda db: decide(db, key, notes='changed' if changed else None))
    assert first[0] == 'ok' and second[0] == ('conflict' if changed else 'ok')
    if changed: assert 'request_id' in second[1]
    else: assert second[1] == first[1]
    with Session(engine) as db:
        assert count(db, ReleaseDecision) == count(db, AuditEvent, entity_type='RELEASE_DECISION') == 1


@pytest.mark.parametrize('different_number', [False, True])
def test_concurrent_decision_business_numbers_keep_existing_history_contract(approvals, monkeypatch, different_number):
    engine, ids = approvals; ready(engine, ids)
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: decide(db, uuid.uuid4()),
        lambda db: decide(db, uuid.uuid4(), decision_no='RD-2' if different_number else 'RD'))
    assert first[0] == 'ok' and second[0] == ('ok' if different_number else 'conflict')
    with Session(engine) as db:
        assert count(db, ReleaseDecision) == count(db, AuditEvent, entity_type='RELEASE_DECISION') == (2 if different_number else 1)


@pytest.mark.parametrize('final_action', ['APPROVED', 'RETURNED', 'REJECTED'])
def test_decision_waits_for_final_approval_transaction_then_rechecks_status(approvals, monkeypatch, final_action):
    engine, ids = approvals
    with Session(engine) as db:
        db.get(ApprovalStep, ids['steps'][0][0]).status = 'APPROVED'
        db.get(ApprovalStep, ids['steps'][0][1]).status = 'PENDING'; db.commit()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: ApprovalService(db).act('APR-1', 'Engineer', final_action, request_id=uuid.uuid4(),
                                          expected_step_id=ids['steps'][0][1]),
        lambda db: decide(db, uuid.uuid4()))
    assert first[0] == 'ok' and second[0] == ('ok' if final_action == 'APPROVED' else 'conflict')
    with Session(engine) as db:
        expected = 1 if final_action == 'APPROVED' else 0
        assert count(db, ReleaseDecision) == count(db, AuditEvent, entity_type='RELEASE_DECISION') == expected
        assert count(db, ApprovalAction) == 1


@pytest.mark.parametrize('kind', ['action', 'decision'])
def test_cross_approval_global_key_collision_rolls_back_losing_transaction(approvals, monkeypatch, kind):
    engine, ids = approvals; key = uuid.uuid4()
    if kind == 'decision': ready(engine, ids)
    def run(db, number):
        if kind == 'decision': return decide(db, key, approval_no=f'APR-{number}', decision_no=f'RD-{number}')
        return ApprovalService(db).act(f'APR-{number}', 'Engineer', 'APPROVED', request_id=key,
                                      expected_step_id=ids['steps'][number-1][0])
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: run(db, 1), lambda db: run(db, 2))
    assert first[0] == 'ok' and second[0] == 'conflict'
    with Session(engine) as db:
        if kind == 'action':
            assert count(db, ApprovalAction) == 1
            assert db.get(ApprovalStep, ids['steps'][1][0]).status == 'PENDING'
            assert db.get(ApprovalStep, ids['steps'][1][1]).status == 'WAITING'
        else: assert count(db, ReleaseDecision) == 1
        assert count(db, AuditEvent) == 2  # initial snapshot event plus the winning command


@pytest.mark.parametrize('kind', ['action', 'decision'])
def test_scope_rows_are_refreshed_before_transition_validation(approvals, kind):
    engine, ids = approvals
    if kind == 'decision': ready(engine, ids)
    with Session(engine, expire_on_commit=False) as db:
        cached = db.get(ApprovalRequest, ids['approvals'][0]); db.commit()
        with Session(engine) as writer:
            writer.get(ApprovalRequest, cached.id).status = 'CANCELLED'; writer.commit()
        with pytest.raises(ApprovalError):
            if kind == 'decision': decide(db, uuid.uuid4())
            else: ApprovalService(db).act('APR-1', 'Engineer', 'APPROVED', request_id=uuid.uuid4(),
                                         expected_step_id=ids['steps'][0][0])
        assert not db.in_transaction()
        assert count(db, ApprovalAction) == count(db, ReleaseDecision) == 0


@pytest.mark.parametrize('kind', ['action', 'decision'])
def test_audit_failure_reverts_step_domain_event_and_releases_lock(approvals, monkeypatch, kind):
    engine, ids = approvals; key = uuid.uuid4()
    if kind == 'decision': ready(engine, ids)
    def run(db):
        if kind == 'decision': return decide(db, key)
        return ApprovalService(db).act('APR-1', 'Engineer', 'APPROVED', request_id=key,
                                      expected_step_id=ids['steps'][0][0])
    original = AuditEventService.record
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('after audit flush')
    with Session(engine) as db:
        before = {model: count(db, model) for model in (ApprovalAction, ReleaseDecision, AuditEvent)}
        monkeypatch.setattr(AuditEventService, 'record', fail)
        with pytest.raises(RuntimeError): run(db)
        assert not db.in_transaction()
        assert {model: count(db, model) for model in before} == before
        if kind == 'action':
            assert db.get(ApprovalStep, ids['steps'][0][0]).status == 'PENDING'
            assert db.get(ApprovalStep, ids['steps'][0][1]).status == 'WAITING'
    monkeypatch.setattr(AuditEventService, 'record', original)
    with Session(engine) as db:
        if kind == 'decision': assert run(db).id == key
        else: assert run(db).status == 'PENDING'
