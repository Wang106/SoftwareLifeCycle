"""Synthetic scoped declaration tests; PostgreSQL locking tested separately."""
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.core.config import settings
from app.models.core import Release, ReleaseComponent, ComponentDefinition, ApplicationReleaseDetail, Artifact
from app.models.audit import AuditEvent
from app.models.security import ProjectMembership,SoftwareMembership,SecurityPrincipal,GlobalRoleAssignment
from test_application_release_creation import creation_db,creation_client,request,body as release_body,submit as release_submit
from app.services.application_component_declaration import ApplicationComponentDeclarationService

def seed_components(db,ids):
    result,_=release_submit(db,ids,release_body(db,ids))
    definition=ComponentDefinition(code='ASRC-DEF',name='Component');db.add(definition);db.flush()
    base=ReleaseComponent(release_id=ids['standard'],component_definition_id=definition.id,version='base-v1',delta_type='ADDED')
    db.add(base);db.commit()
    return {**ids,'release':uuid.UUID(result['release_id']),'definition':definition.id,'base':base.id}

@pytest.fixture
def component_db(creation_db,monkeypatch):
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    db,ids=creation_db
    return db,seed_components(db,ids)

def service(db): return ApplicationComponentDeclarationService(db)
def body(db,ids,base=False):
    base_id=ids['base'] if base else None
    ctx=service(db).context(ids['release'],ids['definition'],base_id,request(db,ids))
    return dict(request_id=uuid.uuid4(),release_id=ids['release'],component_definition_id=ids['definition'],base_component_id=base_id,
        version='v1',delta_type='UNCHANGED' if base else 'ADDED',reason='Declare instance',expected_context_digest=ctx['context_digest'])
def submit(db,ids,values): return service(db).create(request=request(db,ids),**values)

@pytest.mark.parametrize('linked',[False,True])
def test_exact_independent_instances_and_original_receipt(component_db,linked):
    db,ids=component_db;values=body(db,ids,linked);result,created=submit(db,ids,values)
    assert created and result['component_id']==str(values['request_id'])
    assert submit(db,ids,values)==(result,False)
    assert service(db).receipt(values['request_id'],request(db,ids))==result
    for version in ('v1','v2'): assert submit(db,ids,{**values,'request_id':uuid.uuid4(),'version':version})[1]
    assert db.scalar(select(func.count()).select_from(ReleaseComponent).where(ReleaseComponent.release_id==ids['release']))==3
    assert db.scalar(select(func.count()).select_from(Artifact))==0

@pytest.mark.parametrize('kind',['principal','service','project','software','admin_only','readonly','disabled','auth'])
def test_current_authority_on_replay(component_db,monkeypatch,kind):
    db,ids=component_db;values=body(db,ids);submit(db,ids,values)
    if kind=='principal': db.get(SecurityPrincipal,ids['actor']).status='DISABLED'
    elif kind=='service': db.get(SecurityPrincipal,ids['actor']).principal_type='SERVICE'
    elif kind in ('project','admin_only'):
        db.get(ProjectMembership,ids['pm']).status='SUSPENDED'
        if kind=='admin_only': db.add(GlobalRoleAssignment(principal_id=ids['actor'],role='PLATFORM_ADMIN'))
    elif kind=='software': db.get(SoftwareMembership,ids['sm']).status='SUSPENDED'
    elif kind=='readonly': monkeypatch.setattr(settings,'read_only_mode',True)
    elif kind=='disabled': monkeypatch.setattr(settings,'application_component_declaration_enabled',False)
    else: monkeypatch.setattr(settings,'auth_mode','disabled')
    db.commit()
    with pytest.raises(HTTPException) as exc: submit(db,ids,values)
    assert exc.value.status_code in (401,403) and not db.in_transaction()

@pytest.mark.parametrize('kind',['definition','status','standard','base','scope','detail','context'])
def test_fresh_binding_denials(component_db,kind):
    db,ids=component_db;values=body(db,ids,True)
    if kind=='definition': db.get(ComponentDefinition,ids['definition']).is_active=False
    elif kind=='status': db.get(Release,ids['release']).status='RELEASED'
    elif kind=='standard': db.get(Release,ids['standard']).status='REVOKED'
    elif kind=='base': db.get(ReleaseComponent,ids['base']).release_id=ids['release']
    elif kind=='scope': db.get(Release,ids['release']).customer_scope_id=uuid.uuid4()
    elif kind=='detail': db.get(ApplicationReleaseDetail,ids['release']).standard_base_release_id=ids['release']
    else: db.get(Release,ids['release']).version='changed'
    db.commit()
    with pytest.raises(HTTPException): submit(db,ids,values)
    assert db.get(ReleaseComponent,values['request_id']) is None

