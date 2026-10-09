"""Own original Impact/Acceptance evidence and atomic rollback on isolated PostgreSQL."""
import uuid
from dataclasses import replace
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.change import Issue, SoftwareChangeRequest, IssueChangeRequestRelation, AcceptanceCriterion
from app.models.testing import DvpPlan, DvpItem
from app.models.impact import IssueImpactAssessment
from app.models.acceptance import AcceptanceDvpLink
from app.models.audit import AuditEvent
from app.services.impact_assessment import AssessmentInput, record_assessment, evidence_reference_digest
from app.services.change_coverage import AssignmentInput, record_assignment
from app.services.audit import AuditEventService
from test_command_audit import trusted_actor


@pytest.fixture
def evidence_context(pg):
    engine, ids = pg
    with Session(engine) as db:
        release = db.get(Release, ids['release'])
        snapshot = db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id))
        issue = Issue(issue_no='ISSUE-ORIGINAL', title='Issue', scope='STANDARD', severity='HIGH')
        scr = SoftwareChangeRequest(request_no='SCR-ORIGINAL', title='Review', source='INTERNAL',
            scope='STANDARD', change_type='FIX', software_id=release.software_id)
        db.add_all([issue, scr]); db.flush()
        criterion = AcceptanceCriterion(change_request_id=scr.id, criterion_no='AC-1', description='Criterion')
        plan = DvpPlan(change_request_id=scr.id, plan_no='DVP-PLAN', title='Plan')
        db.add_all([criterion, plan, IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type='FIXES')]); db.flush()
        item = DvpItem(plan_id=plan.id, item_no='DVP-1', title='Test', scope='SOFTWARE_TEST')
        db.add(item); db.flush()
        ids = {**ids, 'issue':issue.id, 'scr':scr.id, 'snapshot':snapshot.id, 'criterion':criterion.id, 'dvp':item.id}
        db.commit()
    return engine, ids


def command_input(operation, ids):
    if operation == 'impact':
        return AssessmentInput(request_id=uuid.uuid4(), release_id=ids['release'], snapshot_id=ids['snapshot'],
            decision='NEEDS_REVIEW', evidence_ref='//server/share/原始证据.pdf', actor_name='Declared engineer', reason='原始原因')
    return AssignmentInput(request_id=uuid.uuid4(), criterion_id=ids['criterion'], dvp_item_id=ids['dvp'],
        actor_name='Declared engineer', reason='原始原因')


def write(db, operation, data, actor):
    return record_assessment(db, 'ISSUE-ORIGINAL', data, actor) if operation == 'impact' else record_assignment(db, 'SCR-ORIGINAL', data, actor)


@pytest.mark.parametrize('operation', ['impact','acceptance'])
def test_original_evidence_is_actor_bound_and_replay_does_not_rewrite_audit(evidence_context, operation):
    engine, ids = evidence_context
    data = command_input(operation, ids)
    with Session(engine) as db:
        actor = replace(trusted_actor(db, 'evidence-engineer', 'Authenticated engineer'), declared_name=data.actor_name)
        _, created = write(db, operation, data, actor); assert created
        db.commit()
        no = ('EVT-IMPACT-' if operation == 'impact' else 'EVT-AC-') + str(data.request_id)
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == no))
        assert event.actor_principal_id == actor.principal_id
        assert event.declared_actor_name == data.actor_name and event.detail == data.reason
        assert event.entity_id == ids['issue' if operation == 'impact' else 'scr']
        original = dict(event.payload_json)
        if operation == 'impact':
            assert original['evidence_ref_digest_version'] == 1
            assert original['evidence_ref_sha256'] == evidence_reference_digest(data.evidence_ref)
            assert 'evidence_ref' not in original
        else:
            assert original['assignment_id'] == str(data.request_id)
            assert original['criterion_id'] == str(data.criterion_id)
            assert original['dvp_item_id'] == str(data.dvp_item_id)
        _, created = write(db, operation, data, actor); db.commit(); assert not created
        assert event.payload_json == original
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.event_no == no)).all()) == 1


@pytest.mark.parametrize('operation', ['impact','acceptance'])
def test_interrupted_evidence_audit_rolls_back_business_and_event(evidence_context, monkeypatch, operation):
    engine, ids = evidence_context
    data = command_input(operation, ids)
    original = AuditEventService.record
    def interrupt(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError('interruption after audit flush')
    monkeypatch.setattr(AuditEventService, 'record', interrupt)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            try:
                write(db, operation, data, None); db.commit()
            except Exception:
                db.rollback(); raise
        assert db.get(IssueImpactAssessment if operation == 'impact' else AcceptanceDvpLink, data.request_id) is None
        no = ('EVT-IMPACT-' if operation == 'impact' else 'EVT-AC-') + str(data.request_id)
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_no == no)) is None
