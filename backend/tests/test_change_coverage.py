import uuid
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from test_impact_assessments import context
from app.models.change import AcceptanceCriterion, ChangePoint, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.acceptance import AcceptanceDvpLink
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, DvpPlan, IssueDvpItem
from app.api.change_coverage import assign_acceptance, change_coverage
from app.services.change_coverage import AssignmentInput, AuditEventService, report_coverage

@pytest.fixture
def coverage_context(context):
    db, issue, release, snapshot, scr = context
    scr.requirement = 'Correct timeout'
    criterion = AcceptanceCriterion(change_request_id=scr.id, criterion_no='AC-1', description='No timeout')
    points = [ChangePoint(change_request_id=scr.id, change_no=f'CP-{n}', title='Change') for n in [1, 2]]
    plan = DvpPlan(change_request_id=scr.id, plan_no='PLAN', title='Plan')
    db.add_all([criterion, *points, plan]); db.flush()
    items = [DvpItem(plan_id=plan.id, item_no=f'DVP-{n}', title='Test', scope='SOFTWARE_TEST', status='COMPLETED') for n in [1, 2]]
    db.add_all(items); db.flush()
    db.add_all([ChangePointDvpItem(change_point_id=points[0].id, dvp_item_id=items[0].id), IssueDvpItem(issue_id=issue.id, dvp_item_id=items[0].id)]); db.commit()
    return db, issue, release, snapshot, scr, criterion, points, items

def assignment(criterion, item, **kwargs):
    values = dict(request_id=uuid.uuid4(), criterion_id=criterion.id, dvp_item_id=item.id, actor_name='Engineer', reason='Timeout verification')
    values.update(kwargs)
    return AssignmentInput(**values)

def test_assignments_and_verification_are_separate(coverage_context):
    db, _, _, _, scr, criterion, _, _ = coverage_context
    result = report_coverage(db, scr.request_no)
    assert result['summary']['acceptance'] == {'total': 1, 'assigned': 0, 'assignment_percent': 0, 'passed': None}
    assert result['summary']['change_points']['assignment_percent'] == 50
    assert result['summary']['issues']['assigned'] == 1
    assert result['change_points'][0]['verification'] == 'CONTEXT_REQUIRED'
    assert result['summary']['dvp']['executed'] is None
    assert result['acceptance_criteria'][0]['id'] == str(criterion.id)

def test_assignment_retry_and_audit(coverage_context):
    db, _, release, _, scr, criterion, _, items = coverage_context
    request = assignment(criterion, items[0]); response = Response()
    first = assign_acceptance(scr.request_no, request, response, db)
    assert response.status_code == 201
    assert assign_acceptance(scr.request_no, request, response, db)['id'] == first['id'] and response.status_code == 200
    assert len(db.scalars(select(AcceptanceDvpLink)).all()) == len(db.scalars(select(AuditEvent)).all()) == 1
    result = report_coverage(db, scr.request_no, release.id)
    assert result['summary']['acceptance']['assigned'] == 1
    assert result['acceptance_criteria'][0]['verification'] == 'PENDING'
    assert result['acceptance_criteria'][0]['assignments'][0]['reason'] == request.reason

@pytest.mark.parametrize('conflict', ['payload', 'pair'])
def test_assignment_conflicts(coverage_context, conflict):
    db, _, _, _, scr, criterion, _, items = coverage_context
    request = assignment(criterion, items[0]); assign_acceptance(scr.request_no, request, Response(), db)
    changes = {'reason': 'Different'} if conflict == 'payload' else {'request_id': uuid.uuid4()}
    with pytest.raises(HTTPException) as error: assign_acceptance(scr.request_no, request.model_copy(update=changes), Response(), db)
    assert error.value.status_code == 409 and len(db.scalars(select(AuditEvent)).all()) == 1

def test_atomic_audit_failure(coverage_context, monkeypatch):
    db, _, _, _, scr, criterion, _, items = coverage_context
    def fail(*args, **kwargs): raise RuntimeError('audit failure')
    monkeypatch.setattr(AuditEventService, 'record', fail)
    with pytest.raises(RuntimeError): assign_acceptance(scr.request_no, assignment(criterion, items[0]), Response(), db)
    assert not db.scalars(select(AcceptanceDvpLink)).all()