@pytest.mark.parametrize('point',['audit','commit'])
def test_atomic_rollback(component_db,monkeypatch,point):
    db,ids=component_db;values=body(db,ids)
    def broken(*a,**k): raise RuntimeError('synthetic failure')
    if point=='audit':
        from app.services.audit import AuditEventService
        monkeypatch.setattr(AuditEventService,'record',broken)
    else: monkeypatch.setattr(db,'commit',broken)
    with pytest.raises(RuntimeError): submit(db,ids,values)
    assert not db.in_transaction() and db.get(ReleaseComponent,values['request_id']) is None
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='APPLICATION_COMPONENT_DECLARED'))==0

@pytest.mark.parametrize('kind',['reason','actor','payload','row','legacy'])
def test_conflict_does_not_overwrite(component_db,kind):
    db,ids=component_db;values=body(db,ids);original,_=submit(db,ids,values)
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==original['audit_event_no']))
    if kind=='reason': values['reason']='Changed'
    elif kind=='actor': event.actor_principal_id=uuid.uuid4()
    elif kind=='payload': event.payload_json={'receipt':original}
    elif kind=='row': db.get(ReleaseComponent,values['request_id']).version='changed'
    else: db.delete(event)
    db.commit()
    with pytest.raises(HTTPException) as exc: submit(db,ids,values)
    assert exc.value.status_code==409

def test_original_receipt_survives_later_ineligibility(component_db):
    db,ids=component_db;values=body(db,ids,True);original,_=submit(db,ids,values)
    db.get(Release,ids['release']).status='RELEASED';db.get(Release,ids['standard']).status='REVOKED'
    db.get(ComponentDefinition,ids['definition']).is_active=False;db.commit()
    assert submit(db,ids,values)==(original,False)
    assert service(db).receipt(values['request_id'],request(db,ids))==original

@pytest.mark.parametrize('field,value',[('version',' x'),('version','a\n'),('version',1),('reason',''),('reason','x\ud800'),
    ('delta_type','REMOVED'),('delta_type','MODIFIED'),('customer_id',str(uuid.uuid4())),('request_id',str(uuid.UUID(int=0)))])
def test_strict_input(component_db,field,value):
    db,ids=component_db;values=body(db,ids);values[field]=value
    with pytest.raises(HTTPException) as exc: submit(db,ids,values)
    assert exc.value.status_code==422

@pytest.mark.parametrize('field,value',[('event_type','OTHER'),('event_no','evt-asrc-corrupt')])
def test_audit_exclusion_even_malformed_marker(component_db,field,value):
    from app.api.activity import get_activity,list_activity,audit_catalog,AuditFilters
    from app.api.search import search_records
    from app.api.dashboard import dashboard_summary
    db,ids=component_db;result,_=submit(db,ids,body(db,ids))
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==result['audit_event_no']));setattr(event,field,value);db.commit()
    with pytest.raises(HTTPException) as exc: get_activity(event.event_no,db)
    assert exc.value.status_code==404
    assert list_activity(limit=50,db=db)==[] and audit_catalog(AuditFilters(),db)['total']==0
    assert not any(r['type']=='Activity' for r in search_records(db,event.event_no,50))
    assert dashboard_summary(db)['recent_activity']==[]

@pytest.mark.parametrize('kind',['revoked','expired','token','principal'])
def test_browser_session_rechecked_on_replay(component_db,kind):
    import hashlib
    from datetime import datetime,timedelta,timezone
    from app.models.security import BrowserSession
    from test_application_release_creation import TOKEN
    db,ids=component_db;values=body(db,ids);submit(db,ids,values)
    now=datetime.now(timezone.utc);sid=uuid.uuid4()
    db.add(BrowserSession(id=sid,principal_id=uuid.uuid4() if kind=='principal' else ids['actor'],
        token_digest=hashlib.sha256((TOKEN+'x' if kind=='token' else TOKEN).encode()).hexdigest(),
        created_at=now-timedelta(minutes=5),expires_at=now+timedelta(minutes=-1 if kind=='expired' else 5),
        revoked_at=now if kind=='revoked' else None));db.commit()
    with pytest.raises(HTTPException) as exc: service(db).create(request=request(db,ids,sid),**values)
    assert exc.value.status_code==401


