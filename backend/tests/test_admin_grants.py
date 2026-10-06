"""Signed private administrator reads: exact ownership, bounds, history and growth."""
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import event, func, select

from app import auth, main
from app.models.audit import AuditEvent
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.services.audit import AuditEventService
from test_current_identity import identity_client, headers, private
from test_command_concurrency_postgres import pg

ROOT = '/api/v1/security/admin/grants'


def admin(key, **claims):
    return headers(key, **{'sub':'other', **claims})


def count_admin_events(db):
    return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'MEMBERSHIP_STATUS_CHANGED'))


def identifier(sessions, ids, scope, *, status='ACTIVE'):
    model = {'GLOBAL':GlobalRoleAssignment, 'PROJECT':ProjectMembership, 'SOFTWARE':SoftwareMembership}[scope]
    with sessions() as db:
        stmt = select(model.id).where(model.principal_id == ids['principal'])
        if scope != 'GLOBAL':
            stmt = stmt.where(model.status == status)
        return db.scalar(stmt)


@pytest.mark.parametrize('scope,total', [('GLOBAL',2), ('PROJECT',3), ('SOFTWARE',2)])
def test_catalog_reads_all_states_with_exact_identity_and_minimal_fields(identity_client, scope, total):
    client, sessions, ids, key, _ = identity_client
    response = client.get(ROOT, params={'scope':scope, 'limit':1}, headers=admin(key))
    assert response.status_code == 200, response.text
    private(response)
    body = response.json()
    assert body['scope'] == scope and body['total'] == total and len(body['items']) == 1
    assert body['limit'] == 1 and body['offset'] == 0 and body['next_offset'] == 1
    value = body['items'][0]
    assert set(value) == {'id','scope','role','status','created_at','effective','principal','target','status_history_supported'}
    assert set(value['principal']) == {'id','principal_type','display_name','status'}
    if scope == 'GLOBAL':
        assert value['target'] is None and value['status'] is None and value['status_history_supported'] is False
    else:
        assert set(value['target']) == {'id','code','name'}
        assert value['target']['id'] == str(ids['project' if scope == 'PROJECT' else 'software'])
    for secret in ['private@example.com','user-123','https://identity.example.com',admin(key)['Authorization']]:
        assert secret not in response.text
    with sessions() as db:
        assert count_admin_events(db) == 0


@pytest.mark.parametrize('scope', ['GLOBAL','PROJECT','SOFTWARE'])
def test_all_pages_are_stable_complete_and_out_of_range_preserves_total(identity_client, scope):
    client, _, _, key, _ = identity_client
    body = client.get(ROOT, params={'scope':scope,'limit':1}, headers=admin(key)).json()
    rows = []
    for offset in range(body['total']):
        result = client.get(ROOT, params={'scope':scope,'limit':1,'offset':offset}, headers=admin(key)).json()
        assert result['total'] == body['total'] and result['offset'] == offset
        assert result['next_offset'] == (offset+1 if offset+1 < body['total'] else None)
        rows.extend(row['id'] for row in result['items'])
    assert rows == sorted(set(rows))
    result = client.get(ROOT, params={'scope':scope,'offset':100000}, headers=admin(key)).json()
    assert result['items'] == [] and result['total'] == body['total'] and result['next_offset'] is None


