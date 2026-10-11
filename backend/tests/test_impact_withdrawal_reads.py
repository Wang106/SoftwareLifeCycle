"""Shared withdrawal reads, snapshot isolation and unchanged public guards."""
import uuid
from fastapi import Response
from fastapi.testclient import TestClient
from test_impact_assessments import context, data
from test_impact_withdrawal import withdrawal
from app.api.impact import create_assessment, create_withdrawal, _contexts
from app.api.issue_views import Pages, SnapshotSelection, assessments_page, evidence_summary, candidates_page
from app.core.config import settings
from app.models.snapshot import ReleaseSnapshot
from app.models.impact import IssueImpactAssessment
from app.main import app


def test_selected_snapshot_and_compatibility_context_share_terminal(context):
    db,issue,release,snapshot,_=context
    original=data(release,snapshot);create_assessment(issue.issue_no,original,Response(),db)
    second=ReleaseSnapshot(release_id=release.id,snapshot_no='OTHER',snapshot_number=2,status='FROZEN',content_hash='b'*64)
    db.add(second);db.commit()
    other=data(release,second);create_assessment(issue.issue_no,other,Response(),db)
    body=withdrawal(release,snapshot,original.request_id);create_withdrawal(issue.issue_no,body,Response(),db)
    result=evidence_summary(issue.issue_no,release.id,SnapshotSelection(snapshot_id=snapshot.id),db)
    assert result['assessment'] is None and result['withdrawal']['id']==str(body.request_id)
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(snapshot_id=second.id),db)['assessment']['id']==str(other.request_id)
    assert _contexts(db,issue.id,[release])[release.id]['assessment']['id']==str(other.request_id)
    body2=withdrawal(release,second,other.request_id);create_withdrawal(issue.issue_no,body2,Response(),db)
    compatibility=_contexts(db,issue.id,[release])[release.id]
    assert compatibility['assessment'] is None and compatibility['context_state']=='WITHDRAWN'
    assert compatibility['terminal_event_id']==str(body2.request_id)


def test_unassessed_has_no_fabricated_action_and_legacy_nulls_remain_readable(context):
    db,issue,release,snapshot,_=context
    candidate=candidates_page(issue.issue_no,Pages(issue_id=issue.id),db)['items'][0]
    assert candidate['context_state']=='UNASSESSED' and candidate['terminal_action'] is None
    legacy=IssueImpactAssessment(id=uuid.uuid4(),issue_id=issue.id,release_id=release.id,snapshot_id=snapshot.id,
        decision='AFFECTED',reason='Original legacy',actor_name='Original actor')
    db.add(legacy);db.commit()
    result=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)
    assert result['assessment']['action']=='ASSESS' and result['assessment']['context_seq'] is None
    assert result['assessment']['reason']=='Original legacy'
    create_withdrawal(issue.issue_no,withdrawal(release,snapshot,legacy.id),Response(),db)
    page=assessments_page(issue.issue_no,Pages(issue_id=issue.id,limit=1,offset=1),db)
    assert page['items'][0]['id']==str(legacy.id) and page['items'][0]['is_context_terminal'] is False


def test_public_read_only_and_oidc_block_withdrawal_before_body_and_database(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(settings,'read_only_mode',True)
        response=client.post('/api/v1/issues/TEST/impact-withdrawals',json={})
        assert response.status_code==403 and response.json()['detail']=='read_only_mode'
        monkeypatch.setattr(settings,'read_only_mode',False);monkeypatch.setattr(settings,'auth_mode','oidc')
        assert client.post('/api/v1/issues/TEST/impact-withdrawals',json={}).status_code==401
