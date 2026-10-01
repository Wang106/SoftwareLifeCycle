"""Actual PostgreSQL blocking and rollback in the release/distribution chain."""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg, count, overlapping_commands
from test_command_audit import prepare_snapshot_source
from app.models.core import Release, Customer, Project, ApplicationReleaseDetail
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.audit import AuditEvent
from app.services.distribution import DistributionService, DistributionError
from app.services.approval import ApprovalService
from app.services.snapshot import SnapshotService
from app.services.audit import AuditEventService

KINDS=('delivery','distribution','authorization')
MODEL=dict(delivery=DeliveryPackage,distribution=Distribution,authorization=SoftwareAuthorization)
ENTITY=dict(delivery='DELIVERY_PACKAGE',distribution='DISTRIBUTION',authorization='SOFTWARE_AUTHORIZATION')
MODELS=(DeliveryPackage,DeliveryPackageItem,Distribution,SoftwareAuthorization,ReleaseDecision,AuditEvent)

@pytest.fixture
def chain(pg):
    engine,ids=pg
    with Session(engine,expire_on_commit=False) as db:
        customer=db.scalar(select(Customer));project=db.scalar(select(Project))
        first=db.get(Release,ids['release'])
        second=Release(software_id=first.software_id,release_type='STANDARD',version='2')
        db.add(second);db.commit();prepare_snapshot_source(db,second)
        SnapshotService().create(db,second.id)
        result=[]
        for n,release in enumerate((first,second),1):
            snapshot=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==release.id))
            artifact=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==snapshot.id))
            # Fixture data only: establish an approved distributable frozen chain.
            artifact.distribution_level='CONTROLLED'
            db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=artifact.id,
                recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION',decision='ALLOW'))
            db.add(ApplicationReleaseDetail(release_id=release.id,customer_id=customer.id,
                project_id=project.id,standard_base_release_id=first.id))
            approval=ApprovalRequest(approval_no=f'APR-{n}',target_type='RELEASE',target_id=release.id,
                snapshot_id=snapshot.id,status='APPROVED')
            db.add(approval);db.commit()
            ApprovalService(db).create_release_decision(f'APR-{n}',f'RD-{n}','Manager','READY','RELEASE')
            package=DistributionService(db).create_delivery(release.id,f'DP-{n}',1,'CUSTOMER','C',
                'PRODUCTION',[artifact.id])
            distribution=DistributionService(db).create_distribution(package.id,f'DIST-{n}','CUSTOMER','C')
            result.append(dict(release=release.id,artifact=artifact.id,approval=approval.id,
                package=package.id,distribution=distribution.id,customer=customer.id,project=project.id))
    return engine,result

def run(db,kind,ids,key,number='NEW',**changes):
    if kind=='delivery':values=dict(release_id=ids['release'],package_no=number,revision=1,
        recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION',snapshot_artifact_ids=[ids['artifact']])
    elif kind=='distribution':values=dict(delivery_package_id=ids['package'],distribution_no=number,
        recipient_type='CUSTOMER',recipient_code='C')
    else:values=dict(release_id=ids['release'],distribution_id=ids['distribution'],authorization_no=number,
        customer_id=ids['customer'],project_id=ids['project'],site_code='SITE',line_code='LINE',batch_limit=1)
    return getattr(DistributionService(db),'create_'+kind)(**{**values,**changes},request_id=key)

def counts(db):return {m:count(db,m) for m in MODELS}

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('case',['replay','changed','duplicate','different'])
def test_same_parent_competing_writes_are_serialized(chain,monkeypatch,kind,case):
    engine,ids=chain;key=uuid.uuid4();other=key if case in ('replay','changed') else uuid.uuid4()
    changed={'created_by':'Changed'} if kind=='delivery' else ({'recipient_code':'Changed'} if kind=='distribution' else {'restriction_note':'Changed'})
    with Session(engine) as db:before=counts(db)
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:run(db,kind,ids[0],key),
        lambda db:run(db,kind,ids[0],other,'OTHER' if case=='different' else 'NEW',**(changed if case=='changed' else {})))
    assert first[0]=='ok' and second[0]==('ok' if case in ('replay','different') else 'conflict')
    if case=='replay':assert first[1]==second[1]
    with Session(engine) as db:
        added=2 if case=='different' else 1
        assert count(db,MODEL[kind])==before[MODEL[kind]]+added
        assert count(db,AuditEvent)==before[AuditEvent]+added
        if kind=='delivery':assert count(db,DeliveryPackageItem)==before[DeliveryPackageItem]+added

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('collision',['key','number'])
def test_global_key_or_business_number_race_across_independent_parents(chain,monkeypatch,kind,collision):
    engine,ids=chain;key=uuid.uuid4()
    with Session(engine) as db:before=counts(db)
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:run(db,kind,ids[0],key),
        lambda db:run(db,kind,ids[1],key if collision=='key' else uuid.uuid4(),'OTHER' if collision=='key' else 'NEW'))
    assert first[0]=='ok' and second[0]=='conflict'
    with Session(engine) as db:
        assert count(db,MODEL[kind])==before[MODEL[kind]]+1 and count(db,AuditEvent)==before[AuditEvent]+1
        if kind=='delivery':assert count(db,DeliveryPackageItem)==before[DeliveryPackageItem]+1