@pytest.mark.parametrize('scope,role', [('GLOBAL','AUDITOR'),('PROJECT','REVIEWER'),('SOFTWARE','SOFTWARE_VIEWER')])
def test_filters_use_stored_scope_and_principal_not_display_text(identity_client, scope, role):
    client, sessions, ids, key, _ = identity_client
    params = {'scope':scope,'principal_id':str(ids['principal']),'role':role,'principal_status':'ACTIVE'}
    if scope != 'GLOBAL':
        params.update(scope_id=str(ids['project' if scope == 'PROJECT' else 'software']),status='ACTIVE')
    response = client.get(ROOT, params=params, headers=admin(key))
    assert response.status_code == 200 and response.json()['total'] == 1
    item = response.json()['items'][0]
    assert item['principal']['id'] == str(ids['principal']) and item['effective'] is True
    missing = {**params,'principal_id':str(uuid.uuid4())}
    assert client.get(ROOT,params=missing,headers=admin(key)).json()['total'] == 0
    if scope != 'GLOBAL':
        assert client.get(ROOT,params={**params,'scope_id':str(uuid.uuid4())},headers=admin(key)).json()['total'] == 0
        suspended = client.get(ROOT,params={'scope':scope,'principal_id':str(ids['principal']),'status':'SUSPENDED'},headers=admin(key)).json()
        assert suspended['total'] == 1 and suspended['items'][0]['effective'] is False
    with sessions() as db:
        db.get(SecurityPrincipal,ids['principal']).status='DISABLED'; db.commit()
    response=client.get(ROOT,params={**params,'principal_status':'DISABLED'},headers=admin(key))
    assert response.json()['total'] == 1 and response.json()['items'][0]['effective'] is False


@pytest.mark.parametrize('scope', ['GLOBAL','PROJECT','SOFTWARE'])
def test_exact_detail_has_no_children_and_wrong_scope_never_resolves(identity_client, scope):
    client,sessions,ids,key,_=identity_client
    value=identifier(sessions,ids,scope)
    response=client.get(f'{ROOT}/{scope}/{value}',headers=admin(key))
    assert response.status_code==200
    private(response)
    assert response.json()['id']==str(value) and response.json()['scope']==scope
    assert 'items' not in response.json() and 'history' not in response.json()
    other='SOFTWARE' if scope!='SOFTWARE' else 'PROJECT'
    assert client.get(f'{ROOT}/{other}/{value}',headers=admin(key)).status_code==404
    assert client.get(f'{ROOT}/{scope}/{uuid.uuid4()}',headers=admin(key)).status_code==404
    assert client.get(f'{ROOT}/{scope}/{value}?principal_id={ids["other"]}',headers=admin(key)).status_code==422


@pytest.mark.parametrize('query', ['', 'scope=UNKNOWN','scope=PROJECT&limit=0','scope=PROJECT&limit=101',
 'scope=PROJECT&offset=-1','scope=PROJECT&offset=100001','scope=PROJECT&role=AUDITOR',
 'scope=GLOBAL&status=ACTIVE','scope=GLOBAL&scope_id='+str(uuid.uuid4()), 'scope=SOFTWARE&role=REVIEWER',
 'scope=PROJECT&status=DISABLED','scope=PROJECT&principal_status=SUSPENDED',
 'scope=PROJECT&principal_id=bad','scope=PROJECT&scope_id=bad','scope=PROJECT&role=',
 'scope=PROJECT&issuer=untrusted','scope=PROJECT&subject=other','scope=PROJECT&email=private@example.com'])
def test_invalid_or_unknown_filter_rejected_privately(identity_client,query):
    client,_,_,key,_=identity_client
    response=client.get(ROOT+'?'+query,headers=admin(key))
    assert response.status_code==422
    private(response)


@pytest.mark.parametrize('suffix', ['?scope=PROJECT', '/PROJECT/'+str(uuid.uuid4()), '/PROJECT/'+str(uuid.uuid4())+'/history'])
def test_every_read_requires_current_admin_and_never_uses_demo_fallback(identity_client,monkeypatch,suffix):
    client,sessions,ids,key,_=identity_client
    for authorization,expected in [({},401),(headers(key),403),(admin(key,aud='wrong'),401),(admin(key,sub='unknown'),401)]:
        response=client.get(ROOT+suffix,headers=authorization)
        assert response.status_code==expected
        private(response)
    with sessions() as db:
        row=db.scalar(select(GlobalRoleAssignment).where(GlobalRoleAssignment.principal_id==ids['other']))
        db.delete(row); db.commit()
    assert client.get(ROOT+suffix,headers=admin(key)).status_code==403
    monkeypatch.setattr(main.settings,'auth_mode','disabled')
    monkeypatch.setattr(auth,'jwks_client',lambda *_:pytest.fail('disabled mode must not contact provider'))
    response=client.get(ROOT+suffix,headers=admin(key))
    assert response.status_code==401 and response.json()['detail']=='oidc_not_enabled'
    private(response)


