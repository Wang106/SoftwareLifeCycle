"""Distribution retry, actor, scope and failure contracts."""
import uuid
from dataclasses import replace
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from test_transactional_audit import controlled, approve, decision, delivery, distribute
from test_impact_assessments import context
from test_command_audit import trusted_actor
from app.actor import ActorContext
from app.api.distribution import DeliveryCreate, DistributionCreate, AuthorizationCreate, create_delivery, create_distribution, create_authorization
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.approval import ReleaseDecision
from app.models.audit import AuditEvent
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.distribution import DistributionError, DistributionService
from app.services.audit import AuditEventService

KINDS=('delivery','distribution','authorization')
MODELS=(DeliveryPackage,DeliveryPackageItem,Distribution,SoftwareAuthorization,AuditEvent)
NUMBERS=dict(delivery='package_no',distribution='distribution_no',authorization='authorization_no')

@pytest.fixture
def chain(controlled):
    approve(controlled);decision(controlled)
    package=delivery(controlled);distribution=distribute(controlled,package)
    return controlled,package,distribution

def args(chain,kind):
    ctx,package,distribution=chain
    _,release,_,_,_,artifact,customer,project=ctx
    common=dict(request_id=uuid.uuid4())
    if kind=='delivery':return dict(**common,release_id=release.id,package_no='NEW-DP',revision=1,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION',snapshot_artifact_ids=[artifact.id],created_by='Engineer')
    if kind=='distribution':return dict(**common,delivery_package_id=package.id,distribution_no='NEW-DIST',recipient_type='CUSTOMER',recipient_code='C')
    return dict(**common,release_id=release.id,distribution_id=distribution.id,authorization_no='NEW-AUTH',customer_id=customer.id,project_id=project.id,site_code='SITE',line_code='LINE',purpose='PRODUCTION',batch_limit=2,restriction_note='Controlled')

def counts(db):return {m:db.scalar(select(func.count()).select_from(m)) for m in MODELS}
def run(db,kind,values,actor=None):return getattr(DistributionService(db),'create_'+kind)(**values,actor_context=actor)

@pytest.mark.parametrize('kind',KINDS)
def test_identical_retry_and_no_key_duplicate_compatibility(chain,kind):
    db=chain[0][0];values=args(chain,kind);first=run(db,kind,values);before=counts(db)
    assert run(db,kind,values).id==first.id==values['request_id'] and counts(db)==before
    for key in (None,uuid.uuid4()):
        with pytest.raises(DistributionError):run(db,kind,{**values,'request_id':key})
        assert counts(db)==before

CONFLICTS=[('delivery','package_no','OTHER'),('delivery','revision',2),('delivery','recipient_type','FACTORY'),('delivery','recipient_code','OTHER'),('delivery','purpose','TEST'),('delivery','created_by','Other'),('delivery','snapshot_artifact_ids',[]),('delivery','release_id',uuid.uuid4()),('distribution','distribution_no','OTHER'),('distribution','recipient_type','FACTORY'),('distribution','recipient_code','OTHER'),('distribution','delivery_package_id',uuid.uuid4()),('authorization','authorization_no','OTHER'),('authorization','customer_id',uuid.uuid4()),('authorization','project_id',uuid.uuid4()),('authorization','site_code','OTHER'),('authorization','line_code','OTHER'),('authorization','purpose','TEST'),('authorization','batch_limit',None),('authorization','restriction_note','Other'),('authorization','release_id',uuid.uuid4()),('authorization','distribution_id',uuid.uuid4())]
@pytest.mark.parametrize('kind,field,value',CONFLICTS)
def test_changed_content_conflicts(chain,kind,field,value):
    db=chain[0][0];values=args(chain,kind);run(db,kind,values);before=counts(db)
    with pytest.raises(DistributionError):run(db,kind,{**values,field:value})
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('case',['principal','declaration','display','mode','legacy'])
def test_actor_binding_and_legacy_evidence(chain,kind,case):
    db=chain[0][0];values=args(chain,kind);actor=trusted_actor(db,'writer','Trusted Actor')
    row=run(db,kind,{**values,'request_id':None} if case=='legacy' else values,actor)
    if case=='legacy':values['request_id']=row.id
    elif case=='principal':actor=trusted_actor(db,'other','Trusted Actor')
    elif case=='declaration':actor=replace(actor,declared_name='Changed')
    elif case=='display':actor=replace(actor,display_name='Changed')
    elif case=='mode':actor=ActorContext.legacy('Trusted Actor')
    before=counts(db)
    with pytest.raises(DistributionError,match='request_id'):run(db,kind,values,actor)
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
def test_replay_after_parent_ineligible(chain,kind):
    db=chain[0][0];values=args(chain,kind);row=run(db,kind,values)
    if kind=='delivery':
        chain[0][3].status='CANCELLED';db.scalar(select(ReleaseDecision)).decision='HOLD'
    elif kind=='distribution':chain[1].status='CANCELLED'
    else:chain[2].status='CANCELLED'
    db.commit();before=counts(db)
    assert run(db,kind,values).id==row.id and counts(db)==before
    with pytest.raises(DistributionError):run(db,kind,{**values,'request_id':uuid.uuid4(),NUMBERS[kind]:'FRESH'})
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('failure',['validation','flush','audit_after_flush','commit'])
def test_all_failures_rollback_and_key_reusable(chain,monkeypatch,kind,failure):
    db=chain[0][0];values=args(chain,kind);before=counts(db)
    with monkeypatch.context() as patch:
        bad={**values}
        if failure=='validation':
            if kind=='delivery':bad['snapshot_artifact_ids']=[chain[0][5].id,uuid.uuid4()]
            elif kind=='distribution':bad['recipient_code']='WRONG'
            else:bad['batch_limit']=0
        elif failure=='flush':
            def fail(*a,**kw):raise IntegrityError('injected',{},Exception('failure'))
            patch.setattr(db,'flush',fail)
        elif failure=='audit_after_flush':
            original=AuditEventService.record
            def fail(*a,**kw):original(*a,**kw);raise RuntimeError('audit failure')
            patch.setattr(AuditEventService,'record',fail)
        else:
            def fail(*a,**kw):raise RuntimeError('commit failure')
            patch.setattr(db,'commit',fail)
        with pytest.raises((DistributionError,RuntimeError)):run(db,kind,bad)
    assert not db.in_transaction() and counts(db)==before
    assert run(db,kind,values).id==values['request_id']
    assert counts(db)[AuditEvent]==before[AuditEvent]+1

def test_delivery_item_order_is_set_but_duplicates_invalid(chain):
    from app.models.snapshot import SnapshotArtifact
    db=chain[0][0];first=chain[0][5]
    second=SnapshotArtifact(snapshot_id=first.snapshot_id,source_artifact_id=uuid.uuid4(),component_code='BOOT',filename='boot.hex',artifact_type='HEX',sha256='a'*64,classification='CONFIDENTIAL',distribution_level='CONTROLLED',ai_access_policy='DENY',storage_reference='/boot.hex')
    db.add(second);db.flush();db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=second.id,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION',decision='ALLOW'));db.commit()
    values=args(chain,'delivery');values['snapshot_artifact_ids']=[first.id,second.id]
    row=run(db,'delivery',values);before=counts(db)
    assert run(db,'delivery',{**values,'snapshot_artifact_ids':[second.id,first.id]}).id==row.id
    with pytest.raises(DistributionError):run(db,'delivery',{**values,'snapshot_artifact_ids':[first.id,first.id]})
    assert counts(db)==before

@pytest.mark.parametrize('invalid',['internal','denied','wrong_snapshot','duplicate','empty'])
def test_frozen_artifact_policy_guards_rollback(chain,invalid):
    db=chain[0][0];artifact=chain[0][5];values=args(chain,'delivery')
    if invalid=='internal':artifact.distribution_level='INTERNAL_ONLY'
    elif invalid=='denied':db.scalar(select(SnapshotArtifactDistributionRule)).decision='DENY'
    elif invalid=='wrong_snapshot':values['snapshot_artifact_ids']=[uuid.uuid4()]
    elif invalid=='duplicate':values['snapshot_artifact_ids']=[artifact.id,artifact.id]
    else:values['snapshot_artifact_ids']=[]
    db.commit();before=counts(db)
    with pytest.raises(DistributionError):run(db,'delivery',values)
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
def test_http_shapes_uuid_conflict_and_exact_active_role(chain,monkeypatch,kind):
    from app.core.config import settings
    from app.authorization import AuthorizationError
    from app.models.security import ProjectMembership,SecurityPrincipal
    from test_authorization import authenticated_request
    db=chain[0][0];values=args(chain,kind)
    model=dict(delivery=DeliveryCreate,distribution=DistributionCreate,authorization=AuthorizationCreate)[kind]
    call=dict(delivery=create_delivery,distribution=create_distribution,authorization=create_authorization)[kind]
    with pytest.raises(ValidationError):model(**{**values,'request_id':'invalid'})
    payload=model(**values);actor=trusted_actor(db,kind,'Authenticated Writer')
    request=authenticated_request(db.get(SecurityPrincipal,actor.principal_id))
    grant=ProjectMembership(principal_id=actor.principal_id,project_id=chain[0][-1].id,role='PRODUCTION_AUTHORITY' if kind=='authorization' else 'DISTRIBUTION_AUTHORITY',status='ACTIVE')
    monkeypatch.setattr(settings,'auth_mode','oidc');before=counts(db)
    with pytest.raises(AuthorizationError):call(payload,db,request)
    assert counts(db)==before
    db.add(grant);db.commit();first=call(payload,db,request);before=counts(db)
    assert call(payload,db,request)==first and counts(db)==before and first['id']==str(values['request_id'])
    assert first['status']==('DRAFT' if kind=='authorization' else 'READY')
    event=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==values['request_id']))
    assert event.actor_principal_id==actor.principal_id and event.actor_name=='Authenticated Writer'
    assert event.declared_actor_name==('Engineer' if kind=='delivery' else None)
    with pytest.raises(HTTPException) as exc:call(model(**{**values,NUMBERS[kind]:'DIFFERENT'}),db,request)
    assert exc.value.status_code==409 and counts(db)==before
    grant.status='SUSPENDED';db.commit()
    with pytest.raises(AuthorizationError):call(payload,db,request)
    assert counts(db)==before
