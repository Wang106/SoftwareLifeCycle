"""Preserve coverage semantics without loading child rows; exercise migrated PG."""
import uuid
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.models.audit import AuditEvent
from app.models.change import ChangePoint, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, DvpPlan, IssueDvpItem
from app.services.traceability import CoverageResult, TraceabilityService


def seed(db, release, snapshot, scr, issue=None, size=3):
    plan = DvpPlan(change_request_id=scr.id, plan_no=f'P-{uuid.uuid4()}', title='Plan')
    db.add(plan); db.flush()
    items = [DvpItem(plan_id=plan.id, item_no=f'DVP-{n}', title='Test', scope='SOFTWARE_TEST') for n in range(size)]
    points = [ChangePoint(change_request_id=scr.id, change_no=f'CP-{n}', title='Point', description='private'*1000) for n in range(size)]
    db.add_all(items + points); db.flush()
    for point, item in zip(points, items):
        db.add(ChangePointDvpItem(change_point_id=point.id, dvp_item_id=item.id))
        if issue: db.add(IssueDvpItem(issue_id=issue.id, dvp_item_id=item.id))
        for number, result in [(1, 'PASS'), (2, 'FAIL')]:
            db.add(DvpExecution(dvp_item_id=item.id, execution_no=number, release_id=release.id, snapshot_id=snapshot.id, result=result, actual_result='private'*1000))
    db.commit()
    return items, points


def test_distinct_union_and_any_pass_not_latest(context):
    db, issue, release, snapshot, scr = context
    items, points = seed(db, release, snapshot, scr, issue)
    db.add(IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type='RELATED'))
    db.add(ChangePointDvpItem(change_point_id=points[0].id, dvp_item_id=items[1].id)); db.commit()
    assert TraceabilityService(db).release_coverage(release.id).as_dict() == CoverageResult(str(snapshot.id), snapshot.snapshot_no, 3, 3, 1, 1, 3, 3, 3, True).as_dict()


@pytest.mark.parametrize('case', ['old', 'new_empty', 'foreign', 'missing', 'no_snapshot', 'missing_release'])
def test_exact_snapshot_and_empty_contract(context, case):
    db, issue, release, snapshot, scr = context
    seed(db, release, snapshot, scr, issue)
    rid, selected = release.id, None
    if case in ['old', 'new_empty']:
        db.add(ReleaseSnapshot(release_id=release.id, snapshot_no='NEW', snapshot_number=2, content_hash='b'*64))
        if case == 'old': selected = snapshot.id
    elif case == 'foreign':
        other = Release(software_id=release.software_id, release_type='STANDARD', version='2'); db.add(other); db.flush()
        foreign = ReleaseSnapshot(release_id=other.id, snapshot_no='FOREIGN', snapshot_number=1, content_hash='c'*64); db.add(foreign); db.flush(); selected = foreign.id
    elif case == 'missing': selected = uuid.uuid4()
    elif case == 'no_snapshot': db.delete(snapshot)
    else: rid = uuid.uuid4()
    db.commit()
    result = TraceabilityService(db).release_coverage(rid, selected)
    assert result.current_snapshot_executed == result.current_snapshot_passed == (3 if case == 'old' else 0)
    assert result.snapshot_match == (case == 'old')
    if case in ['foreign', 'missing', 'no_snapshot', 'missing_release']: assert result.snapshot_id is None
    if case == 'missing_release': assert result.as_dict() == CoverageResult(None, None, 0, 0, 0, 0, 0, 0, 0, False).as_dict()


def test_other_release_and_nonrequired_items_do_not_count(context):
    db, issue, release, snapshot, scr = context
    items, _ = seed(db, release, snapshot, scr)
    db.query(DvpExecution).delete()
    other = Release(software_id=release.software_id, release_type='STANDARD', version='2'); db.add(other); db.flush()
    db.add(DvpExecution(dvp_item_id=items[0].id, execution_no=3, release_id=other.id, snapshot_id=snapshot.id, result='PASS'))
    unbound = DvpItem(plan_id=items[0].plan_id, item_no='UNBOUND', title='Not required', scope='SOFTWARE_TEST'); db.add(unbound); db.flush()
    db.add(DvpExecution(dvp_item_id=unbound.id, execution_no=1, release_id=release.id, snapshot_id=snapshot.id, result='PASS')); db.commit()
    result = TraceabilityService(db).release_coverage(release.id)
    assert result.required_dvp_total == 3 and result.current_snapshot_executed == 0 and not result.snapshot_match