def test_inactive_admin_and_unknown_browser_session_cannot_read(identity_client):
    client,sessions,ids,key,_=identity_client
    authorization={**admin(key),'X-Browser-Session':str(uuid.uuid4())}
    response=client.get(ROOT+'?scope=PROJECT',headers=authorization)
    assert response.status_code==401 and response.json()['detail']=='invalid_browser_session'
    with sessions() as db:
        db.get(SecurityPrincipal,ids['other']).status='DISABLED';db.commit()
    response=client.get(ROOT+'?scope=PROJECT',headers=admin(key))
    assert response.status_code==401 and response.json()['detail']=='disabled_principal'
    private(response)


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_status_history_tracks_real_changes_and_excludes_other_scope_or_target(identity_client,monkeypatch,scope):
    client,sessions,ids,key,_=identity_client
    value=identifier(sessions,ids,scope)
    monkeypatch.setattr(main.settings,'read_only_mode',False)
    for before,after in [('ACTIVE','SUSPENDED'),('SUSPENDED','ACTIVE')]:
        response=client.post(f'/api/v1/security/admin/memberships/{scope}/{value}/status',json={
            'event_no':'ADM-'+uuid.uuid4().hex,'expected_status':before,'status':after,'reason':'Review scoped access'},headers=admin(key))
        assert response.status_code==200,response.text
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    with sessions() as db:
        for entity_type,entity_id,entity_ref,event_type in [(scope+'_MEMBERSHIP',uuid.uuid4(),str(value),'MEMBERSHIP_STATUS_CHANGED'),
            ('GLOBAL_MEMBERSHIP',value,str(value),'MEMBERSHIP_STATUS_CHANGED'),
            (scope+'_MEMBERSHIP',value,'wrong-reference','MEMBERSHIP_STATUS_CHANGED'),
            (scope+'_MEMBERSHIP',value,str(value),'UNRELATED_EVENT')]:
            AuditEventService(db).record(event_no='NOISE-'+uuid.uuid4().hex,event_type=event_type,action='NOISE',entity_type=entity_type,
                entity_id=entity_id,entity_ref=entity_ref,actor_name='Unknown',summary='Must not appear',payload={'token':'secret-noise'})
        db.commit()
    response=client.get(f'{ROOT}/{scope}/{value}/history?limit=1',headers=admin(key))
    assert response.status_code==200,response.text
    private(response)
    body=response.json()
    assert body['total']==2 and body['next_offset']==1 and body['coverage']=='MEMBERSHIP_STATUS_CHANGED_ONLY'
    assert body['grant_id']==str(value) and body['current_status']=='ACTIVE'
    item=body['items'][0]
    assert item['action']=='RESUME' and item['expected_status']=='SUSPENDED' and item['status']=='ACTIVE'
    assert item['actor_principal_id']==str(ids['other']) and item['actor_display_name']=='Other'
    assert item['reason']=='Review scoped access' and item['reason_truncated'] is False
    second=client.get(f'{ROOT}/{scope}/{value}/history?limit=1&offset=1',headers=admin(key)).json()
    assert second['items'][0]['action']=='SUSPEND' and second['next_offset'] is None
    assert 'secret-noise' not in response.text and 'payload_json' not in response.text
    assert client.get(f'{ROOT}/GLOBAL/{value}/history',headers=admin(key)).status_code==422
    assert client.get(f'{ROOT}/{scope}/{uuid.uuid4()}/history',headers=admin(key)).status_code==404
    for query in ['limit=101','offset=-1','event_type=UNRELATED_EVENT','actor_principal_id='+str(ids['other'])]:
        assert client.get(f'{ROOT}/{scope}/{value}/history?'+query,headers=admin(key)).status_code==422


