"""Signed exact role creation: suspended-first, retries, scope and atomic audit."""
import json
import uuid

import pytest
from sqlalchemy import func, select
from starlette.requests import Request

from app import main
from app.auth import AuthenticatedPrincipal
from app.authorization import AuthorizationError, _require_any_scope
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.security_roles import PROJECT_ROLES, SOFTWARE_ROLES
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg

ROOT = '/api/v1/security/admin/memberships'


def admin(key): return headers(key,sub='other')


def model_for(scope): return ProjectMembership if scope == 'PROJECT' else SoftwareMembership


def recipient(sessions, *, kind='USER', status='ACTIVE', issuer=None, subject='fresh-grantee'):
    with sessions() as db:
        row = SecurityPrincipal(issuer=issuer or main.settings.oidc_issuer_url,subject=subject,
            principal_type=kind,display_name='New recipient',status=status)
        db.add(row);db.commit();return row.id


def body_for(ids,identifier,scope='PROJECT',**overrides):
    return {'event_no':'MEMBER-REGISTER','reason':'Register approved exact role',
        'membership_id':str(uuid.uuid4()),'principal_id':str(identifier),
        'scope_id':str(ids['project' if scope == 'PROJECT' else 'software']),
        'role':'PROJECT_VIEWER' if scope == 'PROJECT' else 'SOFTWARE_VIEWER',**overrides}


def count(db):
    return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='MEMBERSHIP_REGISTERED'))


def scope_guard(db,identifier,scope,scope_id,role):
    row=db.get(SecurityPrincipal,identifier)
    request=Request({'type':'http','headers':[]})
    request.state.principal=AuthenticatedPrincipal(row.id,row.issuer,row.subject,row.principal_type,row.display_name,None)
    _require_any_scope(request,db,**({'project_ids':[scope_id],'project_roles':frozenset({role})}
        if scope=='PROJECT' else {'software_ids':[scope_id],'software_roles':frozenset({role})}))


@pytest.mark.parametrize('scope,role', [('PROJECT',value) for value in sorted(PROJECT_ROLES)]+[('SOFTWARE',value) for value in sorted(SOFTWARE_ROLES)])
def test_every_scoped_role_registers_suspended_then_exact_resume_authorizes(identity_client,monkeypatch,scope,role):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions)
    body=body_for(ids,identifier,scope,role=role)
    response=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    assert response.status_code==200,response.text
    private(response)
    assert response.json()=={'membership_id':body['membership_id'],'scope':scope,'principal_id':str(identifier),
        'scope_id':body['scope_id'],'role':role,'applied_status':'SUSPENDED','current_status':'SUSPENDED',
        'replayed':False,'audit_event_no':body['event_no']}
    with sessions() as db:
        row=db.get(model_for(scope),uuid.UUID(body['membership_id']))
        assert row.principal_id==identifier and row.status=='SUSPENDED'
        with pytest.raises(AuthorizationError):scope_guard(db,identifier,scope,uuid.UUID(body['scope_id']),role)
        event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==body['event_no']))
        assert event.actor_principal_id==ids['other'] and event.entity_id==row.id and event.entity_ref==str(row.id)
        assert event.entity_type==scope+'_MEMBERSHIP' and count(db)==1
        for secret in ['fresh-grantee',main.settings.oidc_issuer_url,admin(key)['Authorization']]:
            assert secret not in json.dumps(event.payload_json) and secret not in response.text
    catalog=client.get('/api/v1/security/admin/grants',params={'scope':scope,'principal_id':str(identifier)},headers=admin(key))
    assert catalog.status_code==200 and catalog.json()['total']==1
    assert catalog.json()['items'][0]['effective'] is False
    history='/api/v1/security/admin/grants/'+scope+'/'+body['membership_id']+'/history'
    assert client.get(history,headers=admin(key)).json()['total']==0  # Status history excludes registration audit.
    resume={'event_no':'MEMBER-RESUME','expected_status':'SUSPENDED','status':'ACTIVE','reason':'Enable after access review'}
    assert client.post(ROOT+'/'+scope+'/'+body['membership_id']+'/status',json=resume,headers=admin(key)).status_code==200
    with sessions() as db:
        scope_guard(db,identifier,scope,uuid.UUID(body['scope_id']),role)
        with pytest.raises(AuthorizationError):scope_guard(db,identifier,scope,uuid.uuid4(),role)
    assert client.get(history,headers=admin(key)).json()['total']==1
    retry=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    assert retry.status_code==200 and retry.json()['replayed'] is True
    assert retry.json()['applied_status']=='SUSPENDED' and retry.json()['current_status']=='ACTIVE'
    with sessions() as db:assert count(db)==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('kind',['USER','SERVICE'])
