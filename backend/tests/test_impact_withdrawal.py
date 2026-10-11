"""Withdrawal semantics, exact original audit and explicit new judgment contracts."""
import uuid
from dataclasses import replace
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from test_impact_assessments import context, data
from app.actor import ActorContext
from app.api.impact import create_assessment, create_withdrawal
from app.api.issue_views import Empty, Pages, SnapshotSelection, candidates_page, evidence_summary, assessments_page, summary
from app.models.audit import AuditEvent
from app.models.impact import IssueImpactAssessment
from app.services.audit import AuditEventService
from app.services.impact_assessment import AssessmentError, record_assessment
from app.services.impact_withdrawal import WithdrawalInput, record_withdrawal


def withdrawal(release, snapshot, previous, **changes):
    return WithdrawalInput(**dict(request_id=uuid.uuid4(), release_id=release.id, snapshot_id=snapshot.id,
        supersedes_id=previous, reason='Retract disputed bench interpretation',
        correction_reason='Independent review required', actor_name='Engineer') | changes)


def append(db, issue, release, snapshot):
    request = data(release, snapshot)
    create_assessment(issue.issue_no, request, Response(), db)
    return request


def test_withdrawal_terminal_never_revives_independent_roots_and_explicit_new_judgment(context):
    db, issue, release, snapshot, _ = context
    first = append(db, issue, release, snapshot); second = append(db, issue, release, snapshot)
    before = dict(db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{second.request_id}')).payload_json)
    body = withdrawal(release, snapshot, second.request_id)
    response = Response(); original = create_withdrawal(issue.issue_no, body, response, db)
    assert response.status_code == 201 and original['original_operation']['decision'] is None
    assert original['context_observation']['context_state'] == 'WITHDRAWN'
    result = evidence_summary(issue.issue_no, release.id, SnapshotSelection(snapshot_id=snapshot.id), db)
    assert result['assessment'] is None and result['terminal_event_id'] == str(body.request_id)
    candidate = candidates_page(issue.issue_no, Pages(issue_id=issue.id), db)['items'][0]
    assert candidate['assessment_id'] is candidate['decision'] is None
    assert candidate['context_state'] == 'WITHDRAWN'
    info = summary(issue.issue_no, Empty(), db)
    assert info['assessment_count'] == 2 and info['history_count'] == 3
    history = assessments_page(issue.issue_no, Pages(issue_id=issue.id,limit=1,offset=2), db)
    assert history['items'][0]['id'] == str(first.request_id)
    assert history['items'][0]['is_context_terminal'] is False
    with pytest.raises(HTTPException, match='explicitly confirm'):
        create_assessment(issue.issue_no, data(release, snapshot), Response(), db)
    restored = data(release, snapshot, after_withdrawal_id=body.request_id)
    create_assessment(issue.issue_no, restored, Response(), db)
    replay = create_withdrawal(issue.issue_no, body, response, db)
    assert response.status_code == 200 and replay['original_operation'] == original['original_operation']
    assert replay['context_observation']['terminal_event_id'] == str(restored.request_id)
    assert db.scalar(select(func.count()).select_from(IssueImpactAssessment)) == 4
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{second.request_id}')).payload_json == before
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)['assessment']['id'] == str(restored.request_id)


@pytest.mark.parametrize('field', ['reason','correction_reason','actor_name','release_id','snapshot_id','supersedes_id'])
def test_replay_conflicts_on_any_original_body_change(context, field):
    db, issue, release, snapshot, _ = context
    root = append(db, issue, release, snapshot); body = withdrawal(release,snapshot,root.request_id)
    create_withdrawal(issue.issue_no, body, Response(), db)
    value = uuid.uuid4() if field.endswith('_id') else 'Changed original request'
    with pytest.raises(HTTPException):
        create_withdrawal(issue.issue_no, body.model_copy(update={field:value}), Response(), db)
    assert db.scalar(select(func.count()).select_from(IssueImpactAssessment)) == 2


@pytest.mark.parametrize('field', ['request_body_sha256','request_body_digest_version','context_seq','history_action','decision',
    'assessment_id','release_id','snapshot_id','previous_decision','correction_reason','evidence_ref_sha256','actor_source','after_withdrawal_id'])
def test_wrong_original_audit_never_confirms_replay(context, field):
    db, issue, release, snapshot, _ = context
    root = append(db,issue,release,snapshot); body = withdrawal(release,snapshot,root.request_id)
    record_withdrawal(db,issue.issue_no,body); db.commit()
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-IMPACT-{body.request_id}'))
    event.payload_json = {**event.payload_json,field:'Wrong original value'}; db.commit()
    with pytest.raises(AssessmentError):record_withdrawal(db,issue.issue_no,body)
    db.rollback()


@pytest.mark.parametrize('case', ['missing','wrong_type','wrong_entity','wrong_actor','wrong_detail'])
def test_missing_or_wrong_event_identity_refuses_confirmation(context,case):
    db,issue,release,snapshot,_=context
    root=append(db,issue,release,snapshot);body=withdrawal(release,snapshot,root.request_id)
    record_withdrawal(db,issue.issue_no,body);db.commit()
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==f'EVT-IMPACT-{body.request_id}'))
    if case=='missing':db.delete(event)
    elif case=='wrong_type':event.event_type='OTHER'
    elif case=='wrong_entity':event.entity_id=uuid.uuid4()
    elif case=='wrong_actor':event.actor_name='Someone else'
    else:event.detail='Changed detail'
    db.commit()
    with pytest.raises(AssessmentError):record_withdrawal(db,issue.issue_no,body)
    db.rollback()


def test_audit_failure_rolls_back_withdrawal_and_same_id_cross_operation_conflicts(context,monkeypatch):
    db,issue,release,snapshot,_=context;root=append(db,issue,release,snapshot)
    body=withdrawal(release,snapshot,root.request_id)
    with monkeypatch.context() as patch:
        patch.setattr(AuditEventService,'record',lambda *_a,**_k: (_ for _ in ()).throw(RuntimeError('audit failed')))
        with pytest.raises(RuntimeError):create_withdrawal(issue.issue_no,body,Response(),db)
    assert db.get(IssueImpactAssessment,body.request_id) is None
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)['assessment']['id']==str(root.request_id)
    create_withdrawal(issue.issue_no,body,Response(),db)
    with pytest.raises(HTTPException):create_assessment(issue.issue_no,data(release,snapshot,request_id=body.request_id),Response(),db)


@pytest.mark.parametrize('change', [dict(reason=' '),dict(correction_reason='\t'),dict(actor_name=' '),dict(decision='NOT_AFFECTED'),dict(evidence_ref='file')])
def test_withdrawal_body_is_strict_and_not_a_technical_judgment(change):
    values=dict(request_id=uuid.uuid4(),release_id=uuid.uuid4(),snapshot_id=uuid.uuid4(),supersedes_id=uuid.uuid4(),
        reason='Reason',correction_reason='Correction',actor_name='Reviewer')
    with pytest.raises(ValidationError):WithdrawalInput(**{**values,**change})
