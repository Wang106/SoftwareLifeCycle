"""Signed global role lifecycle, exact retries and effective authorization."""
import uuid

import pytest
from sqlalchemy import func, select

from app import main
from app.authorization import _has_global_admin
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, SecurityPrincipal
from app.services.audit import AuditEventError, AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg
from test_admin_grants import admin

ROOT = '/api/v1/security/admin/global-roles'


def body(ids, role='PLATFORM_ADMIN'):
    return {'event_no': 'GR-'+uuid.uuid4().hex, 'grant_id': str(uuid.uuid4()),
            'principal_id': str(ids['principal']), 'role': role, 'reason': 'Approved global access review'}


def transition(status='ACTIVE', event=None):
    return {'event_no': event or 'GS-'+uuid.uuid4().hex, 'expected_status': 'SUSPENDED' if status=='ACTIVE' else 'ACTIVE',
            'status': status, 'reason': 'Approved global access review'}


def active_grant(sessions, principal_id):
    with sessions() as db:
        return db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.principal_id==principal_id,
                                                            GlobalRoleAssignment.role=='PLATFORM_ADMIN'))


def post(client, key, path, data):
    response=client.post(path, json=data, headers=admin(key))
    private(response)
    return response


def test_register_resume_suspend_replay_and_minimal_history(identity_client,monkeypatch):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    response=post(client,key,ROOT,data)
    assert response.status_code==200,response.text
    assert response.json()=={'grant_id':data['grant_id'],'scope':'GLOBAL','principal_id':data['principal_id'],
        'role':'PLATFORM_ADMIN','applied_status':'SUSPENDED','current_status':'SUSPENDED','replayed':False,
        'audit_event_no':data['event_no']}
    with sessions() as db:
        assert not _has_global_admin(db,ids['principal'])
    assert client.get('/api/v1/security/me',headers=headers(key)).json()['active_grant_counts']['GLOBAL']==1
    assert client.get('/api/v1/security/admin/grants?scope=GLOBAL&status=SUSPENDED',headers=admin(key)).json()['total']==1
    resume=transition()
    assert post(client,key,f"{ROOT}/{data['grant_id']}/status",resume).status_code==200
    replayed=post(client,key,ROOT,data).json()
    assert replayed['replayed'] and replayed['applied_status']=='SUSPENDED' and replayed['current_status']=='ACTIVE'
    with sessions() as db:
        assert _has_global_admin(db,ids['principal'])
    assert client.get('/api/v1/security/admin/grants?scope=GLOBAL',headers=headers(key)).status_code==200
    suspend=transition('SUSPENDED')
    assert post(client,key,f"{ROOT}/{data['grant_id']}/status",suspend).status_code==200
    replayed=post(client,key,f"{ROOT}/{data['grant_id']}/status",resume).json()
    assert replayed['replayed'] and replayed['applied_status']=='ACTIVE' and replayed['current_status']=='SUSPENDED'
    assert client.get('/api/v1/security/admin/grants?scope=GLOBAL',headers=headers(key)).status_code==403
    response=client.get(f"/api/v1/security/admin/grants/GLOBAL/{data['grant_id']}/history?limit=1",headers=admin(key))
    private(response)
    history=response.json()
    assert history['total']==2 and history['next_offset']==1
    assert history['coverage']=='GLOBAL_ROLE_STATUS_CHANGED_ONLY' and history['items'][0]['status']=='SUSPENDED'
    assert history['items'][0]['actor_principal_id']==str(ids['other'])
    for secret in ['private@example.com','user-123','identity.example.com',headers(key)['Authorization'],'payload_json']:
        assert secret not in response.text
    with sessions() as db:
        events=list(db.scalars(select(AuditEvent).where(AuditEvent.entity_id==uuid.UUID(data['grant_id']))))
        assert len(events)==3
        assert all(event.actor_principal_id==ids['other'] for event in events)
        assert set(events[0].payload_json)<= {'grant_id','principal_id','role','status','reason','expected_status'}


