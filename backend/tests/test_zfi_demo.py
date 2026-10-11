import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.seed_zfi_demo import seed_zfi_demo, manifest, key
from app.api.release_demo import zfi_import
from app.api.dashboard import _application_release, _readiness_for_release
from app.api.release_catalog import resolve_application, Resolution
from app.models.core import Release, ApplicationReleaseDetail, Supplier, SoftwareProduct, Customer, Project, Artifact
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.models.snapshot import ReleaseSnapshot
from app.models.audit import AuditEvent
from app.seed_release_demo import SSR_ROLES, ASR_ROLES
from test_impact_assessments import context


def verify(db):
    data = manifest(); refs = data['standards'] + data['applications']
    assert len(refs) == 20
    assert len({(r['product'],r['version'],r['customer']) for r in data['applications']}) == 16
    for row in refs:
        r = db.get(Release, key(row['ref'])); assert r.version == row['version'] and r.status == 'DRAFT'
        a = db.get(ApprovalRequest, key(row['ref']+'-approval'))
        steps = db.scalars(select(ApprovalStep).where(ApprovalStep.approval_request_id==a.id).order_by(ApprovalStep.step_order)).all()
        assert tuple(s.role_name for s in steps) == (SSR_ROLES if row['ref'].startswith('SSR') else ASR_ROLES)
        assert len(steps) == 4
        snapshot = db.get(ReleaseSnapshot,a.snapshot_id)
        assert snapshot.release_id == r.id and snapshot.release_metadata_json['sample_only']
        if row['ref'].startswith('ASR'):
            d = db.get(ApplicationReleaseDetail,r.id)
            assert d.customer_id == r.customer_scope_id == key('customer-'+row['customer'])
            assert d.project_id == key('project-'+row['project_code'])
            assert d.standard_base_release_id == key(row['base_ref'])
    assert not db.scalar(select(ReleaseDecision.id).where(ReleaseDecision.release_id.in_([key(r['ref']) for r in refs])))
    result = zfi_import(db); assert result['initialized'] and len(result['items'])==20
    assert result['release_decisions_created']==0
    assert all(i['supplied_artifacts']==i['supplied_test_evidence']==0 for i in result['items'])
    for ref,order in [('SSR02',2),('ASR05',3),('ASR06',4)]:
        assert db.get(ApprovalStep,key(ref+f'-step-{order}')).status=='PENDING'
    assert db.get(ApprovalRequest,key('ASR07-approval')).status=='RETURNED'
    assert db.get(ApprovalRequest,key('ASR08-approval')).status=='REJECTED'
    for ref in ['SSR01','ASR01']:
        assert _readiness_for_release(db.get(Release,key(ref)),db,bounded=True)['overall']=='NOT_READY'


def rows(db):
    return {m.__tablename__:[tuple(getattr(x,c.name) for c in m.__table__.columns) for x in db.scalars(select(m).order_by(m.id if hasattr(m,'id') else m.release_id))]
        for m in (Release,Supplier,SoftwareProduct,Customer,Project,ApplicationReleaseDetail,ApprovalRequest,
                  ApprovalStep,ApprovalAction,AuditEvent,ReleaseSnapshot,ReleaseDecision,Artifact)}


def test_repeat_and_isolation(context):
    db=context[0];before=rows(db);assert not zfi_import(db)['initialized']
    seed_zfi_demo(db);db.commit();verify(db);first=rows(db)
    assert seed_zfi_demo(db)['already_present'];db.commit();assert rows(db)==first
    for model,records in before.items():assert all(r in first[model] for r in records)


def test_atomic_rollback(context):
    db=context[0];before=rows(db);seed_zfi_demo(db);db.rollback();assert rows(db)==before


def test_namespace_collision(context):
    db=context[0];db.add(Customer(code='KUBO',name='Unrelated'));db.commit()
    with pytest.raises(ValueError,match='unowned'):seed_zfi_demo(db)
    assert db.get(Release,key('SSR01')) is None


def test_scoped_duplicate_rejected(context):
    db=context[0];seed_zfi_demo(db);db.commit();r=db.get(Release,key('ASR01'))
    db.add(Release(software_id=r.software_id,release_type='APPLICATION',version=r.version,customer_scope_id=r.customer_scope_id))
    with pytest.raises(IntegrityError):db.flush()
    db.rollback()


def test_explicit_uuid_resolves_and_version_is_ambiguous(context):
    db=context[0];seed_zfi_demo(db);db.commit()
    assert resolve_application(Resolution(identifier='v3.8.1.1'),db)['state']=='ambiguous'
    assert resolve_application(Resolution(identifier=str(key('ASR02'))),db)['release']['id']==str(key('ASR02'))
    with pytest.raises(HTTPException) as err:_application_release(db,'v3.8.1.1')
    assert err.value.status_code==409


def test_legacy_null_scope_stays_unique(context):
    db=context[0];r=context[2]
    db.add(Release(software_id=r.software_id,release_type=r.release_type,version=r.version))
    with pytest.raises(IntegrityError):db.flush()
    db.rollback()
