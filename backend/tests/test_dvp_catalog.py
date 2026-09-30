import uuid
import pytest
from fastapi import HTTPException
from test_impact_assessments import context
from test_change_coverage import coverage_context
from app.api.dvp_catalog import dvp_catalog, dvp_history, dvp_profile
from app.models.acceptance import AcceptanceDvpLink
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpExecution, TestRelease as RecordedTestRelease


def catalog(db, **kwargs):
    args = dict(scr=None, plan=None, scope=None, status=None, result=None, q=None,
        release_id=None, snapshot_no=None, limit=50, offset=0, db=db)
    args.update(kwargs)
    return dvp_catalog(**args)


def history(db, item, **kwargs):
    args = dict(item_id=item.id, release_id=None, snapshot_no=None, result=None,
        limit=50, before_number=None, db=db)
    args.update(kwargs)
    return dvp_history(**args)


@pytest.fixture
def executed(coverage_context):
    db, issue, release, snapshot, scr, criterion, points, items = coverage_context
    old = ReleaseSnapshot(release_id=release.id, snapshot_no='OLD', snapshot_number=0, content_hash='c'*64)
    db.add(old); db.flush()
    db.add_all([DvpExecution(dvp_item_id=items[0].id, execution_no=1, release_id=release.id, snapshot_id=old.id, result='FAIL'),
        DvpExecution(dvp_item_id=items[0].id, execution_no=2, release_id=release.id, snapshot_id=snapshot.id, result='PASS')]); db.commit()
    return coverage_context


def test_summary_and_retests_use_context_not_execution_number(executed):
    db, _, release, snapshot, _, _, _, items = executed
    all_contexts = catalog(db)
    assert all_contexts['total'] == 2
    assert all_contexts['summary'] == {'executed': 1, 'not_executed': 1, 'retested': 1, 'recorded_latest_results': {'PASS': 1}}
    exact = catalog(db, release_id=release.id)
    assert exact['summary']['retested'] == 0  # #2 is first execution on this snapshot
    assert exact['items'][0]['latest_execution']['snapshot_no'] == snapshot.snapshot_no
    old = catalog(db, release_id=release.id, snapshot_no='OLD')
    assert old['summary']['recorded_latest_results'] == {'FAIL': 1}
    assert old['items'][0]['latest_execution']['execution_no'] == 1
    assert old['items'][1]['latest_execution'] is None


@pytest.mark.parametrize('filters,total', [({'scr': 'SCR-1'}, 2), ({'plan': 'PLAN'}, 2),
    ({'scope': 'SOFTWARE_TEST'}, 2), ({'status': 'COMPLETED'}, 2), ({'result': 'PASS'}, 1),
    ({'result': 'NOT_EXECUTED'}, 1), ({'result': 'FAIL'}, 0), ({'q': 'DVP-1'}, 1), ({'scr': 'MISSING'}, 0)])
def test_catalog_filters(executed, filters, total):
    db, *_ = executed
    assert catalog(db, **filters)['total'] == total


def test_search_wildcards_are_literal(executed):
    db, *_, items = executed
    items[0].title = 'Test%_alpha'; db.commit()
    assert catalog(db, q='%_')['total'] == 1
    assert catalog(db, q='%missing')['total'] == 0


def test_catalog_paging_summary_is_global(executed):
    db, *_ = executed
    first = catalog(db, limit=1)
    second = catalog(db, limit=1, offset=first['next_offset'])
    assert first['total'] == second['total'] == 2
    assert first['summary'] == second['summary']
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert second['next_offset'] is None
    assert catalog(db, offset=2)['items'] == []


def test_history_cursor_and_exact_snapshot_filter(executed):
    db, _, release, snapshot, _, _, _, items = executed
    first = history(db, items[0], limit=1)
    assert first['items'][0]['execution_no'] == 2 and first['total'] == 2
    second = history(db, items[0], limit=1, before_number=first['next_before_number'])
    assert second['items'][0]['execution_no'] == 1 and second['total'] == 2
    assert second['next_before_number'] is None
    assert history(db, items[0], release_id=release.id)['items'][0]['snapshot_no'] == snapshot.snapshot_no
    assert history(db, items[0], release_id=release.id, snapshot_no='OLD', result='PASS')['total'] == 0
    assert history(db, items[1])['items'] == []