def test_user_and_service_registration_replay_after_principal_disable_does_not_mutate(identity_client,monkeypatch,scope,kind):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions,kind=kind)
    body=body_for(ids,identifier,scope)
    assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
    disable={'event_no':'DISABLE-RECIPIENT','expected_status':'ACTIVE','status':'DISABLED','reason':'Disable recipient pending review'}
    assert client.post('/api/v1/security/admin/principals/'+str(identifier)+'/status',json=disable,headers=admin(key)).status_code==200
    retry=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    assert retry.status_code==200 and retry.json()['replayed'] is True
    assert client.get('/api/v1/security/me',headers=headers(key,sub='fresh-grantee')).status_code==401
    with sessions() as db:
        assert db.get(model_for(scope),uuid.UUID(body['membership_id'])).status=='SUSPENDED'
        assert db.get(SecurityPrincipal,identifier).status=='DISABLED' and count(db)==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('field',['membership_id','principal_id','scope_id','role','reason','scope'])
def test_changed_replay_request_is_conflict_without_new_role(identity_client,monkeypatch,scope,field):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions)
    body=body_for(ids,identifier,scope)
    assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
    changed=body.copy();other_scope=scope
    if field=='principal_id':changed[field]=str(recipient(sessions,subject='another-recipient'))
    elif field in ['membership_id','scope_id']:changed[field]=str(uuid.uuid4())
    elif field=='role':changed[field]='CONTRIBUTOR' if scope=='PROJECT' else 'SOFTWARE_MAINTAINER'
    elif field=='reason':changed[field]='Changed valid review reason'
    else:
        other_scope='SOFTWARE' if scope=='PROJECT' else 'PROJECT'
        changed=body_for(ids,identifier,other_scope,membership_id=body['membership_id'])
    response=client.post(ROOT+'/'+other_scope,json=changed,headers=admin(key))
    assert response.status_code==409 and response.json()['detail']=='audit_event_conflict'
    private(response)
    with sessions() as db:assert count(db)==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('duplicate',['uuid','exact_role'])
def test_new_key_never_adopts_or_updates_existing_membership(identity_client,monkeypatch,scope,duplicate):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions);body=body_for(ids,identifier,scope)
    assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
    second={**body,'event_no':'DIFFERENT-KEY'}
    if duplicate=='exact_role':second['membership_id']=str(uuid.uuid4())
    else:second['role']='CONTRIBUTOR' if scope=='PROJECT' else 'SOFTWARE_MAINTAINER'
    response=client.post(ROOT+'/'+scope,json=second,headers=admin(key))
    assert response.status_code==409 and response.json()['detail']=='membership_registration_conflict'
    with sessions() as db:assert count(db)==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('case',['missing_principal','disabled_principal','different_issuer','missing_target','wrong_target_type','self_admin','other_admin'])
def test_recipient_and_target_preconditions(identity_client,monkeypatch,scope,case):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions,status='DISABLED' if case=='disabled_principal' else 'ACTIVE',
        issuer='https://other.example.com' if case=='different_issuer' else None)
    if case=='missing_principal':identifier=uuid.uuid4()
    if case=='self_admin':identifier=ids['other']
    if case=='other_admin':
        with sessions() as db:db.add(GlobalRoleAssignment(principal_id=identifier,role='PLATFORM_ADMIN'));db.commit()
    body=body_for(ids,identifier,scope)
    if case=='missing_target':body['scope_id']=str(uuid.uuid4())
    if case=='wrong_target_type':body['scope_id']=str(ids['software' if scope=='PROJECT' else 'project'])
    response=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    details={'missing_principal':(404,'principal_not_found'),'disabled_principal':(409,'recipient_inactive'),
        'different_issuer':(409,'recipient_issuer_mismatch'),'missing_target':(404,'scope_target_not_found'),
        'wrong_target_type':(404,'scope_target_not_found'),'self_admin':(409,'admin_recipient_protected'),
        'other_admin':(409,'admin_recipient_protected')}
    assert (response.status_code,response.json()['detail'])==details[case],response.text
    private(response)
    with sessions() as db:assert count(db)==0


