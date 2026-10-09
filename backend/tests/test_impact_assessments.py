import uuid
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import JSON, MetaData, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
import app.models
from app.core.db import Base
from app.models.core import Supplier, SoftwareProduct, Release
from app.models.change import Issue, SoftwareChangeRequest, IssueChangeRequestRelation
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpPlan, DvpItem, IssueDvpItem, DvpExecution
from app.models.impact import IssueImpactAssessment
from app.models.audit import AuditEvent
from app.api.impact import create_assessment, assessment_history, impact_evidence
from app.services.impact_assessment import AssessmentInput, AuditEventService

@pytest.fixture
def context():
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for col in copied.columns:
            if isinstance(col.type, JSONB): col.type = JSON()
    engine = create_engine('sqlite://')
    metadata.create_all(engine)
    with Session(engine) as db:
        supplier = Supplier(code='S', name='Supplier')
        db.add(supplier); db.flush()
        product = SoftwareProduct(supplier_id=supplier.id, code='B', name='BMS')
        db.add(product); db.flush()
        release = Release(software_id=product.id, release_type='STANDARD', version='1', status='RELEASED')
        issue = Issue(issue_no='310', title='Issue', scope='STANDARD', severity='HIGH')
        scr = SoftwareChangeRequest(request_no='SCR-1', title='Fix', source='INTERNAL', scope='STANDARD', change_type='FIX', software_id=product.id)
        db.add_all([release, issue, scr]); db.flush()
        snapshot = ReleaseSnapshot(snapshot_no='SNAP-1', release_id=release.id, snapshot_number=1, content_hash='a'*64, status='FROZEN')
        db.add_all([snapshot, IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type='FIXES')]); db.commit()
        yield db, issue, release, snapshot, scr
    engine.dispose()

def data(release, snapshot, **kwargs):
    values = dict(request_id=uuid.uuid4(), release_id=release.id, snapshot_id=snapshot.id, decision='AFFECTED', reason='Observed on bench', actor_name='Engineer')
    values.update(kwargs)
    return AssessmentInput(**values)

def test_idempotent_write_and_history(context):
    db, issue, release, snapshot, _ = context
    request = data(release, snapshot); response = Response()
    first = create_assessment(issue.issue_no, request, response, db)
    assert response.status_code == 201
    retry = create_assessment(issue.issue_no, request, response, db)
    assert retry['id'] == first['id'] and response.status_code == 200
    assert len(db.scalars(select(IssueImpactAssessment)).all()) == 1
    assert len(db.scalars(select(AuditEvent)).all()) == 1
    history = assessment_history(issue.issue_no, 1, db)
    assert history['items'][0]['snapshot_no'] == snapshot.snapshot_no
    assert history['items'][0]['release_version'] == release.version
    assert not history['truncated']
    assert impact_evidence(issue.issue_no, release.id, db)['assessment']['decision'] == 'AFFECTED'

def test_request_id_payload_conflict(context):
    db, issue, release, snapshot, _ = context
    request = data(release, snapshot)
    create_assessment(issue.issue_no, request, Response(), db)
    with pytest.raises(HTTPException) as error:
        create_assessment(issue.issue_no, request.model_copy(update={'decision': 'NOT_AFFECTED'}), Response(), db)
    assert error.value.status_code == 409
    assert len(db.scalars(select(AuditEvent)).all()) == 1

@pytest.mark.parametrize('case', ['wrong_release', 'draft', 'unlinked'])
def test_invalid_context_rejected(context, case):
    db, issue, release, snapshot, _ = context
    if case == 'wrong_release':
        other = Release(software_id=release.software_id, release_type='STANDARD', version='2', status='DRAFT')
        db.add(other); db.commit(); request = data(other, snapshot)
    elif case == 'draft':
        snapshot.status = 'DRAFT'; db.commit(); request = data(release, snapshot)
    else:
        db.delete(db.scalars(select(IssueChangeRequestRelation)).one()); db.commit(); request = data(release, snapshot)
    with pytest.raises(HTTPException) as error:
        create_assessment(issue.issue_no, request, Response(), db)
    assert error.value.status_code == 409
    assert not db.scalars(select(IssueImpactAssessment)).all()
    assert not db.scalars(select(AuditEvent)).all()

def test_audit_failure_rolls_back_assessment(context, monkeypatch):
    db, issue, release, snapshot, _ = context
    def fail(*args, **kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService, 'record', fail)
    with pytest.raises(RuntimeError): create_assessment(issue.issue_no, data(release, snapshot), Response(), db)
    assert not db.scalars(select(IssueImpactAssessment)).all()

