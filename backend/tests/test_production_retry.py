"""Deployment/Changeover retry, scope, timestamps and rollback."""
import uuid
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from test_distribution_catalog import chain
from test_impact_assessments import context
from test_command_audit import trusted_actor
from app.actor import ActorContext
from app.api.production import DeploymentCreate,ChangeoverCreate,create_deployment,create_changeover
from app.models.core import Release
from app.models.production import Deployment,ManufacturingSite,ProductionLine,SoftwareChangeover
from app.models.audit import AuditEvent
from app.services.production import ProductionError,ProductionService
from app.services.audit import AuditEventService

KINDS=('deployment','changeover')
@pytest.fixture
def production(chain):
    db,release,_,snapshot,_,_,authorizations,customer,project=chain
    authorization=authorizations[1]
    site=ManufacturingSite(site_code='SITE',customer_id=customer.id,project_id=project.id,name='Site',status='ACTIVE')
    db.add(site);db.flush()
    line=ProductionLine(site_id=site.id,line_code='LINE',name='Line',status='ACTIVE')
    previous=Release(software_id=release.software_id,release_type='STANDARD',version='0')
    db.add_all([line,previous]);db.commit()
    deployment=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP'))
    return db,authorization,site,line,previous,deployment,release,snapshot

def args(ctx,kind):
    _,authorization,_,line,previous,*_=ctx
    if kind=='deployment':return dict(deployment_no='NEW-DEP',authorization_id=authorization.id,production_line_id=line.id,request_id=uuid.uuid4())
    return dict(deployment_no='DEP',changeover_no='NEW-CO',from_release_id=previous.id,changed_at=None,note='Controlled',request_id=uuid.uuid4())
def run(ctx,kind,values,actor=None):return getattr(ProductionService(ctx[0]),'create_'+kind)(**values,actor_context=actor)
def counts(db):return {m:db.scalar(select(func.count()).select_from(m)) for m in (Deployment,SoftwareChangeover,AuditEvent)}

@pytest.mark.parametrize('kind',KINDS)
def test_replay_and_legacy_duplicate_behavior(production,kind):
    db=production[0];values=args(production,kind);row=run(production,kind,values);before=counts(db)
    assert run(production,kind,values).id==row.id==values['request_id'] and counts(db)==before
    for key in (None,uuid.uuid4()):
        with pytest.raises(ProductionError):run(production,kind,{**values,'request_id':key})
        assert counts(db)==before

@pytest.mark.parametrize('kind,field,value',[('deployment','deployment_no','OTHER'),('deployment','authorization_id',uuid.uuid4()),('deployment','production_line_id',uuid.uuid4()),('changeover','deployment_no','OTHER'),('changeover','changeover_no','OTHER'),('changeover','from_release_id',uuid.uuid4()),('changeover','changed_at',datetime(2026,1,1)),('changeover','note','Other')])
def test_changed_content_conflicts(production,kind,field,value):
    db=production[0];values=args(production,kind);run(production,kind,values);before=counts(db)
    if kind=='changeover' and field=='deployment_no':
        original=production[5]
        db.add(Deployment(deployment_no='OTHER',authorization_id=original.authorization_id,production_line_id=original.production_line_id,expected_release_id=original.expected_release_id,expected_snapshot_id=original.expected_snapshot_id));db.commit();before=counts(db)
    with pytest.raises(ProductionError):run(production,kind,{**values,field:value})
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('case',['principal','display','declaration','mode','legacy'])
def test_full_actor_binding_and_legacy_row_cannot_be_claimed(production,kind,case):
    db=production[0];values=args(production,kind);actor=trusted_actor(db,'writer','Operator')
    row=run(production,kind,{**values,'request_id':None} if case=='legacy' else values,actor)
    if case=='legacy':values['request_id']=row.id
    elif case=='principal':actor=trusted_actor(db,'other','Operator')
    elif case=='display':actor=replace(actor,display_name='Changed')
    elif case=='declaration':actor=replace(actor,declared_name='Changed')
    elif case=='mode':actor=ActorContext.legacy(None)
    before=counts(db)
    with pytest.raises(ProductionError,match='request_id'):run(production,kind,values,actor)
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
def test_replay_recovers_committed_record_after_parent_changes(production,kind):
    db=production[0];values=args(production,kind);row=run(production,kind,values)
    if kind=='deployment':production[1].status='REVOKED';production[3].status='INACTIVE'
    else:production[5].expected_release_id=production[4].id
    db.commit();before=counts(db)
    assert run(production,kind,values).id==row.id and counts(db)==before
    fresh={**values,'request_id':uuid.uuid4(),('deployment_no' if kind=='deployment' else 'changeover_no'):'FRESH'}
    with pytest.raises(ProductionError):run(production,kind,fresh)
    assert counts(db)==before