@pytest.mark.parametrize('field,value',[('scope','GLOBAL'),('scope','project'),('role','PLATFORM_ADMIN'),('role','AUDITOR'),
    ('role','SOFTWARE_VIEWER'),('status','ACTIVE'),('scope','SOFTWARE'),('actor_name','spoofed'),
    ('issuer','https://wrong.example.com'),('membership_id','invalid'),('principal_id','invalid'),('scope_id','invalid'),
    ('event_no','invalid key'),('event_no','x'*51),('reason','short'),('reason',' '),('reason','x'*501),('reason','control\nreason')])
def test_strict_validation_and_role_scope_binding(identity_client,monkeypatch,field,value):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body=body_for(ids,recipient(sessions))
    scope='PROJECT'
    if field=='scope':scope=value
    else:body[field]=value
    if field=='reason' and value=='short':body[field]='four'
    response=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    assert response.status_code==422,response.text
    private(response)
    with sessions() as db:assert count(db)==0


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('denial',['readonly','auth_disabled','anonymous','nonadmin','disabled_admin','invalid_session'])
def test_all_denials_are_private_and_leave_no_grant(identity_client,monkeypatch,scope,denial):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body=body_for(ids,recipient(sessions),scope);auth_headers=admin(key);status=401
    if denial=='readonly':monkeypatch.setattr(main.settings,'read_only_mode',True);status=403
    elif denial=='auth_disabled':monkeypatch.setattr(main.settings,'auth_mode','disabled')
    elif denial=='anonymous':auth_headers={}
    elif denial=='nonadmin':auth_headers=headers(key);status=403
    elif denial=='disabled_admin':
        with sessions() as db:db.get(SecurityPrincipal,ids['other']).status='DISABLED';db.commit()
    else:auth_headers['X-Browser-Session']=str(uuid.uuid4())
    response=client.post(ROOT+'/'+scope,json=body,headers=auth_headers)
    assert response.status_code==status,response.text
    private(response)
    with sessions() as db:assert count(db)==0 and db.get(model_for(scope),uuid.UUID(body['membership_id'])) is None


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_audit_insert_failure_rolls_back_grant_and_evidence(identity_client,monkeypatch,scope):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body=body_for(ids,recipient(sessions),scope);record=AuditEventService.record
    def fail(*args,**kwargs):record(*args,**kwargs);raise RuntimeError('deliberate audit failure')
    monkeypatch.setattr(AuditEventService,'record',fail)
    with pytest.raises(RuntimeError,match='deliberate audit failure'):
        client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    with sessions() as db:assert count(db)==0 and db.get(model_for(scope),uuid.UUID(body['membership_id'])) is None


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_different_admin_cannot_claim_existing_registration_event(identity_client,monkeypatch,scope):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body=body_for(ids,recipient(sessions),scope)
    assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
    with sessions() as db:db.add(GlobalRoleAssignment(principal_id=ids['principal'],role='PLATFORM_ADMIN'));db.commit()
    response=client.post(ROOT+'/'+scope,json=body,headers=headers(key))
    assert response.status_code==409 and response.json()['detail']=='audit_event_conflict'
    with sessions() as db:assert count(db)==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_distinct_roles_and_targets_are_independent_exact_memberships(identity_client,monkeypatch,scope):
    from app.models.core import Project,SoftwareProduct
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions);first=body_for(ids,identifier,scope)
    with sessions() as db:
        target=(Project(customer_id=ids['customer'],project_code='OTHER-P',name='Other project') if scope=='PROJECT'
            else SoftwareProduct(supplier_id=db.get(SoftwareProduct,ids['software']).supplier_id,code='OTHER-SW',name='Other software'))
        db.add(target);db.commit();target_id=target.id
    bodies=[first,{**first,'event_no':'SECOND-ROLE','membership_id':str(uuid.uuid4()),
        'role':'CONTRIBUTOR' if scope=='PROJECT' else 'SOFTWARE_MAINTAINER'},
        {**first,'event_no':'SECOND-TARGET','membership_id':str(uuid.uuid4()),'scope_id':str(target_id)}]
    for body in bodies:assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
    catalog=client.get('/api/v1/security/admin/grants',params={'scope':scope,'principal_id':str(identifier)},headers=admin(key)).json()
    assert catalog['total']==3 and all(row['status']=='SUSPENDED' for row in catalog['items'])
    with sessions() as db:assert count(db)==3