def test_new_snapshot_does_not_inherit_judgment(context):
    db, issue, release, snapshot, _ = context
    create_assessment(issue.issue_no, data(release, snapshot), Response(), db)
    db.add(ReleaseSnapshot(snapshot_no='SNAP-2', release_id=release.id, snapshot_number=2, content_hash='b'*64, status='FROZEN')); db.commit()
    result = impact_evidence(issue.issue_no, release.id, db)
    assert result['snapshot']['snapshot_no'] == 'SNAP-2' and result['assessment'] is None
    assert len(assessment_history(issue.issue_no, 50, db)['items']) == 1

def test_dvp_results_are_exact_snapshot_and_release(context):
    db, issue, release, snapshot, scr = context
    plan = DvpPlan(change_request_id=scr.id, plan_no='P', title='Plan')
    db.add(plan); db.flush()
    item = DvpItem(plan_id=plan.id, item_no='DVP-1', title='Test', scope='STANDARD')
    db.add(item); db.flush(); db.add(IssueDvpItem(issue_id=issue.id, dvp_item_id=item.id))
    old = ReleaseSnapshot(snapshot_no='OLD', release_id=release.id, snapshot_number=0, content_hash='c'*64, status='FROZEN')
    other = Release(software_id=release.software_id, release_type='STANDARD', version='2')
    db.add_all([old, other]); db.flush()
    for number, rel, snap, result in [(1, release, snapshot, 'FAIL'), (2, release, snapshot, 'PASS'), (3, release, old, 'FAIL'), (4, other, snapshot, 'FAIL')]:
        db.add(DvpExecution(dvp_item_id=item.id, execution_no=number, release_id=rel.id, snapshot_id=snap.id, result=result))
    db.commit()
    result = impact_evidence(issue.issue_no, release.id, db)
    assert result['verification'][0]['execution']['execution_no'] == 2
    assert result['verification'][0]['execution']['result'] == 'PASS' and result['assessment'] is None

@pytest.mark.parametrize('field,value', [('reason', '  '), ('actor_name', '\t'), ('decision', 'PASS')])
def test_input_validation(context, field, value):
    _, _, release, snapshot, _ = context
    with pytest.raises(ValidationError): data(release, snapshot, **{field: value})

def test_history_limit_and_missing_issue(context):
    db, issue, release, snapshot, _ = context
    for decision in ['AFFECTED', 'NOT_AFFECTED']: create_assessment(issue.issue_no, data(release, snapshot, decision=decision), Response(), db)
    assert assessment_history(issue.issue_no, 1, db)['truncated']
    with pytest.raises(HTTPException) as error: assessment_history('missing', 1, db)
    assert error.value.status_code == 404

def test_draft_snapshot_does_not_replace_frozen_evidence(context):
    db, issue, release, snapshot, _ = context
    db.add(ReleaseSnapshot(snapshot_no='DRAFT', release_id=release.id, snapshot_number=2, content_hash='d'*64, status='DRAFT')); db.commit()
    assert impact_evidence(issue.issue_no, release.id, db)['snapshot']['id'] == str(snapshot.id)

def test_audit_summary_respects_storage_limit(context):
    db, issue, release, snapshot, _ = context
    issue.issue_no = 'I'*50; release.version = 'V'*100; snapshot.snapshot_no = 'S'*80; db.commit()
    create_assessment(issue.issue_no, data(release, snapshot), Response(), db)
    assert len(db.scalars(select(AuditEvent)).one().summary) == 240


@pytest.mark.parametrize('reference', [None, '  //server/share/原始证据.pdf  '])
def test_original_impact_audit_binds_evidence_reference_without_exposing_it(context, reference):
    import hashlib
    import json
    db, issue, release, snapshot, _ = context
    request = data(release, snapshot, evidence_ref=reference)
    create_assessment(issue.issue_no, request, Response(), db)
    event = db.scalars(select(AuditEvent)).one()
    expected = hashlib.sha256(json.dumps(request.evidence_ref, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    assert event.payload_json['evidence_ref_digest_version'] == 1
    assert event.payload_json['evidence_ref_sha256'] == expected
    assert 'evidence_ref' not in event.payload_json
    original = dict(event.payload_json)
    create_assessment(issue.issue_no, request, Response(), db)
    assert event.payload_json == original
    assert len(db.scalars(select(AuditEvent)).all()) == 1