@pytest.mark.parametrize('decoy',['none','disabled','suspended','wrong_issuer','auditor'])
def test_last_effective_admin_is_protected_even_with_ineffective_decoys(identity_client,monkeypatch,decoy):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    grant=active_grant(sessions,ids['other'])
    if decoy!='none':
        with sessions() as db:
            target=db.get(SecurityPrincipal,ids['principal'])
            if decoy=='disabled':target.status='DISABLED'
            if decoy=='wrong_issuer':target.issuer='https://wrong.example.com'
            if decoy!='auditor':db.add(GlobalRoleAssignment(principal_id=target.id,role='PLATFORM_ADMIN',
                status='SUSPENDED' if decoy=='suspended' else 'ACTIVE'))
            db.commit()
    response=post(client,key,f'{ROOT}/{grant}/status',transition('SUSPENDED'))
    assert response.status_code==409 and response.json()['detail']=='last_active_admin_protected'
    with sessions() as db:
        assert db.get(GlobalRoleAssignment,grant).status=='ACTIVE'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==grant))==0


@pytest.mark.parametrize('self_suspend',[False,True])
def test_suspension_removes_all_admin_authority_and_keeps_other_roles(identity_client,monkeypatch,self_suspend):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    with sessions() as db:
        db.add(GlobalRoleAssignment(principal_id=ids['principal'],role='PLATFORM_ADMIN'));db.commit()
    target=ids['other'] if self_suspend else ids['principal']
    grant=active_grant(sessions,target)
    response=post(client,key,f'{ROOT}/{grant}/status',transition('SUSPENDED'))
    assert response.status_code==200,response.text
    auth=admin(key) if self_suspend else headers(key)
    assert client.get('/api/v1/security/admin/grants?scope=GLOBAL',headers=auth).status_code==403
    assert client.post(ROOT,json=body(ids),headers=auth).status_code==403
    with sessions() as db:
        assert not _has_global_admin(db,target)
    if not self_suspend:
        summary=client.get('/api/v1/security/me',headers=auth).json()
        assert summary['active_grant_counts']=={'GLOBAL':1,'PROJECT':1,'SOFTWARE':1}


@pytest.mark.parametrize('operation',['register','status'])
def test_every_control_is_read_only_blocked_oidc_required_and_admin_only(identity_client,monkeypatch,operation):
    client,sessions,ids,key,_=identity_client
    path=ROOT if operation=='register' else f"{ROOT}/{active_grant(sessions,ids['other'])}/status"
    data=body(ids) if operation=='register' else transition('SUSPENDED')
    assert post(client,key,path,data).status_code==403
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    for auth,expected in [({},401),(headers(key),403),(admin(key,aud='wrong'),401),
                          ({**admin(key),'X-Browser-Session':str(uuid.uuid4())},401)]:
        response=client.post(path,json=data,headers=auth)
        assert response.status_code==expected,response.text
        private(response)
    monkeypatch.setattr(main.settings,'auth_mode','disabled')
    assert post(client,key,path,data).status_code==401


@pytest.mark.parametrize('defect',['missing','inactive','issuer','duplicate_id','duplicate_role','event','role','extra','reason','del'])
def test_registration_preconditions_reject_without_mutation(identity_client,monkeypatch,defect):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    expected=409
    with sessions() as db:
        target=db.get(SecurityPrincipal,ids['principal'])
        if defect=='inactive':target.status='DISABLED'
        if defect=='issuer':target.issuer='https://wrong.example.com'
        if defect=='duplicate_id':data['grant_id']=str(active_grant(sessions,ids['other']))
        if defect=='duplicate_role':data['role']='AUDITOR'
        if defect=='event':AuditEventService(db).record(event_no=data['event_no'],event_type='UNRELATED',action='NOISE',
            entity_type='NOISE',entity_ref='unrelated',actor_name='Test',summary='Other event')
        db.commit()
    if defect=='missing':data['principal_id']=str(uuid.uuid4());expected=404
    if defect=='role':data['role']='REVIEWER';expected=422
    if defect=='extra':data['status']='ACTIVE';expected=422
    if defect=='reason':data['reason']='bad';expected=422
    if defect=='del':data['reason']='bad\x7freason';expected=422
    response=post(client,key,ROOT,data)
    assert response.status_code==expected,response.text
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(GlobalRoleAssignment))==2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='GLOBAL_ROLE_REGISTERED'))==0


