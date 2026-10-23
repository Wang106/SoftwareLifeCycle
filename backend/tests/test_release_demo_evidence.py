from sqlalchemy import select
from app.seed_release_evidence import seed_release_evidence, key, VERSIONS
from app.models.core import Release
from app.models.approval import ReleaseDecision, ApprovalRequest
from app.models.snapshot import ReleaseSnapshot
from app.api.dashboard import _readiness_for_release
from test_impact_assessments import context
from test_release_demo_seed import rows as original_rows
from app.models.testing import DvpExecution
from app.api.release_demo import evidence

def rows(db):
    result = original_rows(db)
    for model in (ReleaseDecision, DvpExecution):
        result[model] = [tuple(getattr(x,c.name) for c in model.__table__.columns) for x in db.scalars(select(model).order_by(model.id))]
    return result


def verify(db):
    for i, version in enumerate(VERSIONS):
        release=db.get(Release,key(version)); ready=_readiness_for_release(release,db,bounded=True)
        assert ready['coverage']['required_dvp_total']==3
        assert ready['coverage']['change_points_total']==1 and ready['coverage']['issues_total']==1
        assert ready['coverage']['change_coverage']==100 and ready['coverage']['issue_verification_coverage']==100
        decision=db.get(ReleaseDecision,key(version+'-decision'))
        approval=db.get(ApprovalRequest,key(version+'-approval'))
        assert approval.status=='APPROVED' and approval.snapshot_id==decision.snapshot_id
        assert ready['coverage']['snapshot_id']==str(decision.snapshot_id)
        if i==2:
            assert ready['overall']=='NOT_READY' and not ready['approval_eligible']
            assert ready['coverage']['current_snapshot_executed']==0 and not ready['coverage']['snapshot_match']
            assert decision.decision=='HOLD' and decision.readiness_status=='NOT_READY'
            assert db.get(ReleaseSnapshot,key(version+'-snapshot-1')).content_hash==db.get(ReleaseSnapshot,decision.snapshot_id).content_hash
        else:
            assert ready['overall']=='READY' and ready['coverage']['current_snapshot_passed']==3
            assert all(r['effective']=='PASS' for r in ready['rules'])
            assert decision.decision=='RELEASE' and decision.readiness_status=='READY'


def test_calculated_positive_and_blocked_evidence(context):
    db=context[0]; seed_release_evidence(db); db.commit(); verify(db)


def test_repeat_preserves_old_and_new_history(context):
    db=context[0]; old=rows(db); seed_release_evidence(db); db.commit(); first=rows(db)
    seed_release_evidence(db); db.commit(); assert rows(db)==first
    for model,records in old.items(): assert all(r in first[model] for r in records)


def test_caller_rollback_removes_whole_evidence_family(context):
    db=context[0]; seed_release_evidence(db); db.rollback()
    assert db.get(Release,key(VERSIONS[0])) is None
    seed_release_evidence(db); db.commit(); verify(db)


def test_evidence_read_empty_without_installation(context):
    assert evidence(context[0]) == {'sample_only': True, 'initialized': False, 'items': []}


def test_evidence_read_distinguishes_approval_and_decision(context):
    db=context[0]; seed_release_evidence(db); db.commit()
    result=evidence(db)
    assert result['initialized'] and len(result['items'])==3
    assert [x['current_release_confirmed'] for x in result['items']]==[True,True,False]
    assert [x['snapshot']['status'] for x in result['items']]==['FROZEN','FROZEN','FROZEN']
    blocked=result['items'][2]
    assert blocked['approval']['status']=='APPROVED'
    assert blocked['decision']['decision']=='HOLD'
    assert blocked['readiness']['coverage']['current_snapshot_executed']==0


def test_new_snapshot_does_not_reuse_old_release_decision(context):
    db=context[0]; seed_release_evidence(db); db.commit()
    db.add(ReleaseSnapshot(id=key('later'), snapshot_no='SNAP-DEMO-LATER',release_id=key(VERSIONS[0]),
        snapshot_number=2,status='FROZEN',content_hash='a'*64))
    db.commit()
    row=evidence(db)['items'][0]
    assert not row['current_release_confirmed']
    assert not row['decision']['current_evidence_bound']
    assert not row['approval']['current_snapshot_bound']
    assert row['decision']['decision']=='RELEASE'


def test_family_scope_never_reads_foreign_release(context):
    db=context[0]; seed_release_evidence(db); db.commit()
    db.get(Release,key(VERSIONS[0])).software_id=context[2].software_id
    db.commit()
    result=evidence(db)
    assert not result['initialized'] and len(result['items'])==2


def test_read_only_api_and_existing_passport_agree():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.db import get_db
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.models import Base
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    from sqlalchemy import MetaData, JSON
    from sqlalchemy.dialects.postgresql import JSONB
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        copied=table.to_metadata(metadata)
        for col in copied.columns:
            if isinstance(col.type,JSONB): col.type=JSON()
    metadata.create_all(engine)
    db=Session(engine); seed_release_evidence(db); db.commit()
    app.dependency_overrides[get_db]=lambda: db
    try:
        with TestClient(app) as client:
            response=client.get('/api/v1/demo/release-evidence')
            assert response.status_code==200
            for row in response.json()['items'][1:]:
                assert row['snapshot']['status']=='FROZEN'
                passport=client.get('/api/v1/releases/application/id/'+row['release_id']+'/passport/summary')
                assert passport.status_code==200
                data=passport.json()
                assert data['selection']['snapshot_id']==row['snapshot']['id']
                assert data['selection']['decision_id']==str(key(row['version']+'-decision'))
                assert data['profile']['base_release']['id']==str(key(VERSIONS[0]))
            assert not any(getattr(route,'path',None)=='/api/v1/demo/release-evidence' and 'POST' in getattr(route,'methods',set()) for route in app.routes)
    finally:
        app.dependency_overrides.clear()
        db.close(); engine.dispose()
