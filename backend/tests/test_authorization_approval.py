"""Synthetic dual-person authorization approval contracts; no real identities/writes."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, MetaData, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import app.models
from app.actor import ActorContext
from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.core.db import Base
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct, Supplier
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.security import BrowserSession, GlobalRoleAssignment, ProjectMembership, SecurityPrincipal
from app.models.snapshot import ReleaseSnapshot
from app.services.audit import AuditEventService
from app.services.distribution import DistributionService

ISSUER='https://approval.synthetic.example'
TOKEN='synthetic-approval-token'


def seed_approval(db):
    supplier=Supplier(code='PAA-S',name='Synthetic supplier');customer=Customer(code='PAA-C',name='Synthetic customer')
    db.add_all([supplier,customer]);db.flush()
    product=SoftwareProduct(supplier_id=supplier.id,code='PAA-SW',name='Synthetic software')
    project=Project(customer_id=customer.id,project_code='PAA-P',name='Synthetic project')
    foreign=Project(customer_id=customer.id,project_code='PAA-F',name='Foreign project')
    people={name:SecurityPrincipal(issuer=ISSUER,subject='paa-'+name,principal_type='SERVICE' if name=='service' else 'USER',display_name=name) for name in ['creator','approver','other','admin','foreign','service']}
    db.add_all([product,project,foreign,*people.values()]);db.flush()
    release=Release(software_id=product.id,release_type='APPLICATION',version='PAA-1',status='RELEASED');db.add(release);db.flush()
    db.add(ApplicationReleaseDetail(release_id=release.id,customer_id=customer.id,project_id=project.id,standard_base_release_id=release.id))
    snapshot=ReleaseSnapshot(release_id=release.id,snapshot_no='PAA-SNAP',snapshot_number=1,status='FROZEN',content_hash='a'*64);db.add(snapshot);db.flush()
    approval=ApprovalRequest(approval_no='PAA-APR',target_type='RELEASE',target_id=release.id,snapshot_id=snapshot.id,status='APPROVED');db.add(approval);db.flush()
    decision=ReleaseDecision(decision_no='PAA-RD',release_id=release.id,snapshot_id=snapshot.id,approval_request_id=approval.id,readiness_status='READY',decision='RELEASE',decided_by='Synthetic reviewer');db.add(decision)
    package=DeliveryPackage(package_no='PAA-DP',revision=1,release_id=release.id,snapshot_id=snapshot.id,recipient_type='CUSTOMER',recipient_code=customer.code,purpose='PRODUCTION',status='READY');db.add(package);db.flush()
    distribution=Distribution(distribution_no='PAA-DIST',delivery_package_id=package.id,recipient_type='CUSTOMER',recipient_code=customer.code,status='READY');db.add(distribution)
    grants={name:ProjectMembership(principal_id=person.id,project_id=foreign.id if name=='foreign' else project.id,role='PRODUCTION_AUTHORITY') for name,person in people.items() if name!='admin'}
    db.add_all([*grants.values(),GlobalRoleAssignment(principal_id=people['admin'].id,role='PLATFORM_ADMIN')]);db.commit()
    creator=people['creator'];actor=ActorContext(creator.display_name,creator.id,creator.display_name,None,'AUTHENTICATED_PRINCIPAL')
    authorization=DistributionService(db).create_authorization(release.id,distribution.id,'PAA-AUTH',customer.id,project.id,'PAA-SITE','PAA-LINE',batch_limit=2,restriction_note='Synthetic controlled facts',actor_context=actor,request_id=uuid.uuid4())
    ids={'authorization':authorization.id,'number':authorization.authorization_no,'release':release.id,'snapshot':snapshot.id,'decision':decision.id,'package':package.id,'distribution':distribution.id,'project':project.id,'foreign_project':foreign.id,'people':{name:person.id for name,person in people.items()},'grants':{name:grant.id for name,grant in grants.items()}}
    return ids


def configure(monkeypatch):
    for key,value in {'auth_mode':'oidc','oidc_issuer_url':ISSUER,'read_only_mode':False}.items():monkeypatch.setattr(settings,key,value)


def actor_request(db,ids,name='approver',session_id=None):
    p=db.get(SecurityPrincipal,ids['people'][name]);headers=[(b'authorization',('Bearer '+TOKEN).encode())]
    if session_id:headers.append((b'x-browser-session',str(session_id).encode()))
    request=Request({'type':'http','method':'POST','path':'/','headers':headers})
    request.state.principal=AuthenticatedPrincipal(p.id,p.issuer,p.subject,p.principal_type,p.display_name,p.email)
    return request


def service(db):
    from app.services.authorization_approval import AuthorizationApprovalService
    return AuthorizationApprovalService(db)


def prepare(db,ids,name='approver'):
    return service(db).context(ids['number'],actor_request(db,ids,name))


def body(db,ids):
    return {'request_id':uuid.uuid4(),'expected_context_digest':prepare(db,ids)['context_digest'],'reason':'Reviewed exact frozen production chain'}


def submit(db,ids,values,name='approver',request=None):
    return service(db).approve(ids['number'],request or actor_request(db,ids,name),**values)


def counts(db):
    return db.scalar(select(func.count()).select_from(AuditEvent))


@pytest.fixture
def approval_db(monkeypatch):
    configure(monkeypatch);metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        copied=table.to_metadata(metadata)
        for column in copied.columns:
            if isinstance(column.type,JSONB):column.type=JSON()
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:yield db,seed_approval(db)
    engine.dispose()


def test_context_is_minimal_coherent_and_read_only(approval_db):
    db,ids=approval_db;before=counts(db);data=prepare(db,ids)
    assert set(data)=={'version','context','context_digest'} and data['version']==1
    assert len(data['context_digest'])==64 and set(data['context_digest'])<=set('0123456789abcdef')
    assert set(data['context'])=={'authorization_id','authorization_no','release_id','snapshot_id','release_decision_id','distribution_id','delivery_package_id','package_revision','customer_id','project_id','site_code','line_code','purpose','batch_limit','restriction_note','creation_event_id','creator_principal_id'}
    assert data['context']['creator_principal_id']==str(ids['people']['creator'])
    assert data['context']['snapshot_id']==str(ids['snapshot']) and data['context']['batch_limit']==2
    assert db.get(SoftwareAuthorization,ids['authorization']).status=='DRAFT' and counts(db)==before


def test_second_person_approval_has_one_original_event_and_exact_replay(approval_db):
    db,ids=approval_db;values=body(db,ids);before=counts(db);first=submit(db,ids,values)
    assert first['applied_status']=='APPROVED' and first['request_id']==str(values['request_id'])
    assert first['creator_principal_id']==str(ids['people']['creator']) and first['approver_principal_id']==str(ids['people']['approver'])
    assert first['audit_event_no']=='EVT-PAA-'+values['request_id'].hex
    row=db.get(SoftwareAuthorization,ids['authorization']);assert row.status=='APPROVED' and row.approved_at is not None
    assert counts(db)==before+1 and submit(db,ids,values)==first and counts(db)==before+1
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==first['audit_event_no']))
    assert (event.event_type,event.action,event.entity_type,event.entity_id)==('AUTHORIZATION_APPROVED','APPROVED','SOFTWARE_AUTHORIZATION',ids['authorization'])
    assert event.actor_principal_id==ids['people']['approver']


@pytest.mark.parametrize('name',['creator','admin','foreign','service'])
def test_creator_admin_only_foreign_scope_and_service_cannot_approve(approval_db,name):
    db,ids=approval_db;values=body(db,ids);before=counts(db)
    for operation in [lambda:prepare(db,ids,name),lambda:submit(db,ids,values,name)]:
        with pytest.raises(HTTPException) as error:operation()
        assert error.value.status_code in (401,403)
        assert counts(db)==before and db.get(SoftwareAuthorization,ids['authorization']).status=='DRAFT'


@pytest.mark.parametrize('case',['disabled_mode','anonymous','disabled_principal','suspended_membership'])
def test_current_identity_and_scope_required_before_original_replay(approval_db,monkeypatch,case):
    db,ids=approval_db;values=body(db,ids);submit(db,ids,values);before=counts(db);request=actor_request(db,ids)
    if case=='disabled_mode':monkeypatch.setattr(settings,'auth_mode','disabled')
    elif case=='anonymous':request=Request({'type':'http','headers':[]})
    elif case=='disabled_principal':db.get(SecurityPrincipal,ids['people']['approver']).status='DISABLED';db.commit()
    else:db.get(ProjectMembership,ids['grants']['approver']).status='SUSPENDED';db.commit()
    with pytest.raises(HTTPException) as error:submit(db,ids,values,request=request)
    assert error.value.status_code in (401,403) and counts(db)==before


@pytest.mark.parametrize('invalid',['revoked','expired','wrong_token','wrong_principal'])
def test_browser_session_revalidated_before_replay(approval_db,invalid):
    db,ids=approval_db;values=body(db,ids);submit(db,ids,values);now=datetime.now(timezone.utc);sid=uuid.uuid4()
    db.add(BrowserSession(id=sid,principal_id=ids['people']['other' if invalid=='wrong_principal' else 'approver'],token_digest=hashlib.sha256((TOKEN+'wrong' if invalid=='wrong_token' else TOKEN).encode()).hexdigest(),created_at=now-timedelta(minutes=2),expires_at=now+timedelta(minutes=-1 if invalid=='expired' else 5),revoked_at=now if invalid=='revoked' else None));db.commit();before=counts(db)
    with pytest.raises(HTTPException) as error:submit(db,ids,values,request=actor_request(db,ids,session_id=sid))
    assert error.value.status_code==401 and counts(db)==before


@pytest.mark.parametrize('case',['missing','legacy','wrong_entity','wrong_request','wrong_snapshot'])
def test_untrusted_or_missing_creator_evidence_fails_closed(approval_db,case):
    db,ids=approval_db;values=body(db,ids);event=db.scalar(select(AuditEvent).where(AuditEvent.event_no=='EVT-PA-'+ids['authorization'].hex))
    if case=='missing':db.delete(event)
    elif case=='legacy':event.actor_principal_id=None;event.payload_json={**event.payload_json,'actor_source':'NOT_PROVIDED'}
    elif case=='wrong_entity':event.entity_id=uuid.uuid4()
    elif case=='wrong_request':event.payload_json={**event.payload_json,'request':{**event.payload_json['request'],'site_code':'FORGED'}}
    else:event.payload_json={**event.payload_json,'snapshot_id':str(uuid.uuid4())}
    db.commit();before=counts(db)
    with pytest.raises(HTTPException):submit(db,ids,values)
    assert counts(db)==before and db.get(SoftwareAuthorization,ids['authorization']).status=='DRAFT'


@pytest.mark.parametrize('case',['digest','restriction','new_decision','cancelled_distribution','draft_snapshot'])
def test_stale_context_or_ineligible_chain_cannot_approve(approval_db,case):
    db,ids=approval_db;values=body(db,ids)
    if case=='digest':values['expected_context_digest']='0'*64
    elif case=='restriction':db.get(SoftwareAuthorization,ids['authorization']).restriction_note='Changed'
    elif case=='new_decision':
        old=db.get(ReleaseDecision,ids['decision']);db.add(ReleaseDecision(decision_no='PAA-HOLD',release_id=old.release_id,snapshot_id=old.snapshot_id,approval_request_id=old.approval_request_id,readiness_status='READY',decision='HOLD',decided_by='Synthetic reviewer',supersedes_id=old.id,correction_reason='New hold after context'))
    elif case=='cancelled_distribution':db.get(Distribution,ids['distribution']).status='CANCELLED'
    else:db.get(ReleaseSnapshot,ids['snapshot']).status='DRAFT'
    db.commit();before=counts(db)
    with pytest.raises(HTTPException):submit(db,ids,values)
    assert counts(db)==before and db.get(SoftwareAuthorization,ids['authorization']).status=='DRAFT'


@pytest.mark.parametrize('case',['reason','digest','actor','new_key'])
def test_original_request_key_and_single_approval_are_exact(approval_db,case):
    db,ids=approval_db;values=body(db,ids);submit(db,ids,values);before=counts(db);name='approver'
    if case=='reason':values['reason']='Different reason'
    elif case=='digest':values['expected_context_digest']='0'*64
    elif case=='actor':name='other'
    else:values['request_id']=uuid.uuid4()
    with pytest.raises(HTTPException) as error:submit(db,ids,values,name)
    assert error.value.status_code==409 and counts(db)==before


@pytest.mark.parametrize('failure',['audit_before','audit_after','commit'])
def test_approval_status_and_audit_rollback_atomically(approval_db,monkeypatch,failure):
    db,ids=approval_db;values=body(db,ids);before=counts(db)
    with monkeypatch.context() as patch:
        original=AuditEventService.record
        def fail(service,**kwargs):
            if failure=='audit_after':original(service,**kwargs)
            raise RuntimeError('injected approval failure')
        if failure=='commit':patch.setattr(db,'commit',lambda:(_ for _ in ()).throw(RuntimeError('injected approval failure')))
        else:patch.setattr(AuditEventService,'record',fail)
        with pytest.raises(RuntimeError,match='injected'):submit(db,ids,values)
    assert not db.in_transaction() and counts(db)==before
    db.expire_all();row=db.get(SoftwareAuthorization,ids['authorization']);assert row.status=='DRAFT' and row.approved_at is None
    assert submit(db,ids,values)['applied_status']=='APPROVED'


def test_historical_receipt_does_not_undo_later_revocation(approval_db):
    from app.services.revocation import RevocationService
    db,ids=approval_db;values=body(db,ids);first=submit(db,ids,values)
    RevocationService(db).revoke('AUTHORIZATION',ids['authorization'],'Synthetic later revocation',request_id=uuid.uuid4())
    before=counts(db);assert submit(db,ids,values)==first and counts(db)==before
    with pytest.raises(HTTPException):submit(db,ids,{**values,'request_id':uuid.uuid4()})


@pytest.fixture
def approval_client(approval_db,monkeypatch):
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import auth, main
    from app.core.db import get_db
    from test_auth import AUDIENCE,signed_token
    db,ids=approval_db;sessions=sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(auth,'jwks_client',lambda *_:SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(auth,'SessionLocal',sessions)
    for name,value in {'oidc_audience':AUDIENCE,'oidc_jwks_url':ISSUER+'/keys','oidc_leeway_seconds':0}.items():monkeypatch.setattr(settings,name,value)
    token=signed_token(key,iss=ISSUER,sub='paa-approver')
    def route_db():
        with sessions() as route_session:yield route_session
    previous=dict(main.app.dependency_overrides);main.app.dependency_overrides[get_db]=route_db
    try:
        with TestClient(main.app) as client:yield client,{'Authorization':'Bearer '+token},ids
    finally:main.app.dependency_overrides.clear();main.app.dependency_overrides.update(previous)


def test_real_middleware_private_context_and_approval(approval_client):
    client,headers,ids=approval_client;path='/api/v1/authorizations/'+ids['number']
    context=client.get(path+'/approval-context',headers=headers);assert context.status_code==200,context.text
    assert context.headers['cache-control']=='private, no-store' and 'authorization' in context.headers['vary'].lower() and 'x-browser-session' in context.headers['vary'].lower()
    data={'request_id':str(uuid.uuid4()),'expected_context_digest':context.json()['context_digest'],'reason':'Reviewed synthetic production chain'}
    response=client.post(path+'/approval',headers=headers,json=data);assert response.status_code==200,response.text
    assert response.json()['applied_status']=='APPROVED' and response.headers['cache-control']=='private, no-store'


@pytest.mark.parametrize('method,suffix',[('GET','/approval-context'),('HEAD','/approval-context'),('GET','/approval-context/'),('HEAD','/approval-context/'),('POST','/approval'),('GET','/approval'),('HEAD','/approval/')])
def test_private_route_never_public_with_auth_disabled(approval_client,monkeypatch,method,suffix):
    client,_headers,ids=approval_client;monkeypatch.setattr(settings,'auth_mode','disabled')
    response=client.request(method,'/api/v1/authorizations/'+ids['number']+suffix)
    assert response.status_code==401 and response.headers['cache-control']=='private, no-store'


def test_read_only_allows_private_context_but_never_approval(approval_client,monkeypatch):
    client,headers,ids=approval_client;monkeypatch.setattr(settings,'read_only_mode',True);path='/api/v1/authorizations/'+ids['number']
    assert client.get(path+'/approval-context',headers=headers).status_code==200
    response=client.post(path+'/approval',headers=headers,json={});assert response.status_code==403 and response.json()['detail']=='read_only_mode'


@pytest.mark.parametrize('patch',[{'request_id':'invalid'},{'expected_context_digest':'A'*64},{'reason':''},{'reason':'x'*2001},{'actor_name':'spoof'},{'approved_by':'spoof'}])
def test_request_model_rejects_invalid_or_extra_fields(approval_client,patch):
    client,headers,ids=approval_client;path='/api/v1/authorizations/'+ids['number'];context=client.get(path+'/approval-context',headers=headers).json()
    body={'request_id':str(uuid.uuid4()),'expected_context_digest':context['context_digest'],'reason':'Reviewed exact frozen production chain',**patch}
    response=client.post(path+'/approval',headers=headers,json=body);assert response.status_code==422


def test_admin_with_explicit_project_role_still_cannot_approve_own_creation(approval_db):
    db,ids=approval_db;values=body(db,ids)
    db.add(GlobalRoleAssignment(principal_id=ids['people']['creator'],role='PLATFORM_ADMIN'));db.commit();before=counts(db)
    with pytest.raises(HTTPException) as error:submit(db,ids,values,'creator')
    assert error.value.status_code==403 and error.value.detail=='creator_cannot_approve' and counts(db)==before


def test_service_validation_never_normalizes_or_accepts_malformed_confirmation(approval_db):
    db,ids=approval_db;values=body(db,ids);before=counts(db)
    for patch in [{'request_id':str(values['request_id'])},{'expected_context_digest':'A'*64},{'reason':' '},{'reason':' padded reason '},{'reason':'x'*2001}]:
        with pytest.raises(HTTPException) as error:submit(db,ids,{**values,**patch})
        assert error.value.status_code==422 and counts(db)==before


def test_authenticated_creation_without_request_key_preserves_known_creator(approval_db):
    db,ids=approval_db;original=db.get(SoftwareAuthorization,ids['authorization']);creator=db.get(SecurityPrincipal,ids['people']['creator'])
    actor=ActorContext(creator.display_name,creator.id,creator.display_name,None,'AUTHENTICATED_PRINCIPAL')
    row=DistributionService(db).create_authorization(original.release_id,original.distribution_id,'PAA-NOKEY',original.customer_id,original.project_id,original.site_code,original.line_code,actor_context=actor)
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no=='EVT-PA-'+row.id.hex));assert event.payload_json['request'] is None
    newids={**ids,'number':row.authorization_no,'authorization':row.id};values=body(db,newids)
    assert submit(db,newids,values)['creator_principal_id']==str(creator.id)


def test_existing_approved_row_without_new_approval_evidence_is_not_reapproved(approval_db):
    db,ids=approval_db;values=body(db,ids);row=db.get(SoftwareAuthorization,ids['authorization']);row.status='APPROVED';db.commit();before=counts(db)
    with pytest.raises(HTTPException) as error:submit(db,ids,values)
    assert error.value.status_code==409 and counts(db)==before
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='AUTHORIZATION_APPROVED'))==0


def test_new_valid_same_actor_browser_session_can_recover_original_receipt(approval_db):
    db,ids=approval_db;values=body(db,ids);original=submit(db,ids,values);before=counts(db)
    for _ in range(2):
        sid=uuid.uuid4();now=datetime.now(timezone.utc)
        db.add(BrowserSession(id=sid,principal_id=ids['people']['approver'],token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),created_at=now,expires_at=now+timedelta(minutes=5)));db.commit()
        assert submit(db,ids,values,request=actor_request(db,ids,session_id=sid))==original
        assert counts(db)==before


def test_approved_delivery_package_remains_eligible_for_dual_person_approval(approval_db):
    db,ids=approval_db
    package=db.get(DeliveryPackage,ids['package']);package.status='APPROVED';db.commit()
    values=body(db,ids);before=counts(db)
    receipt=submit(db,ids,values)
    assert receipt['applied_status']=='APPROVED'
    assert receipt['creator_principal_id']!=receipt['approver_principal_id']
    assert counts(db)==before+1
    assert db.get(DeliveryPackage,ids['package']).status=='APPROVED'
    assert submit(db,ids,values)==receipt and counts(db)==before+1
