import uuid
import pytest
from sqlalchemy import select,func
from test_impact_assessments import context
from app.models.approval import ApprovalRequest,ApprovalStep,ApprovalAction,ReleaseDecision
from app.models.core import Customer,Project,ApplicationReleaseDetail
from app.models.snapshot import SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.models.distribution import DeliveryPackage,DeliveryPackageItem,Distribution,SoftwareAuthorization
from app.models.audit import AuditEvent
from app.services.approval import ApprovalService,ApprovalError
from app.services.distribution import DistributionService,DistributionError
from app.services.audit import AuditEventService
from app.actor import ActorContext
from app.models.security import SecurityPrincipal
from app.api.activity import audit_catalog,AuditFilters,get_activity

@pytest.fixture
def controlled(context):
    db,_,release,snapshot,_=context
    customer=Customer(code='C',name='Customer');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='P',name='Project');db.add(project);db.flush()
    db.add(ApplicationReleaseDetail(release_id=release.id,customer_id=customer.id,project_id=project.id,standard_base_release_id=release.id))
    approval=ApprovalRequest(approval_no='APR',target_type='RELEASE',target_id=release.id,snapshot_id=snapshot.id,status='PENDING')
    db.add(approval);db.flush()
    steps=[ApprovalStep(approval_request_id=approval.id,step_order=i,role_name='Review',status='PENDING' if i==1 else 'WAITING') for i in [1,2]];db.add_all(steps)
    artifact=SnapshotArtifact(snapshot_id=snapshot.id,source_artifact_id=uuid.uuid4(),component_code='APP',filename='app.hex',artifact_type='HEX',sha256='f'*64,classification='CONFIDENTIAL',distribution_level='CONTROLLED',ai_access_policy='DENY',storage_reference='/test/app.hex');db.add(artifact);db.flush()
    db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=artifact.id,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION',decision='ALLOW'))
    db.commit();return db,release,snapshot,approval,steps,artifact,customer,project


def count(db,model):return db.scalar(select(func.count()).select_from(model))
def approve(ctx):
    db,_,_,approval,*_=ctx
    for _ in range(2):ApprovalService(db).act(approval.approval_no,'Engineer','APPROVED','Reviewed')
def decision(ctx,no='RD'):
    db,*_=ctx;return ApprovalService(db).create_release_decision('APR',no,'Manager','READY','RELEASE','Notes')
def delivery(ctx,revision=1):
    db,release,_,_,_,artifact,*_=ctx
    return DistributionService(db).create_delivery(release.id,'DP',revision,'CUSTOMER','C','PRODUCTION',[artifact.id],created_by='Engineer')
def distribute(ctx,package):return DistributionService(ctx[0]).create_distribution(package.id,'DIST','CUSTOMER','C')
def authorize(ctx,distribution):
    db,release,*_=ctx;customer,project=ctx[-2:]
    return DistributionService(db).create_authorization(release.id,distribution.id,'PA',customer.id,project.id,'SITE','LINE',batch_limit=1,restriction_note='Controlled')


def test_full_controlled_chain_records_five_operations(controlled):
    db,release,snapshot,approval,steps,*_=controlled
    approve(controlled);d=decision(controlled);p=delivery(controlled);dist=distribute(controlled,p);auth=authorize(controlled,dist)
    events=db.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()
    assert len(events)==6 and count(db,ApprovalAction)==2
    assert events[0].payload_json['before_status']=='PENDING' and events[0].payload_json['after_status']=='PENDING'
    assert events[1].payload_json['after_status']=='APPROVED'
    assert events[0].payload_json['approval_action_id']!=events[1].payload_json['approval_action_id']
    assert all(step.decided_at for step in steps)
    rd=next(e for e in events if e.entity_type=='RELEASE_DECISION')
    assert rd.entity_id==d.id and rd.payload_json['snapshot_id']==str(snapshot.id) and rd.payload_json['content_hash']==snapshot.content_hash
    dp=next(e for e in events if e.entity_type=='DELIVERY_PACKAGE')
    assert dp.entity_id==p.id and dp.payload_json['revision']==1 and dp.actor_name=='Engineer'
    assert get_activity(dp.event_no,db)['delivery_revision']==1
    assert audit_catalog(AuditFilters(entity_id=p.id),db)['items'][0]['delivery_revision']==1
    assert dist.status=='READY' and auth.status=='DRAFT'
    assert all(e.actor_name=='Not recorded' and e.payload_json['actor_source']=='NOT_PROVIDED' for e in events if e.entity_type in ['DISTRIBUTION','SOFTWARE_AUTHORIZATION'])
    assert len({e.event_no for e in events})==6 and all(len(e.event_no)<=50 for e in events)


