"""Explicit predecessor-bound corrections never rewrite the original judgment."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import func, select

from test_impact_assessments import context, data
from app.actor import ActorContext
from app.api.impact import create_assessment, assessment_history, impact_evidence, issue_impact
from app.api.issue_views import Empty, Pages, SnapshotSelection, assessments_page, candidates_page, evidence_summary, summary
from app.models.audit import AuditEvent
from app.models.change import Issue
from app.models.impact import IssueImpactAssessment
from app.models.snapshot import ReleaseSnapshot
from app.services.impact_assessment import AssessmentError, AuditEventService, record_assessment


def correction(release, snapshot, original, **changes):
    return data(release, snapshot, **{
        'supersedes_id': original.id, 'correction_reason': 'Reviewed corrected bench evidence',
        'decision': 'NOT_AFFECTED', 'reason': 'Fault belongs to another component', **changes})


def append(db, issue, body):
    return create_assessment(issue.issue_no, body, Response(), db)


def test_append_preserves_original_and_links_atomic_audit(context):
    db, issue, release, snapshot, _ = context
    first = data(release, snapshot, evidence_ref='//private/original.pdf')
    append(db, issue, first)
    original = db.get(IssueImpactAssessment, first.request_id)
    before = {c.name: getattr(original, c.name) for c in original.__table__.columns}
    body = correction(release, snapshot, original)
    result = append(db, issue, body)
    assert result['supersedes_id'] == str(original.id)
    assert result['correction_reason'] == body.correction_reason
    assert {c.name: getattr(original, c.name) for c in original.__table__.columns} == before
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{body.request_id}'))
    assert event.action == 'SUPERSEDE'
    assert event.payload_json['supersedes_id'] == str(original.id)
    assert event.payload_json['previous_decision'] == 'AFFECTED'
    assert event.payload_json['correction_reason'] == body.correction_reason
    assert '//private/original.pdf' not in str(event.payload_json)
    assert db.scalar(select(func.count()).select_from(IssueImpactAssessment)) == 2
    original_event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{first.request_id}'))
    original_payload = dict(original_event.payload_json)
    replay = append(db, issue, first)
    assert replay['decision'] == first.decision and replay['reason'] == first.reason
    assert replay['superseded_by_id'] == str(body.request_id)
    assert original_event.action == 'ASSESS' and original_event.payload_json == original_payload


@pytest.mark.parametrize('changes', [
    {'supersedes_id': uuid.uuid4()}, {'correction_reason': 'Correction only'},
    {'supersedes_id': uuid.uuid4(), 'correction_reason': '  '},
    {'supersedes_id': uuid.uuid4(), 'correction_reason': 'x' * 4001},
])
def test_correction_requires_both_predecessor_and_nonblank_bounded_reason(context, changes):
    _, _, release, snapshot, _ = context
    with pytest.raises(ValidationError): data(release, snapshot, **changes)


@pytest.mark.parametrize('field', ['decision', 'reason', 'evidence_ref', 'supersedes_id', 'correction_reason', 'actor_name'])
def test_retry_is_exact_and_does_not_reapply_after_a_later_correction(context, field):
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    body = correction(release, snapshot, db.get(IssueImpactAssessment, root.request_id))
    append(db, issue, body)
    later = correction(release, snapshot, db.get(IssueImpactAssessment, body.request_id), decision='NEEDS_REVIEW')
    append(db, issue, later)
    response = Response(); replay = create_assessment(issue.issue_no, body, response, db)
    assert response.status_code == 200 and replay['id'] == str(body.request_id)
    value = uuid.uuid4() if field == 'supersedes_id' else 'AFFECTED' if field == 'decision' else 'Changed'
    with pytest.raises(HTTPException) as error: append(db, issue, body.model_copy(update={field: value}))
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 3
    assert impact_evidence(issue.issue_no, release.id, db)['assessment']['id'] == str(later.request_id)


@pytest.mark.parametrize('case', ['missing', 'self', 'foreign_issue', 'foreign_snapshot', 'stale', 'superseded'])
def test_wrong_predecessor_context_and_stale_head_fail_without_partial_write(context, case):
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    original = db.get(IssueImpactAssessment, root.request_id)
    body = correction(release, snapshot, original)
    if case == 'missing': body = body.model_copy(update={'supersedes_id': uuid.uuid4()})
    if case == 'self': body = body.model_copy(update={'supersedes_id': body.request_id})
    if case == 'foreign_issue':
        other = Issue(issue_no='OTHER', title='Other', scope='STANDARD', severity='HIGH')
        db.add(other); db.commit(); original.issue_id = other.id; db.commit()
    if case == 'foreign_snapshot':
        other = ReleaseSnapshot(snapshot_no='OTHER-SNAPSHOT', release_id=release.id, snapshot_number=2,
            content_hash='b' * 64, status='FROZEN')
        db.add(other); db.commit(); body = body.model_copy(update={'snapshot_id': other.id})
    if case == 'stale': append(db, issue, data(release, snapshot, decision='NEEDS_REVIEW'))
    if case == 'superseded': append(db, issue, correction(release, snapshot, original))
    before = db.scalar(select(func.count()).select_from(IssueImpactAssessment))
    events = db.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(HTTPException) as error: append(db, issue, body)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(IssueImpactAssessment)) == before
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == events


def test_all_current_views_use_leaf_not_superseded_timestamp_and_history_keeps_both(context):
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    body = correction(release, snapshot, db.get(IssueImpactAssessment, root.request_id))
    append(db, issue, body)
    # A clock/UUID tie must never resurrect the explicitly superseded original.
    db.get(IssueImpactAssessment, body.request_id).created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    info = summary(issue.issue_no, Empty(), db)
    pin = Pages(issue_id=issue.id)
    assert info['assessment_count'] == 2
    assert impact_evidence(issue.issue_no, release.id, db)['assessment']['id'] == str(body.request_id)
    assert issue_impact(issue.issue_no, db)['candidate_releases'][0]['assessment']['id'] == str(body.request_id)
    assert candidates_page(issue.issue_no, pin, db)['items'][0]['assessment_id'] == str(body.request_id)
    assert evidence_summary(issue.issue_no, release.id, SnapshotSelection(snapshot_id=snapshot.id), db)['assessment']['id'] == str(body.request_id)
    rows = {r['id']: r for r in assessments_page(issue.issue_no, pin, db)['items']}
    assert rows[str(root.request_id)]['superseded_by_id'] == str(body.request_id)
    assert rows[str(body.request_id)]['supersedes_id'] == str(root.request_id)
    assert rows[str(body.request_id)]['superseded_by_id'] is None
    legacy = {r['id']: r for r in assessment_history(issue.issue_no, 50, db)['items']}
    assert legacy[str(root.request_id)]['superseded_by_id'] == str(body.request_id)


def test_correction_audit_failure_rolls_back_and_keeps_original_effective(context, monkeypatch):
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    body = correction(release, snapshot, db.get(IssueImpactAssessment, root.request_id))
    def fail(*args, **kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService, 'record', fail)
    with pytest.raises(RuntimeError): append(db, issue, body)
    assert db.get(IssueImpactAssessment, body.request_id) is None
    assert impact_evidence(issue.issue_no, release.id, db)['assessment']['id'] == str(root.request_id)
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize('field', ['supersedes_id', 'previous_decision', 'correction_reason', 'assessment_id',
    'release_id', 'snapshot_id', 'decision', 'evidence_ref_sha256', 'actor_source'])
def test_correction_retry_requires_original_authenticated_actor_and_audit_payload(context, field):
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    body = correction(release, snapshot, db.get(IssueImpactAssessment, root.request_id))
    actor = ActorContext('Trusted reviewer', uuid.uuid4(), 'Trusted reviewer', body.actor_name, 'AUTHENTICATED_PRINCIPAL')
    row, _ = record_assessment(db, issue.issue_no, body, actor); db.commit()
    assert row.actor_name == actor.name
    other = ActorContext(actor.name, uuid.uuid4(), actor.display_name, actor.declared_name, actor.source)
    with pytest.raises(AssessmentError): record_assessment(db, issue.issue_no, body, other)
    db.rollback()
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{body.request_id}'))
    event.payload_json = {**event.payload_json, field: 'Changed'}; db.commit()
    with pytest.raises(AssessmentError): record_assessment(db, issue.issue_no, body, actor)
    db.rollback()
    event.payload_json = None; db.commit()
    with pytest.raises(AssessmentError): record_assessment(db, issue.issue_no, body, actor)
    db.rollback()


def test_legacy_new_judgments_remain_independent_not_implicit_corrections(context):
    db, issue, release, snapshot, _ = context
    one = data(release, snapshot); two = data(release, snapshot, decision='NEEDS_REVIEW')
    append(db, issue, one); append(db, issue, two)
    assert db.get(IssueImpactAssessment, one.request_id).supersedes_id is None
    assert db.get(IssueImpactAssessment, two.request_id).supersedes_id is None
    assert all(event.action == 'ASSESS' for event in db.scalars(select(AuditEvent)))
    assert impact_evidence(issue.issue_no, release.id, db)['assessment']['id'] == str(two.request_id)


def test_scalar_history_growth_keeps_query_shape_and_successor_links_across_pages(context):
    from sqlalchemy import event
    db, issue, release, snapshot, _ = context
    root = data(release, snapshot); append(db, issue, root)
    number, identifier, release_id, snapshot_id = issue.issue_no, issue.id, release.id, snapshot.id
    queries = []
    def capture(_connection, _cursor, statement, *_): queries.append(statement)
    event.listen(db.bind, 'before_cursor_execute', capture)
    def probe():
        db.expunge_all(); queries.clear()
        info = summary(number, Empty(), db)
        page = assessments_page(number, Pages(issue_id=identifier, limit=1), db)
        selected = evidence_summary(number, release_id, SnapshotSelection(snapshot_id=snapshot_id), db)
        assert len(page['items']) == 1 and not db.identity_map
        return info, page, selected, list(queries)
    try:
        _, _, _, before = probe()
        parent = root.request_id
        # Synthetic immutable history growth, not an authenticated acceptance test.
        for _ in range(60):
            child = uuid.uuid4()
            db.add(IssueImpactAssessment(id=child, issue_id=identifier, release_id=release_id, snapshot_id=snapshot_id,
                decision='NEEDS_REVIEW', reason='Judgment', actor_name='Reviewer', supersedes_id=parent, correction_reason='Correction'))
            db.flush(); parent = child
        db.commit()
        info, page, selected, after = probe()
        assert before == after and info['assessment_count'] == page['total'] == 61
        assert selected['assessment']['id'] == str(parent)
        assert page['items'][0]['supersedes_id'] is not None
        oldest = assessments_page(number, Pages(issue_id=identifier, limit=1, offset=60), db)['items'][0]
        assert oldest['id'] == str(root.request_id) and oldest['superseded_by_id'] is not None
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)


@pytest.mark.parametrize('access', ['reviewer', 'missing_identity', 'wrong_project', 'contributor', 'suspended'])
def test_corrections_keep_exact_reviewer_scope_and_trusted_actor(context, monkeypatch, access):
    from test_authorization import authenticated_request
    from app.authorization import AuthorizationError
    from app.core.config import settings
    from app.models.core import Customer, Project, ApplicationReleaseDetail
    from app.models.security import SecurityPrincipal, ProjectMembership
    db, issue, release, snapshot, scr = context
    root = data(release, snapshot); append(db, issue, root)
    customer = Customer(code='CORRECTION', name='Customer'); db.add(customer); db.flush()
    project = Project(customer_id=customer.id, project_code='P', name='Project')
    other = Project(customer_id=customer.id, project_code='OTHER', name='Other')
    principal = SecurityPrincipal(issuer='https://identity.example.com', subject='reviewer',
        principal_type='USER', display_name='Trusted reviewer')
    db.add_all([project, other, principal]); db.flush()
    release.release_type = 'APPLICATION'; scr.project_id = project.id
    db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id,
        standard_base_release_id=release.id))
    db.add(ProjectMembership(principal_id=principal.id, project_id=other.id if access == 'wrong_project' else project.id,
        role='CONTRIBUTOR' if access == 'contributor' else 'REVIEWER', status='SUSPENDED' if access == 'suspended' else 'ACTIVE'))
    db.commit()
    body = correction(release, snapshot, db.get(IssueImpactAssessment, root.request_id), actor_name='Untrusted declaration')
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    request = None if access == 'missing_identity' else authenticated_request(principal)
    if access != 'reviewer':
        with pytest.raises(AuthorizationError): create_assessment(issue.issue_no, body, Response(), db, request)
        assert db.get(IssueImpactAssessment, body.request_id) is None
    else:
        result = create_assessment(issue.issue_no, body, Response(), db, request)
        assert result['actor_name'] == 'Trusted reviewer'
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{body.request_id}'))
        assert event.actor_principal_id == principal.id and event.declared_actor_name == body.actor_name