def test_later_fail_overrides_pass_and_other_release_is_isolated(executed):
    db, _, release, snapshot, _, _, _, items = executed
    other = Release(software_id=release.software_id, release_type='STANDARD', version='2')
    db.add(other); db.flush()
    other_snap = ReleaseSnapshot(release_id=other.id, snapshot_no='OTHER', snapshot_number=1, content_hash='d'*64)
    db.add(other_snap); db.flush()
    db.add_all([DvpExecution(dvp_item_id=items[0].id, execution_no=3, release_id=release.id, snapshot_id=snapshot.id, result='FAIL'),
        DvpExecution(dvp_item_id=items[0].id, execution_no=4, release_id=other.id, snapshot_id=other_snap.id, result='PASS')]); db.commit()
    result = catalog(db, release_id=release.id)
    assert result['summary']['recorded_latest_results'] == {'FAIL': 1}
    assert result['summary']['retested'] == 1
    assert result['items'][0]['latest_execution']['execution_no'] == 3


def test_context_mismatch_is_flagged(executed):
    db, _, release, snapshot, _, _, _, items = executed
    old = history(db, items[0])['items'][1]
    test = RecordedTestRelease(test_release_no='WRONG', release_id=release.id,
        snapshot_id=uuid.UUID(old['snapshot_id']), purpose_scope='SOFTWARE_TEST')
    db.add(test); db.flush()
    db.add(DvpExecution(dvp_item_id=items[0].id, execution_no=3, release_id=release.id,
        snapshot_id=snapshot.id, test_release_id=test.id, result='PASS')); db.commit()
    assert catalog(db)['items'][0]['latest_execution']['context_consistent'] is False
    assert history(db, items[0])['items'][0]['context_consistent'] is False


def test_new_snapshot_does_not_reuse_old_results(executed):
    db, _, release, _, _, _, _, _ = executed
    db.add(ReleaseSnapshot(release_id=release.id, snapshot_no='NEW', snapshot_number=2, content_hash='e'*64)); db.commit()
    assert catalog(db, release_id=release.id)['summary']['executed'] == 0


def test_release_without_frozen_snapshot_does_not_fall_back(executed):
    db, _, release, _, _, _, _, items = executed
    empty = Release(software_id=release.software_id, release_type='STANDARD', version='EMPTY')
    db.add(empty); db.commit()
    assert catalog(db, release_id=empty.id)['summary']['executed'] == 0
    assert history(db, items[0], release_id=empty.id)['total'] == 0


@pytest.mark.parametrize('filters,status', [({'snapshot_no': 'OLD'}, 422),
    ({'release_id': uuid.uuid4()}, 404), ({'snapshot_no': 'WRONG'}, 409)])
def test_invalid_context(executed, filters, status):
    db, _, release, _, _, _, _, _ = executed
    if status == 409: filters = {**filters, 'release_id': release.id}
    with pytest.raises(HTTPException) as error: catalog(db, **filters)
    assert error.value.status_code == status


def test_profile_reverse_links_and_missing_item(executed):
    db, issue, _, _, _, criterion, points, items = executed
    db.add(AcceptanceDvpLink(id=uuid.uuid4(), criterion_id=criterion.id, dvp_item_id=items[0].id,
        actor_name='Engineer', reason='Verification')); db.commit()
    profile = dvp_profile(items[0].id, db)
    assert profile['linked_acceptance'][0]['criterion_no'] == criterion.criterion_no
    assert profile['linked_change_points'][0]['change_no'] == points[0].change_no
    assert profile['linked_issues'][0]['issue_no'] == issue.issue_no
    assert profile['plan']['change_request_no'] == 'SCR-1'
    with pytest.raises(HTTPException) as error: dvp_profile(uuid.uuid4(), db)
    assert error.value.status_code == 404


def test_application_scope_filters_customer_project(executed):
    db, _, release, _, scr, _, _, _ = executed
    customer = Customer(code='A', name='A'); db.add(customer); db.flush()
    project = Project(customer_id=customer.id, project_code='P', name='P'); db.add(project); db.flush()
    app = Release(software_id=release.software_id, release_type='APPLICATION', version='APP'); db.add(app); db.flush()
    db.add(ApplicationReleaseDetail(release_id=app.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=release.id))
    scr.project_id = uuid.uuid4(); db.commit()
    assert catalog(db, release_id=app.id)['total'] == 0
    scr.project_id = project.id; db.commit()
    assert catalog(db, release_id=app.id)['total'] == 2