@pytest.mark.parametrize('kind', ['STANDARD', 'APPLICATION', 'APPLICATION_WITH_DETAIL'])
def test_software_project_scope_and_legacy_missing_detail(context, kind):
    db, issue, release, snapshot, scr = context
    project, sibling = uuid.uuid4(), uuid.uuid4()
    release.release_type = 'STANDARD' if kind == 'STANDARD' else 'APPLICATION'
    if kind == 'APPLICATION_WITH_DETAIL': db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=uuid.uuid4(), project_id=project, standard_base_release_id=uuid.uuid4()))
    for n, (software, project_id) in enumerate([(release.software_id, None), (release.software_id, project), (release.software_id, sibling), (uuid.uuid4(), project)]):
        request = SoftwareChangeRequest(request_no=f'S-{n}', title='Scope', source='INTERNAL', scope='STANDARD', change_type='FIX', software_id=software, project_id=project_id)
        db.add(request); db.flush(); db.add(ChangePoint(change_request_id=request.id, change_no=f'C-{n}', title='Point'))
    db.commit(); result = TraceabilityService(db).release_coverage(release.id)
    assert result.change_points_total == (2 if kind == 'APPLICATION_WITH_DETAIL' else 3)
    assert result.change_points_covered == result.required_dvp_total == 0
    assert result.as_dict()['dvp_execution_coverage'] == 100


def test_recorded_bindings_survive_missing_metadata(context):
    # Legacy orphan fixture is SQLite-only; PostgreSQL enforces foreign keys.
    db, issue, release, snapshot, scr = context
    item_id, issue_id = uuid.uuid4(), uuid.uuid4()
    db.add(IssueChangeRequestRelation(issue_id=issue_id, change_request_id=scr.id, relation_type='RELATED'))
    db.add(IssueDvpItem(issue_id=issue_id, dvp_item_id=item_id))
    db.add(DvpExecution(dvp_item_id=item_id, execution_no=1, release_id=release.id, snapshot_id=snapshot.id, result='PASS')); db.commit()
    result = TraceabilityService(db).release_coverage(release.id)
    assert (result.issues_total, result.issues_covered, result.required_dvp_total, result.current_snapshot_passed) == (2, 1, 1, 1)


def test_growth_fixed_queries_no_child_rows_or_private_payload(context):
    db, issue, release, snapshot, scr = context
    rid, sid, scrid = release.id, snapshot.id, scr.id
    calls = []
    def capture(_conn, _cursor, statement, *_): calls.append(statement.lower())
    def read():
        db.expunge_all(); calls.clear(); result = TraceabilityService(db).release_coverage(rid)
        assert not any(isinstance(row, (ChangePoint, DvpExecution, SoftwareChangeRequest, IssueDvpItem)) for row in db.identity_map.values())
        return result, list(calls)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        small, small_sql = read()
        seed(db, db.get(Release, rid), db.get(ReleaseSnapshot, sid), db.get(SoftwareChangeRequest, scrid), size=120)
        grown, grown_sql = read()
    finally: event.remove(db.bind, 'before_cursor_execute', capture)
    assert small.change_points_total == 0 and grown.change_points_total == grown.current_snapshot_executed == 120
    assert len(small_sql) == len(grown_sql) == 3 and 'limit' in grown_sql[1]
    assert not any('actual_result' in sql or 'description' in sql or 'requirement' in sql for sql in grown_sql)
    assert len(small_sql[2]) == len(grown_sql[2])


def test_real_migrated_postgresql_aggregates_and_readonly(pg):
    engine, ids = pg
    with Session(engine) as db:
        release = db.get(Release, ids['release'])
        snapshot = db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id))
        scr = SoftwareChangeRequest(request_no='PG-COVERAGE', title='Coverage', source='INTERNAL', scope='STANDARD', change_type='FIX', software_id=release.software_id)
        db.add(scr); db.flush(); seed(db, release, snapshot, scr, size=120)
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        result = TraceabilityService(db).release_coverage(release.id, snapshot.id)
        assert (result.change_points_total, result.change_points_covered, result.required_dvp_total, result.current_snapshot_executed, result.current_snapshot_passed) == (120, 120, 120, 120, 120)
        assert result.snapshot_match and db.scalar(select(func.count()).select_from(AuditEvent)) == before
