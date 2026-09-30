import uuid
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from test_impact_assessments import context
from test_change_coverage import coverage_context
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpExecution, TestRelease as RecordedVersion
from app.api.testing_releases import create_test_release, test_catalog as catalog_route, test_detail as detail_route, test_executions as records_route
from app.services.testing_release import TestReleaseInput as DraftInput, AuditEventService


def draft(release, snapshot, **kwargs):
    values = dict(request_id=uuid.uuid4(), test_release_no='TR-NEW', release_id=release.id, snapshot_id=snapshot.id,
        purpose_scope='SOFTWARE_TEST', actor_name='Engineer', reason='Verification draft')
    values.update(kwargs)
    return DraftInput(**values)


def catalog(db, **kwargs):
    args = dict(status=None, scope=None, release_id=None, q=None, limit=50, offset=0, db=db)
    args.update(kwargs)
    return catalog_route(**args)


def records(db, no, **kwargs):
    args = dict(test_release_no=no, limit=50, offset=0, db=db)
    args.update(kwargs)
    return records_route(**args)


def test_create_draft_is_idempotent_and_atomic(context):
    db, _, release, snapshot, _ = context
    data = draft(release, snapshot); response = Response()
    first = create_test_release(data, response, db)
    assert first['status'] == 'DRAFT' and response.status_code == 201
    assert create_test_release(data, response, db) == first and response.status_code == 200
    assert len(db.scalars(select(RecordedVersion)).all()) == len(db.scalars(select(AuditEvent)).all()) == 1
    event = db.scalars(select(AuditEvent)).one()
    assert event.entity_type == 'TEST_RELEASE' and event.payload_json['snapshot_no'] == snapshot.snapshot_no


@pytest.mark.parametrize('field,value', [('reason','changed'), ('actor_name','Other'), ('purpose_scope','BATTERY_TEST')])
def test_idempotency_conflict(context, field, value):
    db, _, release, snapshot, _ = context
    data = draft(release, snapshot); create_test_release(data, Response(), db)
    with pytest.raises(HTTPException) as error:
        create_test_release(data.model_copy(update={field:value}), Response(), db)
    assert error.value.status_code == 409 and len(db.scalars(select(AuditEvent)).all()) == 1


def test_duplicate_number_and_legacy_id_do_not_overwrite(context):
    db, _, release, snapshot, _ = context
    existing = RecordedVersion(id=uuid.uuid4(), test_release_no='TR-NEW', release_id=release.id, snapshot_id=snapshot.id, purpose_scope='SOFTWARE_TEST', status='ACTIVE')
    db.add(existing); db.commit()
    for request_id in [uuid.uuid4(), existing.id]:
        with pytest.raises(HTTPException) as error: create_test_release(draft(release, snapshot, request_id=request_id), Response(), db)
        assert error.value.status_code == 409
    assert db.get(RecordedVersion, existing.id).status == 'ACTIVE' and not db.scalars(select(AuditEvent)).all()


@pytest.mark.parametrize('case,status', [('draft_snapshot',409),('wrong_release',409),('missing_snapshot',404),('missing_release',404)])
def test_invalid_binding_rejected(context, case, status):
    db, _, release, snapshot, _ = context
    args = {}
    if case == 'draft_snapshot': snapshot.status='DRAFT'; db.commit()
    if case == 'wrong_release':
        other = Release(software_id=release.software_id, release_type='STANDARD', version='Other')
        db.add(other); db.commit(); args['release_id']=other.id
    if case == 'missing_snapshot': args['snapshot_id']=uuid.uuid4()
    if case == 'missing_release': args['release_id']=uuid.uuid4()
    with pytest.raises(HTTPException) as error: create_test_release(draft(release,snapshot,**args),Response(),db)
    assert error.value.status_code==status and not db.scalars(select(RecordedVersion)).all()


def test_audit_failure_rolls_back_draft(context, monkeypatch):
    db, _, release, snapshot, _ = context
    def fail(*args,**kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService,'record',fail)
    with pytest.raises(RuntimeError): create_test_release(draft(release,snapshot),Response(),db)
    assert not db.scalars(select(RecordedVersion)).all()


@pytest.mark.parametrize('field,value',[('actor_name',' '),('reason','\t'),('test_release_no',' '),('purpose_scope','PRODUCTION'),('status','ACTIVE')])
def test_create_input_validation(context, field, value):
    _, _, release, snapshot, _ = context
    with pytest.raises(ValidationError): draft(release,snapshot,**{field:value})