@pytest.mark.parametrize('defect',['reason','role','principal_id','grant_id','other_actor'])
def test_registration_event_cannot_be_rebound(identity_client,monkeypatch,defect):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    assert post(client,key,ROOT,data).status_code==200
    changed={**data}
    if defect=='other_actor':
        with sessions() as db:
            db.get(GlobalRoleAssignment,uuid.UUID(data['grant_id'])).status='ACTIVE';db.commit()
        response=client.post(ROOT,json=data,headers=headers(key))
    else:
        changed[defect]={'reason':'Another approved review','role':'AUDITOR','principal_id':str(ids['other']),
                         'grant_id':str(uuid.uuid4())}[defect]
        response=post(client,key,ROOT,changed)
    assert response.status_code==409 and response.json()['detail']=='audit_event_conflict'


@pytest.mark.parametrize('defect',['inactive','issuer','missing','stale','same','extra'])
def test_status_preconditions(identity_client,monkeypatch,defect):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    assert post(client,key,ROOT,data).status_code==200
    grant=data['grant_id'];change=transition();expected=409
    with sessions() as db:
        target=db.get(SecurityPrincipal,ids['principal'])
        if defect=='inactive':target.status='DISABLED'
        if defect=='issuer':target.issuer='https://wrong.example.com'
        db.commit()
    if defect=='missing':grant=str(uuid.uuid4());expected=404
    if defect=='stale':change=transition('SUSPENDED')
    if defect=='same':change['expected_status']='ACTIVE';expected=422
    if defect=='extra':change['actor_name']='untrusted';expected=422
    response=post(client,key,f'{ROOT}/{grant}/status',change)
    assert response.status_code==expected,response.text
    with sessions() as db:
        assert db.get(GlobalRoleAssignment,uuid.UUID(data['grant_id'])).status=='SUSPENDED'


@pytest.mark.parametrize('operation',['register','status'])
@pytest.mark.parametrize('failure',[RuntimeError,AuditEventError])
def test_audit_failure_rolls_back_the_entire_control(identity_client,monkeypatch,operation,failure):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    if operation=='status':assert post(client,key,ROOT,data).status_code==200
    def fail(*args,**kwargs):raise failure('forced audit failure')
    monkeypatch.setattr(AuditEventService,'record',fail)
    if failure==RuntimeError:
        with pytest.raises(RuntimeError,match='forced audit failure'):
            post(client,key,ROOT if operation=='register' else f"{ROOT}/{data['grant_id']}/status",
                 data if operation=='register' else transition())
    else:
        assert post(client,key,ROOT if operation=='register' else f"{ROOT}/{data['grant_id']}/status",
                    data if operation=='register' else transition()).status_code==409
    with sessions() as db:
        row=db.get(GlobalRoleAssignment,uuid.UUID(data['grant_id']))
        assert row is None if operation=='register' else row.status=='SUSPENDED'


@pytest.mark.parametrize('principal_type',['USER','SERVICE'])
@pytest.mark.parametrize('role',['PLATFORM_ADMIN','AUDITOR'])
def test_both_global_roles_register_suspended_for_active_configured_identities(identity_client,monkeypatch,principal_type,role):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    with sessions() as db:
        target=SecurityPrincipal(issuer=main.settings.oidc_issuer_url,subject='recipient-'+uuid.uuid4().hex,
            principal_type=principal_type,display_name='Approved recipient')
        db.add(target);db.commit();identifier=target.id
    data=body({**ids,'principal':identifier},role)
    response=post(client,key,ROOT,data)
    assert response.status_code==200 and response.json()['current_status']=='SUSPENDED'
    response=post(client,key,f"{ROOT}/{data['grant_id']}/status",transition())
    assert response.status_code==200 and response.json()['current_status']=='ACTIVE'
    with sessions() as db:
        assert _has_global_admin(db,identifier)==(role=='PLATFORM_ADMIN')


@pytest.mark.parametrize('field',['reason','transition'])
def test_status_event_exact_request_cannot_be_changed(identity_client,monkeypatch,field):
    client,sessions,ids,key,_=identity_client
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    data=body(ids)
    assert post(client,key,ROOT,data).status_code==200
    change=transition()
    path=f"{ROOT}/{data['grant_id']}/status"
    assert post(client,key,path,change).status_code==200
    if field=='reason':change['reason']='Changed approval reason'
    else:change.update(expected_status='ACTIVE',status='SUSPENDED')
    response=post(client,key,path,change)
    assert response.status_code==409 and response.json()['detail']=='audit_event_conflict'
    with sessions() as db:
        assert db.get(GlobalRoleAssignment,uuid.UUID(data['grant_id'])).status=='ACTIVE'
