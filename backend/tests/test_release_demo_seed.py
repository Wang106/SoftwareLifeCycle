import pytest
from sqlalchemy import select, func
from app.seed_release_demo import seed_release_demo, SSR_ROLES, ASR_ROLES, key
from app.models.core import Release, ReleaseComponent, Artifact, ApplicationReleaseDetail, StandardReleaseDetail
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.audit import AuditEvent
from app.services.approval import ApprovalService, ApprovalError
from test_impact_assessments import context


def verify(db):
    releases = db.scalars(select(Release).where(Release.software_id == key('product'))).all()
    assert len(releases) == 4
    for release in releases:
        approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.target_id == release.id))
        steps = db.scalars(select(ApprovalStep).where(ApprovalStep.approval_request_id == approval.id).order_by(ApprovalStep.step_order)).all()
        assert tuple(s.role_name for s in steps) == (SSR_ROLES if release.release_type == 'STANDARD' else ASR_ROLES)
        assert [s.step_order for s in steps] == [1,2,3,4]
        snapshot = db.get(ReleaseSnapshot, approval.snapshot_id)
        assert snapshot.release_id == release.id and snapshot.status == 'FROZEN'
        assert db.scalar(select(func.count()).select_from(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot.id)) == 3
        if release.release_type == 'APPLICATION':
            assert db.get(ApplicationReleaseDetail, release.id).standard_base_release_id == key('DEMO-SSR-1.1')
            for c in db.scalars(select(ReleaseComponent).where(ReleaseComponent.release_id == release.id)):
                base = db.get(ReleaseComponent, c.base_component_id)
                assert base.release_id == key('DEMO-SSR-1.1')
                if c.delta_type == 'UNCHANGED':
                    a = db.scalar(select(Artifact).where(Artifact.release_component_id == c.id))
                    b = db.scalar(select(Artifact).where(Artifact.release_component_id == base.id))
                    assert a.sha256 == b.sha256 and c.version == base.version
    assert db.get(StandardReleaseDetail, key('DEMO-SSR-1.1')).previous_release_id == key('DEMO-SSR-1.0')
    assert not db.scalar(select(ReleaseDecision).where(ReleaseDecision.release_id.in_([r.id for r in releases])))


def rows(db):
    return {m: [tuple(getattr(x,c.name) for c in m.__table__.columns) for x in db.scalars(select(m).order_by(m.id))] for m in (Release, ReleaseComponent, Artifact, ApprovalRequest, ApprovalStep, ApprovalAction, AuditEvent, ReleaseSnapshot, SnapshotArtifact)}


def test_repeat_and_isolation(context):
    db=context[0]; old=rows(db); seed_release_demo(db); db.commit(); verify(db)
    first=rows(db); seed_release_demo(db); db.commit(); assert first==rows(db)
    for model, records in old.items():
        assert all(record in first[model] for record in records)


def test_caller_atomic_rollback(context):
    db=context[0]; seed_release_demo(db); db.rollback()
    assert db.get(Release,key('DEMO-SSR-1.0')) is None
    seed_release_demo(db); db.commit(); verify(db)


def test_four_stage_progress_and_closed_samples(context):
    db=context[0]; seed_release_demo(db); db.commit()
    for order in (2,3,4):
        step=db.get(ApprovalStep,key('DEMO-SSR-1.0'+str(order)))
        result=ApprovalService(db).act('APR-DEMO-SSR-1.0','Test reviewer','APPROVED',expected_step_id=step.id)
        assert result.status==('APPROVED' if order==4 else 'PENDING')
    for v in ('DEMO-ASR-A-1.0','DEMO-ASR-B-1.0'):
        with pytest.raises(ApprovalError,match='closed'):
            ApprovalService(db).act('APR-'+v,'Test reviewer','APPROVED')
    seed_release_demo(db); db.commit()
    assert db.get(ApprovalRequest,key('DEMO-SSR-1.0approval')).status=='APPROVED'