@pytest.mark.parametrize('field', ['criterion_id', 'dvp_item_id'])
def test_cross_scr_assignment_rejected(coverage_context, field):
    db, _, _, _, scr, criterion, _, items = coverage_context
    other = SoftwareChangeRequest(request_no='OTHER', title='Other', software_id=scr.software_id, source='INTERNAL', scope='STANDARD', change_type='FIX')
    db.add(other); db.flush()
    ac = AcceptanceCriterion(change_request_id=other.id, criterion_no='OTHER', description='Other')
    plan = DvpPlan(change_request_id=other.id, plan_no='OTHER', title='Other')
    db.add_all([ac, plan]); db.flush()
    item = DvpItem(plan_id=plan.id, item_no='OTHER', title='Other', scope='SOFTWARE_TEST')
    db.add(item); db.commit()
    request = assignment(criterion, items[0], **{field: ac.id if field == 'criterion_id' else item.id})
    with pytest.raises(HTTPException) as error: assign_acceptance(scr.request_no, request, Response(), db)
    assert error.value.status_code == 409 and not db.scalars(select(AcceptanceDvpLink)).all()

def test_exact_context_and_latest_failure_override_pass(coverage_context):
    db, _, release, snapshot, scr, criterion, _, items = coverage_context
    assign_acceptance(scr.request_no, assignment(criterion, items[0]), Response(), db)
    old = ReleaseSnapshot(release_id=release.id, snapshot_no='OLD', snapshot_number=0, content_hash='b'*64)
    other = Release(software_id=release.software_id, release_type='STANDARD', version='2')
    db.add_all([old, other]); db.flush()
    for n, rel, snap, result in [(1, release, snapshot, 'PASS'), (2, release, snapshot, 'FAIL'), (3, release, old, 'PASS'), (4, other, snapshot, 'PASS')]:
        db.add(DvpExecution(dvp_item_id=items[0].id, execution_no=n, release_id=rel.id, snapshot_id=snap.id, result=result))
    db.commit()
    result = report_coverage(db, scr.request_no, release.id)
    assert result['acceptance_criteria'][0]['verification'] == 'FAILED'
    assert result['summary']['dvp'] == {'total': 2, 'executed': 1, 'passed': 0}
    assert report_coverage(db, scr.request_no, release.id, 'OLD')['acceptance_criteria'][0]['verification'] == 'PASSED'

def test_all_assigned_tests_must_pass(coverage_context):
    db, _, release, snapshot, scr, criterion, _, items = coverage_context
    for item in items: assign_acceptance(scr.request_no, assignment(criterion, item), Response(), db)
    db.add(DvpExecution(dvp_item_id=items[0].id, execution_no=1, release_id=release.id, snapshot_id=snapshot.id, result='PASS')); db.commit()
    assert report_coverage(db, scr.request_no, release.id)['acceptance_criteria'][0]['verification'] == 'PENDING'
    db.add(DvpExecution(dvp_item_id=items[1].id, execution_no=1, release_id=release.id, snapshot_id=snapshot.id, result='PASS')); db.commit()
    assert report_coverage(db, scr.request_no, release.id)['summary']['acceptance']['passed'] == 1

def test_missing_data_does_not_report_100_percent(context):
    db, _, _, _, scr = context
    result = report_coverage(db, scr.request_no)
    assert result['summary']['acceptance']['assignment_percent'] is None
    assert {g['code'] for g in result['gaps']} >= {'REQUIREMENT_MISSING', 'CRITERIA_MISSING', 'CHANGE_POINTS_MISSING', 'DVP_PLAN_MISSING'}

def test_latest_frozen_snapshot_and_no_snapshot(coverage_context):
    db, _, release, snapshot, scr, _, _, _ = coverage_context
    db.add(ReleaseSnapshot(release_id=release.id, snapshot_no='DRAFT', snapshot_number=2, content_hash='d'*64, status='DRAFT')); db.commit()
    assert report_coverage(db, scr.request_no, release.id)['snapshot']['id'] == str(snapshot.id)
    other = Release(software_id=release.software_id, release_type='STANDARD', version='EMPTY')
    db.add(other); db.commit()
    result = report_coverage(db, scr.request_no, other.id)
    assert result['summary']['dvp']['passed'] is None and result['change_points'][0]['verification'] == 'NO_FROZEN_SNAPSHOT'