def test_history_projects_bounded_fields_in_sql_and_stable_tie_order(identity_client):
    client,sessions,ids,key,_=identity_client
    value=identifier(sessions,ids,'PROJECT')
    timestamp=datetime.now(timezone.utc)
    identifiers=[]
    with sessions() as db:
        for index in range(3):
            row=AuditEventService(db).record(event_no='HIST-'+str(index),event_type='MEMBERSHIP_STATUS_CHANGED',action='SUSPEND',
                entity_type='PROJECT_MEMBERSHIP',entity_id=value,entity_ref=str(value),actor_name='Administrator',
                actor_principal_id=ids['other'],actor_display_name='Historical Name',summary='History projection',occurred_at=timestamp,
                payload={'reason':'x'*2000,'expected_status':'UNKNOWN','status':'SUSPENDED','token':'secret-token',
                         'raw':'z'*100000,'issuer':'private-issuer','email':'private-email'})
            identifiers.append(row.id)
        db.commit()
    response=client.get(f'{ROOT}/PROJECT/{value}/history?limit=2',headers=admin(key))
    assert response.status_code==200,response.text
    body=response.json()
    assert body['total']==3 and body['next_offset']==2
    assert [row['id'] for row in body['items']]==[str(v) for v in sorted(identifiers,reverse=True)[:2]]
    assert all(row['reason']=='x'*500 and row['reason_truncated'] is True and row['expected_status'] is None for row in body['items'])
    assert len(response.content)<2400
    for secret in ['secret-token','private-issuer','private-email','z'*1000,'payload_json']:
        assert secret not in response.text


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_catalog_and_history_growth_keep_fixed_queries_and_no_orm_graph(identity_client,scope):
    client,sessions,ids,key,engine=identity_client
    value=identifier(sessions,ids,scope)
    queries=[]
    def capture(_connection,_cursor,statement,_parameters,_context,_executemany):
        queries.append(statement)
    def forbid_graph(*args,**kwargs):
        pytest.fail('Admin grant reads must use scalar projections, not ORM history/children')
    def read():
        before=len(queries)
        catalog=client.get(ROOT,params={'scope':scope,'limit':1},headers=admin(key))
        detail=client.get(f'{ROOT}/{scope}/{value}',headers=admin(key))
        history=client.get(f'{ROOT}/{scope}/{value}/history?limit=1',headers=admin(key))
        assert catalog.status_code==detail.status_code==history.status_code==200
        return catalog.json(),history.json(),len(queries)-before
    event.listen(engine,'before_cursor_execute',capture)
    for model in [ProjectMembership,SoftwareMembership,GlobalRoleAssignment,AuditEvent]:
        event.listen(model,'load',forbid_graph)
    try:
        initial_catalog,initial_history,initial_queries=read()
        with sessions() as db:
            people=[SecurityPrincipal(issuer='https://growth.example.com',subject=str(i),principal_type='USER',display_name='Growth Person') for i in range(110)]
            db.add_all(people);db.flush()
            model=ProjectMembership if scope=='PROJECT' else SoftwareMembership
            for person in people:
                db.add(model(principal_id=person.id,**({'project_id':ids['project'],'role':'REVIEWER'} if scope=='PROJECT' else {'software_id':ids['software'],'role':'SOFTWARE_VIEWER'})))
            for i in range(110):
                AuditEventService(db).record(event_no='GROW-'+str(i),event_type='MEMBERSHIP_STATUS_CHANGED',action='SUSPEND',
                    entity_type=scope+'_MEMBERSHIP',entity_id=value,entity_ref=str(value),actor_name='Growth Actor',summary='Growth audit',
                    payload={'expected_status':'ACTIVE','status':'SUSPENDED','reason':'Bounded growth check','unreturned':'x'*10000})
            db.commit()
        grown_catalog,grown_history,grown_queries=read()
        assert grown_catalog['total']==initial_catalog['total']+110
        assert grown_history['total']==initial_history['total']+110
        assert len(grown_catalog['items'])==len(grown_history['items'])==1
        assert initial_queries==grown_queries==15  # Middleware1 + admin2 + data2/1/3.
        with sessions() as db:
            assert count_admin_events(db)==110
    finally:
        event.remove(engine,'before_cursor_execute',capture)
        for model in [ProjectMembership,SoftwareMembership,GlobalRoleAssignment,AuditEvent]:
            event.remove(model,'load',forbid_graph)