@pytest.mark.parametrize('kind',['deployment','changeover','actual'])
@pytest.mark.parametrize('failure',['validation','flush','audit_after_flush','commit'])
def test_every_failure_rolls_back_and_allows_reuse(production,monkeypatch,kind,failure):
    db=production[0];values=args(production,kind) if kind!='actual' else dict(deployment_no='DEP',actual_release_id=production[6].id,actual_snapshot_id=production[7].id)
    def call(v):return ProductionService(db).report_actual(**v) if kind=='actual' else run(production,kind,v)
    before=counts(db);old=(production[5].actual_release_id,production[5].actual_snapshot_id,production[5].status)
    with monkeypatch.context() as patch:
        bad={**values}
        if failure=='validation':
            if kind=='deployment':bad['production_line_id']=uuid.uuid4()
            elif kind=='changeover':bad['from_release_id']=production[6].id
            else:bad['actual_snapshot_id']=uuid.uuid4()
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
        with pytest.raises((ProductionError,RuntimeError)):call(bad)
    assert not db.in_transaction() and counts(db)==before
    assert (production[5].actual_release_id,production[5].actual_snapshot_id,production[5].status)==old
    call(values);assert counts(db)[AuditEvent]==before[AuditEvent]+1

def test_changeover_timestamp_equivalence_and_omission(production):
    values=args(production,'changeover');values['changed_at']=datetime(2026,1,1)
    row=run(production,'changeover',values);before=counts(production[0])
    assert run(production,'changeover',{**values,'changed_at':datetime(2026,1,1,8,tzinfo=timezone(timedelta(hours=8)))}).id==row.id
    with pytest.raises(ProductionError):run(production,'changeover',{**values,'changed_at':None})
    assert counts(production[0])==before

@pytest.mark.parametrize('field',['authorization','site','line','scope'])
def test_deployment_preserves_parent_scope_status_guards(production,field):
    db=production[0];values=args(production,'deployment')
    if field=='authorization':production[1].status='DRAFT'
    elif field=='site':production[2].status='INACTIVE'
    elif field=='line':production[3].status='INACTIVE'
    else:production[3].line_code='WRONG'
    db.commit();before=counts(db)
    with pytest.raises(ProductionError):run(production,'deployment',values)
    assert counts(db)==before

@pytest.mark.parametrize('kind',KINDS)
def test_http_uuid_shapes_conflict_and_exact_role_on_replay(production,monkeypatch,kind):
    from app.core.config import settings
    from app.authorization import AuthorizationError
    from app.models.security import ProjectMembership,SecurityPrincipal
    from test_authorization import authenticated_request
    db=production[0];values=args(production,kind)
    model=DeploymentCreate if kind=='deployment' else ChangeoverCreate
    payload_values=values if kind=='deployment' else {k:v for k,v in values.items() if k!='deployment_no'}
    with pytest.raises(ValidationError):model(**{**payload_values,'request_id':'invalid'})
    payload=model(**payload_values);actor=trusted_actor(db,kind,'Trusted Operator')
    request=authenticated_request(db.get(SecurityPrincipal,actor.principal_id))
    grant=ProjectMembership(principal_id=actor.principal_id,project_id=production[1].project_id,role='PRODUCTION_OPERATOR',status='ACTIVE')
    monkeypatch.setattr(settings,'auth_mode','oidc')
    def call(p):return create_deployment(p,db,request) if kind=='deployment' else create_changeover('DEP',p,db,request)
    before=counts(db)
    with pytest.raises(AuthorizationError):call(payload)
    assert counts(db)==before
    db.add(grant);db.commit();first=call(payload);before=counts(db)
    assert call(payload)==first and counts(db)==before and first['id']==str(values['request_id'])
    assert first['status']==('PENDING' if kind=='deployment' else 'COMPLETED')
    event=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==values['request_id']))
    assert event.actor_principal_id==actor.principal_id and event.actor_display_name=='Trusted Operator'
    field='deployment_no' if kind=='deployment' else 'changeover_no'
    with pytest.raises(HTTPException) as exc:call(model(**{**payload_values,field:'OTHER'}))
    assert exc.value.status_code==409 and counts(db)==before
    grant.status='SUSPENDED';db.commit()
    with pytest.raises(AuthorizationError):call(payload)
    assert counts(db)==before