@pytest.mark.parametrize('case,status', [('no_release', 422), ('missing_release', 404), ('wrong_snapshot', 409), ('missing_scr', 404)])
def test_invalid_report_context(coverage_context, case, status):
    db, _, release, _, scr, _, _, _ = coverage_context
    args = dict(request_no=scr.request_no, release_id=release.id, snapshot_no=None, db=db)
    if case == 'no_release': args.update(release_id=None, snapshot_no='SNAP-1')
    if case == 'missing_release': args['release_id'] = uuid.uuid4()
    if case == 'wrong_snapshot': args['snapshot_no'] = 'WRONG'
    if case == 'missing_scr': args['request_no'] = 'MISSING'
    with pytest.raises(HTTPException) as error: change_coverage(**args)
    assert error.value.status_code == status

def test_application_customer_project_filter(coverage_context):
    db, _, release, _, scr, _, _, _ = coverage_context
    customers = [Customer(code=c, name=c) for c in ['A', 'B']]
    db.add_all(customers); db.flush()
    projects = [Project(customer_id=c.id, project_code='P', name='P') for c in customers]
    db.add_all(projects); db.flush()
    apps = [Release(software_id=release.software_id, release_type='APPLICATION', version=str(i)) for i in [1, 2]]
    db.add_all(apps); db.flush()
    for app, customer, project in zip(apps, customers, projects): db.add(ApplicationReleaseDetail(release_id=app.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=release.id))
    scr.customer_id = customers[0].id; scr.project_id = projects[0].id; db.commit()
    assert {r['id'] for r in report_coverage(db, scr.request_no)['candidate_releases']} == {str(release.id), str(apps[0].id)}
    with pytest.raises(HTTPException) as error: change_coverage(scr.request_no, apps[1].id, None, db)
    assert error.value.status_code == 409

def test_duplicate_issue_relations_do_not_inflate_coverage(coverage_context):
    db, issue, _, _, scr, _, _, _ = coverage_context
    db.add(IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type='RELATED')); db.commit()
    assert report_coverage(db, scr.request_no)['summary']['issues']['total'] == 1

@pytest.mark.parametrize('field', ['actor_name', 'reason'])
def test_assignment_blank_input(coverage_context, field):
    _, _, _, _, _, criterion, _, items = coverage_context
    with pytest.raises(ValidationError): assignment(criterion, items[0], **{field: '  '})

def test_foreign_test_links_are_excluded(coverage_context):
    db, _, _, _, scr, _, points, _ = coverage_context
    other = SoftwareChangeRequest(request_no='FOREIGN', title='Other', software_id=scr.software_id, source='INTERNAL', scope='STANDARD', change_type='FIX')
    db.add(other); db.flush()
    plan = DvpPlan(change_request_id=other.id, plan_no='FOREIGN', title='Other')
    db.add(plan); db.flush()
    item = DvpItem(plan_id=plan.id, item_no='FOREIGN', title='Other', scope='SOFTWARE_TEST')
    db.add(item); db.flush()
    db.add(ChangePointDvpItem(change_point_id=points[1].id, dvp_item_id=item.id)); db.commit()
    result = report_coverage(db, scr.request_no)
    assert result['change_points'][1]['verification'] == 'UNASSIGNED'
    assert result['change_points'][1]['excluded_link_count'] == 1
    assert result['summary']['change_points']['assigned'] == 1
    assert any(g['code'] == 'DVP_OUTSIDE_SCR' for g in result['gaps'])

def test_candidate_limit_does_not_prevent_direct_context_selection(coverage_context):
    db, _, release, _, scr, _, _, _ = coverage_context
    for n in range(101): db.add(Release(software_id=release.software_id, release_type='STANDARD', version=f'V{n}'))
    db.commit()
    report = report_coverage(db, scr.request_no, release.id)
    assert report['candidates_truncated'] and len(report['candidate_releases']) == 100
    assert report['release']['id'] == str(release.id)

def test_missing_assignment_target_returns_404(coverage_context):
    db, _, _, _, scr, criterion, _, items = coverage_context
    with pytest.raises(HTTPException) as error:
        assign_acceptance(scr.request_no, assignment(criterion, items[0], dvp_item_id=uuid.uuid4()), Response(), db)
    assert error.value.status_code == 404