def test_same_uuid_in_different_scope_tables_never_confuses_replay_or_detail(identity_client,monkeypatch):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions);project=body_for(ids,identifier)
    software=body_for(ids,identifier,'SOFTWARE',event_no='SOFTWARE-REGISTER',membership_id=project['membership_id'])
    for scope,body in [('PROJECT',project),('SOFTWARE',software)]:
        assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).status_code==200
        assert client.post(ROOT+'/'+scope,json=body,headers=admin(key)).json()['replayed'] is True
        detail=client.get('/api/v1/security/admin/grants/'+scope+'/'+body['membership_id'],headers=admin(key)).json()
        assert detail['scope']==scope and detail['target']['id']==body['scope_id'] and detail['role']==body['role']
    with sessions() as db:assert count(db)==2


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_unrelated_global_audit_key_is_conflict_without_role_insert(identity_client,monkeypatch,scope):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    body=body_for(ids,recipient(sessions),scope)
    with sessions() as db:
        AuditEventService(db).record(event_no=body['event_no'],event_type='UNRELATED',action='READ',
            entity_type='OTHER',entity_id=uuid.UUID(body['membership_id']),entity_ref=body['membership_id'],
            summary='Unrelated evidence',payload=['unrelated'],actor_name='Historical actor')
        db.commit()
    response=client.post(ROOT+'/'+scope,json=body,headers=admin(key))
    assert response.status_code==409 and response.json()['detail']=='audit_event_conflict'
    with sessions() as db:assert count(db)==0 and db.get(model_for(scope),uuid.UUID(body['membership_id'])) is None


@pytest.mark.parametrize('operation',['role_register','principal_register','principal_status','membership_status'])
def test_late_audit_service_key_conflict_is_409_and_rolls_back_admin_mutation(identity_client,monkeypatch,operation):
    from app.services.audit import AuditEventError
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    identifier=recipient(sessions)
    body=body_for(ids,identifier)
    path=ROOT+'/PROJECT'
    expected='membership_registration_conflict'
    if operation=='principal_register':
        body={'principal_id':str(uuid.uuid4()),'subject':'register-late-conflict','principal_type':'USER',
            'display_name':'New principal','event_no':'LATE-AUDIT','reason':'Register approved local reference'}
        path='/api/v1/security/admin/principals';expected='principal_registration_conflict'
    elif operation=='principal_status':
        body={'event_no':'LATE-AUDIT','expected_status':'ACTIVE','status':'DISABLED','reason':'Disable pending review'}
        path='/api/v1/security/admin/principals/'+str(identifier)+'/status';expected='audit_event_conflict'
    elif operation=='membership_status':
        with sessions() as db:
            member=ProjectMembership(principal_id=identifier,project_id=ids['project'],role='PROJECT_VIEWER')
            db.add(member);db.commit();membership_id=member.id
        body={'event_no':'LATE-AUDIT','expected_status':'ACTIVE','status':'SUSPENDED','reason':'Suspend pending review'}
        path=ROOT+'/PROJECT/'+str(membership_id)+'/status';expected='audit_event_conflict'
    def conflict(*_,**__):raise AuditEventError('Audit event number already exists')
    monkeypatch.setattr(AuditEventService,'record',conflict)
    response=client.post(path,json=body,headers=admin(key))
    assert response.status_code==409 and response.json()['detail']==expected,response.text
    private(response)
    with sessions() as db:
        assert count(db)==0 and db.get(SecurityPrincipal,identifier).status=='ACTIVE'
        if operation=='role_register':assert db.get(ProjectMembership,uuid.UUID(body['membership_id'])) is None
        elif operation=='principal_register':assert db.get(SecurityPrincipal,uuid.UUID(body['principal_id'])) is None
        elif operation=='membership_status':assert db.get(ProjectMembership,membership_id).status=='ACTIVE'