@pytest.fixture
def versions(coverage_context):
    db, issue, release, snapshot, scr, criterion, points, items = coverage_context
    old = ReleaseSnapshot(release_id=release.id, snapshot_no='OLD', snapshot_number=0, content_hash='b'*64)
    db.add(old); db.flush()
    tests = [RecordedVersion(test_release_no='TR-OLD',release_id=release.id,snapshot_id=old.id,purpose_scope='SOFTWARE_TEST',status='SUPERSEDED'),
        RecordedVersion(test_release_no='TR-NEW',release_id=release.id,snapshot_id=snapshot.id,purpose_scope='BATTERY_TEST',status='ACTIVE')]
    db.add_all(tests); db.flush()
    for n, snap, test, result in [(1,old,tests[0],'FAIL'),(2,snapshot,tests[1],'PASS'),(3,snapshot,tests[1],'FAIL'),(4,old,tests[1],'PASS')]:
        db.add(DvpExecution(dvp_item_id=items[0].id,execution_no=n,release_id=release.id,snapshot_id=snap.id,test_release_id=test.id,result=result))
    db.add(DvpExecution(dvp_item_id=items[1].id,execution_no=1,release_id=release.id,snapshot_id=snapshot.id,result='PASS'))
    for snap, filename in [(old,'old.hex'),(snapshot,'new.hex')]:
        db.add(SnapshotArtifact(snapshot_id=snap.id,source_artifact_id=uuid.uuid4(),component_code='APP',component_version='1',filename=filename,
            artifact_type='HEX',sha256='c'*64,classification='INTERNAL',distribution_level='INTERNAL_ONLY',ai_access_policy='DENY',storage_reference='/sample'))
    db.commit()
    return db, release, snapshot, old, tests


def test_exact_pinned_manifest_and_execution_summary(versions):
    db, _, _, _, tests = versions
    old = detail_route(tests[0].test_release_no,db)
    assert old['snapshot']['snapshot_no']=='OLD' and old['artifacts'][0]['filename']=='old.hex'
    assert not old['is_latest_frozen_snapshot']
    current = detail_route(tests[1].test_release_no,db)
    assert current['artifacts'][0]['filename']=='new.hex'
    assert current['execution_summary']=={'records':3,'matching_records':2,'mismatched_records':1,'executed_items':1,'latest_result_counts':{'FAIL':1}}
    # Unassigned PASS and mismatched PASS cannot change this test release's latest outcome.
    assert current['context_consistent']


@pytest.mark.parametrize('filters,total',[({'status':'ACTIVE'},1),({'scope':'SOFTWARE_TEST'},1),({'q':'OLD'},1),({'q':'absent'},0)])
def test_catalog_filters(versions,filters,total):
    db,*_ = versions
    assert catalog(db,**filters)['total']==total


def test_catalog_and_execution_pagination(versions):
    db,release,_,_,tests = versions
    first=catalog(db,limit=1)
    second=catalog(db,limit=1,offset=first['next_offset'])
    assert first['total']==second['total']==2 and first['status_counts']==second['status_counts']
    assert first['items'][0]['id']!=second['items'][0]['id'] and second['next_offset'] is None
    assert catalog(db,release_id=release.id)['total']==2
    page=records(db,tests[1].test_release_no,limit=1)
    following=records(db,tests[1].test_release_no,limit=1,offset=page['next_offset'])
    assert page['total']==following['total']==3 and page['items'][0]['id']!=following['items'][0]['id']
    all_rows=records(db,tests[1].test_release_no)['items']
    assert sum(not r['matches_test_context'] for r in all_rows)==1


def test_empty_draft_and_missing_record(context):
    db,_,release,snapshot,_=context
    create_test_release(draft(release,snapshot),Response(),db)
    assert detail_route('TR-NEW',db)['execution_summary']['records']==0
    assert records(db,'TR-NEW')['items']==[]
    with pytest.raises(HTTPException) as error: detail_route('MISSING',db)
    assert error.value.status_code==404


def test_literal_search_wildcards(versions):
    db,*_,tests=versions
    tests[0].test_release_no='TR-%_'; db.commit()
    assert catalog(db,q='%_')['total']==1
    assert catalog(db,q='%missing')['total']==0