def test_signed_http_round_trip(creation_client,creation_db,monkeypatch):
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    client,headers,_=creation_client;db,raw_ids=creation_db;ids=seed_components(db,raw_ids)
    path='/api/v1/application-component-declaration'
    response=client.get(path+'/context',params={'release_id':str(ids['release']),'component_definition_id':str(ids['definition'])},headers=headers)
    assert response.status_code==200,response.text
    values={**body(db,ids),'expected_context_digest':response.json()['context_digest']}
    values={k:str(v) if isinstance(v,uuid.UUID) else v for k,v in values.items()}
    new=client.post('/api/v1/application-component-declarations',json=values,headers=headers)
    assert new.status_code==201,new.text
    again=client.post('/api/v1/application-component-declarations',json=values,headers=headers)
    receipt=client.get(path+'/receipts/'+values['request_id'],headers=headers)
    assert again.status_code==receipt.status_code==200 and again.json()==new.json()==receipt.json()
    for r in (response,new,again,receipt):
        assert r.headers['cache-control']=='private, no-store' and 'x-browser-session' in r.headers['vary'].lower()
    assert client.get(path+'/receipts/'+values['request_id']).status_code==401

def test_new_to_baseline_definition_and_explicit_modified(component_db):
    db,ids=component_db
    definition=ComponentDefinition(code='ASRC-NEW',name='Not in baseline');db.add(definition);db.commit()
    new_ids={**ids,'definition':definition.id}
    values=body(db,new_ids);receipt,_=submit(db,new_ids,values)
    assert receipt['delta_type']=='ADDED' and receipt['base_component_id'] is None
    linked={**body(db,ids,True),'delta_type':'MODIFIED','version':'independent-v9'}
    assert submit(db,ids,linked)[0]['delta_type']=='MODIFIED'
    assert db.get(ReleaseComponent,ids['base']).version=='base-v1'

@pytest.mark.parametrize('kind',['wrong_definition','wrong_standard','missing','inactive_project','inactive_customer','inactive_software'])
def test_exact_parent_and_base_rechecks(component_db,kind):
    from app.models.core import Project,Customer,SoftwareProduct
    db,ids=component_db;values=body(db,ids,True)
    if kind=='wrong_definition':
        definition=ComponentDefinition(code='ASRC-OTHER',name='Other');db.add(definition);db.flush()
        db.get(ReleaseComponent,ids['base']).component_definition_id=definition.id
    elif kind=='wrong_standard':
        other=Release(software_id=ids['software'],release_type='STANDARD',version='other');db.add(other);db.flush()
        db.get(ReleaseComponent,ids['base']).release_id=other.id
    elif kind=='missing': db.delete(db.get(ReleaseComponent,ids['base']))
    else:
        key=kind.removeprefix('inactive_');model={'project':Project,'customer':Customer,'software':SoftwareProduct}[key]
        db.get(model,ids[key]).status='INACTIVE'
    db.commit()
    with pytest.raises(HTTPException): submit(db,ids,values)
    assert db.get(ReleaseComponent,values['request_id']) is None


def test_actual_asr_chain_revocation_blocks_fresh_declaration(component_db):
    from app.models.revocation import ReleaseChainRevocation
    db,ids=component_db;values=body(db,ids)
    # Service must inspect effective recorded revocation, not just Release.status.
    row=ReleaseChainRevocation(revocation_no='ASRC-REVOKED',release_id=ids['release'],target_kind='RELEASE',
        snapshot_id=uuid.uuid4(),release_decision_id=uuid.uuid4(),reason='Synthetic revocation',revoked_by='Synthetic')
    db.add(row);db.commit()
    with pytest.raises(HTTPException) as exc: submit(db,ids,values)
    assert exc.value.detail=='asrc_release_revoked'

@pytest.mark.parametrize('kind',['extra','duplicate','nil','uppercase','compact'])
def test_strict_context_query(creation_client,creation_db,monkeypatch,kind):
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    client,headers,_=creation_client;db,raw_ids=creation_db;ids=seed_components(db,raw_ids)
    params=[('release_id',str(ids['release'])),('component_definition_id',str(ids['definition']))]
    if kind=='extra': params.append(('customer_id',str(ids['customer'])))
    elif kind=='duplicate': params.append(params[0])
    elif kind=='nil': params[0]=('release_id',str(uuid.UUID(int=0)))
    elif kind=='uppercase': params[0]=('release_id','AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA')
    else: params[0]=('release_id',ids['release'].hex)
    response=client.get('/api/v1/application-component-declaration/context',params=params,headers=headers)
    assert response.status_code==422 and response.json()['detail']=='invalid_asrc_context_query'
    assert response.headers['cache-control']=='private, no-store'

@pytest.mark.parametrize('key',[str(uuid.UUID(int=0)),'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA','a'*32])
def test_strict_receipt_id(creation_client,monkeypatch,key):
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    client,headers,_=creation_client
    response=client.get('/api/v1/application-component-declaration/receipts/'+key,headers=headers)
    assert response.status_code==422 and response.json()['detail']=='invalid_asrc_receipt_id'
    assert response.headers['cache-control']=='private, no-store'