@pytest.mark.parametrize('kind',KINDS)
def test_audit_flush_failure_rolls_back_and_releases_all_locks(chain,monkeypatch,kind):
    engine,ids=chain;key=uuid.uuid4();original=AuditEventService.record
    def fail(*a,**kw):original(*a,**kw);raise RuntimeError('after audit flush')
    with Session(engine) as db:
        before=counts(db);monkeypatch.setattr(AuditEventService,'record',fail)
        with pytest.raises(RuntimeError):run(db,kind,ids[0],key)
        assert not db.in_transaction() and counts(db)==before
    monkeypatch.setattr(AuditEventService,'record',original)
    with Session(engine) as db:assert run(db,kind,ids[0],key).id==key

@pytest.mark.parametrize('kind,stale',[('delivery','approval'),('distribution','package'),
    ('authorization','distribution'),('authorization','package'),('authorization','decision')])
def test_parent_identity_map_is_refreshed_before_checks(chain,kind,stale):
    engine,ids=chain;ids=ids[0]
    with Session(engine,expire_on_commit=False) as db:
        if stale=='approval':cached=db.get(ApprovalRequest,ids['approval'])
        elif stale=='package':cached=db.get(DeliveryPackage,ids['package'])
        elif stale=='distribution':cached=db.get(Distribution,ids['distribution'])
        else:cached=db.scalar(select(ReleaseDecision).where(ReleaseDecision.release_id==ids['release']))
        db.commit()
        with Session(engine) as writer:
            row=writer.get(type(cached),cached.id)
            if stale=='decision':row.decision='HOLD'
            elif kind=='authorization' and stale=='package':row.purpose='TEST'
            else:row.status='CANCELLED'
            writer.commit()
        before=counts(db)
        with pytest.raises(DistributionError):run(db,kind,ids,uuid.uuid4())
        assert not db.in_transaction() and counts(db)==before

@pytest.mark.parametrize('kind',['delivery','authorization'])
@pytest.mark.parametrize('decision',['RELEASE','HOLD'])
def test_new_release_decision_commits_before_downstream_validation(chain,monkeypatch,kind,decision):
    engine,ids=chain
    with Session(engine) as db:before=counts(db)
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:ApprovalService(db).create_release_decision('APR-1','RD-NEW','Manager','READY',decision,request_id=uuid.uuid4()),
        lambda db:run(db,kind,ids[0],uuid.uuid4()))
    assert first[0]=='ok' and second[0]==('ok' if decision=='RELEASE' else 'conflict')
    with Session(engine) as db:
        assert count(db,MODEL[kind])==before[MODEL[kind]]+(decision=='RELEASE')
        assert count(db,AuditEvent)==before[AuditEvent]+1+(decision=='RELEASE')

@pytest.mark.parametrize('kind',['delivery','authorization'])
def test_downstream_commit_precedes_later_hold_without_deadlock(chain,monkeypatch,kind):
    engine,ids=chain
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:run(db,kind,ids[0],uuid.uuid4()),
        lambda db:ApprovalService(db).create_release_decision('APR-1','RD-NEW','Manager','READY','HOLD',request_id=uuid.uuid4()))
    assert first[0]==second[0]=='ok'
    with Session(engine) as db:
        event=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==first[1]))
        if kind=='delivery':assert event.payload_json['decision_no']=='RD-1'
        assert db.get(ReleaseDecision,second[1]).decision=='HOLD'