def test_authenticated_actor_replaces_declaration_and_preserves_it(controlled):
    db,_,_,approval,*_=controlled
    principal=SecurityPrincipal(issuer='https://identity.example.com',subject='reviewer-1',
        principal_type='USER',display_name='Trusted Reviewer')
    db.add(principal);db.commit()
    actor=ActorContext(name='Trusted Reviewer',principal_id=principal.id,
        display_name=principal.display_name,declared_name='Claimed Manager',
        source='AUTHENTICATED_PRINCIPAL')
    ApprovalService(db).act(approval.approval_no,'Claimed Manager','APPROVED','Reviewed',
        actor_context=actor)
    action=db.scalars(select(ApprovalAction)).one()
    event=db.scalars(select(AuditEvent)).one()
    assert action.actor_name=='Trusted Reviewer'
    assert event.actor_name==event.actor_display_name=='Trusted Reviewer'
    assert event.actor_principal_id==principal.id
    assert event.declared_actor_name=='Claimed Manager'
    assert event.payload_json['actor_source']=='AUTHENTICATED_PRINCIPAL'
    detail=get_activity(event.event_no,db)
    assert detail['actor_principal_id']==str(principal.id)
    assert detail['declared_actor_name']=='Claimed Manager'
    assert audit_catalog(AuditFilters(actor_principal_id=principal.id),db)['total']==1


@pytest.mark.parametrize('action',['RETURNED','REJECTED'])
def test_terminal_actions_audited_once(controlled,action):
    db,*_=controlled;ApprovalService(db).act('APR','Engineer',action)
    assert count(db,AuditEvent)==count(db,ApprovalAction)==1
    assert db.scalars(select(AuditEvent)).one().payload_json['after_status']==action
    with pytest.raises(ApprovalError):ApprovalService(db).act('APR','Engineer',action)
    assert count(db,AuditEvent)==1


def test_invalid_action_does_not_mutate_waiting_step(controlled):
    db,_,_,approval,steps,*_=controlled;steps[0].status='WAITING';db.commit()
    with pytest.raises(ApprovalError):ApprovalService(db).act('APR','Engineer','UNSUPPORTED')
    assert steps[0].status=='WAITING' and count(db,AuditEvent)==count(db,ApprovalAction)==0


@pytest.mark.parametrize('kind',['action','decision','delivery','distribution','authorization'])
@pytest.mark.parametrize('failure',['audit','audit_after_flush','commit'])
def test_atomic_failure_rolls_back_domain_and_event(controlled,monkeypatch,kind,failure):
    db,*_=controlled
    if kind!='action':approve(controlled)
    if kind in ['delivery','distribution','authorization']:decision(controlled)
    p=delivery(controlled) if kind in ['distribution','authorization'] else None
    dist=distribute(controlled,p) if kind=='authorization' else None
    models=[ApprovalAction,ReleaseDecision,DeliveryPackage,DeliveryPackageItem,Distribution,SoftwareAuthorization,AuditEvent]
    before={m:count(db,m) for m in models}
    def fail(*args,**kwargs):raise RuntimeError('Injected failure')
    if failure=='audit':monkeypatch.setattr(AuditEventService,'record',fail)
    elif failure=='audit_after_flush':
        original=AuditEventService.record
        def fail_after_flush(self,**fields):
            original(self,**fields)
            raise RuntimeError('Injected after event flush')
        monkeypatch.setattr(AuditEventService,'record',fail_after_flush)
    else:monkeypatch.setattr(db,'commit',fail)
    call={'action':lambda:ApprovalService(db).act('APR','Engineer','APPROVED'),'decision':lambda:decision(controlled),'delivery':lambda:delivery(controlled),'distribution':lambda:distribute(controlled,p),'authorization':lambda:authorize(controlled,dist)}[kind]
    with pytest.raises(RuntimeError):call()
    assert {m:count(db,m) for m in models}==before
    if kind=='action':assert db.scalars(select(ApprovalRequest)).one().status=='PENDING' and db.scalars(select(ApprovalStep).order_by(ApprovalStep.step_order)).first().status=='PENDING'
    monkeypatch.undo();call()
    assert count(db,AuditEvent)==before[AuditEvent]+1


def test_duplicate_numbers_create_no_extra_audit(controlled):
    db,*_=controlled;approve(controlled);decision(controlled);p=delivery(controlled);dist=distribute(controlled,p);authorize(controlled,dist)
    for call in [lambda:decision(controlled),lambda:delivery(controlled),lambda:distribute(controlled,p),lambda:authorize(controlled,dist)]:
        with pytest.raises((ApprovalError,DistributionError)):call()
    assert count(db,AuditEvent)==6


def test_delivery_revision_link_uses_uuid_not_latest(controlled):
    db,*_=controlled;approve(controlled);decision(controlled);first=delivery(controlled);second=delivery(controlled,2)
    events=audit_catalog(AuditFilters(entity_type='DELIVERY_PACKAGE'),db)['items']
    assert {e['entity_id']:e['delivery_revision'] for e in events}=={str(first.id):1,str(second.id):2}
