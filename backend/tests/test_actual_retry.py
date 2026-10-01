"""Actual report retry results, optimistic versions, corrections and rollback."""
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_production_retry import production, counts
from test_distribution_catalog import chain
from test_impact_assessments import context
from test_command_audit import trusted_actor
from app.actor import ActorContext
from app.api.production import ActualSoftwareReport, report_actual, get_deployment
from app.models.audit import AuditEvent
from app.models.production import Deployment
from app.models.snapshot import ReleaseSnapshot
from app.services.audit import AuditEventService
from app.services.production import ProductionError, ProductionService

@pytest.fixture
def actual(production):
    db, _, _, _, previous, dep, _, _ = production
    dep.actual_release_id = dep.actual_snapshot_id = dep.deployed_at = None
    dep.status = 'PENDING'; db.commit()
    other = ReleaseSnapshot(release_id=previous.id, snapshot_no='PREVIOUS',snapshot_number=1,content_hash='a'*64,status='FROZEN')
    db.add(other); db.commit()
    return production, other

def values(actual, **changes):
    ctx, _ = actual
    return {**dict(deployment_no='DEP',actual_release_id=ctx[6].id,actual_snapshot_id=ctx[7].id,request_id=uuid.uuid4(),expected_version=0), **changes}
def run(actual,data,actor=None):return ProductionService(actual[0][0]).report_actual(**data,actor_context=actor)
def state(actual):
    dep=actual[0][5]
    return dep.actual_release_id,dep.actual_snapshot_id,dep.status,dep.actual_version,dep.deployed_at

def test_retry_original_result_after_correction(actual):
    ctx,other=actual;db=ctx[0];data=values(actual);first=run(actual,data)
    assert first.actual_version==1 and first.status=='MATCH'
    second=run(actual,{**data,'request_id':uuid.uuid4(),'expected_version':1,'actual_release_id':ctx[4].id,'actual_snapshot_id':other.id,'correction_reason':'Corrected evidence'})
    before=counts(db);current=state(actual)
    assert second.actual_version==2 and second.status=='MISMATCH'
    assert run(actual,data)==first and state(actual)==current and counts(db)==before
    events=db.scalars(select(AuditEvent).where(AuditEvent.entity_id==ctx[5].id).order_by(AuditEvent.created_at)).all()
    assert [e.action for e in events]==['ACTUAL_REPORTED','ACTUAL_CORRECTED']
    assert events[1].payload_json['before']==events[0].payload_json['after']
    assert events[1].payload_json['correction_reason']=='Corrected evidence'
    assert get_deployment('DEP',db)['actual_version']==2

@pytest.mark.parametrize('field,changed',[('actual_release_id',uuid.uuid4()),('actual_snapshot_id',uuid.uuid4()),('expected_version',1),('deployed_at',datetime(2026,1,1)),('correction_reason','Changed reason'),('deployment_no','OTHER')])
def test_changed_content_conflicts(actual,field,changed):
    db=actual[0][0];data=values(actual);run(actual,data)
    if field=='deployment_no':
        dep=actual[0][5]
        db.add(Deployment(deployment_no='OTHER',authorization_id=dep.authorization_id,production_line_id=dep.production_line_id,expected_release_id=dep.expected_release_id,expected_snapshot_id=dep.expected_snapshot_id));db.commit()
    before=counts(db);current=state(actual)
    with pytest.raises(ProductionError,match='request_id'):run(actual,{**data,field:changed})
    assert counts(db)==before and state(actual)==current

@pytest.mark.parametrize('case',['principal','display','declaration','mode','legacy'])
def test_actor_and_legacy_key_conflict(actual,case):
    db=actual[0][0];actor=trusted_actor(db,'writer','Trusted Writer');data=values(actual)
    run(actual,{**data,'request_id':None} if case=='legacy' else data,actor)
    if case=='legacy':
        event=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==actual[0][5].id));data['request_id']=uuid.UUID(event.event_no.removeprefix('EVT-DA-'))
    elif case=='principal':actor=trusted_actor(db,'other','Trusted Writer')
    elif case=='display':actor=replace(actor,display_name='Changed')
    elif case=='declaration':actor=replace(actor,declared_name='Changed')
    else:actor=ActorContext.legacy(None)
    before=counts(db);current=state(actual)
    with pytest.raises(ProductionError,match='request_id'):run(actual,data,actor)
    assert counts(db)==before and state(actual)==current

@pytest.mark.parametrize('case',['stale','missing_reason','blank_reason','invalid_snapshot'])
def test_conflict_rollback_and_key_reusable(actual,case):
    db=actual[0][0];data=values(actual);run(actual,data)
    data={**data,'request_id':uuid.uuid4(),'expected_version':1,'correction_reason':'Correction'};bad={**data}
    if case=='stale':bad['expected_version']=0
    elif case=='missing_reason':bad['correction_reason']=None
    elif case=='blank_reason':bad['correction_reason']='  '
    else:bad['actual_snapshot_id']=uuid.uuid4()
    before=counts(db);current=state(actual)
    with pytest.raises(ProductionError):run(actual,bad)
    assert not db.in_transaction() and counts(db)==before and state(actual)==current
    assert run(actual,data).actual_version==2

@pytest.mark.parametrize('failure',['flush','audit_after_flush','commit'])
@pytest.mark.parametrize('correction',[False,True])
def test_failure_rolls_back_and_key_reusable(actual,monkeypatch,failure,correction):
    db=actual[0][0];data=values(actual)
    if correction:
        run(actual,data);data={**data,'request_id':uuid.uuid4(),'expected_version':1,'correction_reason':'Correction'}
    before=counts(db);current=state(actual)
    with monkeypatch.context() as patch:
        if failure=='flush':
            def fail(*args,**kwargs):raise IntegrityError('injected',{},Exception('failure'))
            patch.setattr(db,'flush',fail)
        elif failure=='audit_after_flush':
            original=AuditEventService.record
            def fail(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('after audit flush')
            patch.setattr(AuditEventService,'record',fail)
        else:
            def fail(*args,**kwargs):raise RuntimeError('commit failure')
            patch.setattr(db,'commit',fail)
        with pytest.raises((ProductionError,RuntimeError)):run(actual,data)
    assert not db.in_transaction() and counts(db)==before and state(actual)==current
    assert run(actual,data).actual_version==(2 if correction else 1)

def test_legacy_overwrite_advances_version(actual):
    data=values(actual,request_id=None,expected_version=None)
    assert run(actual,data).actual_version==1
    before=counts(actual[0][0]);assert run(actual,data).actual_version==2
    assert counts(actual[0][0])[AuditEvent]==before[AuditEvent]+1
    with pytest.raises(ProductionError,match='actual_version'):run(actual,{**data,'expected_version':1})

def test_legacy_baseline_requires_reason_at_version_zero(production):
    db=production[0];data=dict(deployment_no='DEP',actual_release_id=production[6].id,actual_snapshot_id=production[7].id,request_id=uuid.uuid4(),expected_version=0)
    production[5].actual_release_id=production[6].id
    production[5].actual_snapshot_id=production[7].id
    production[5].status='MATCH';db.commit()
    assert production[5].actual_version==0
    with pytest.raises(ProductionError,match='correction_reason'):ProductionService(db).report_actual(**data)
    assert ProductionService(db).report_actual(**data,correction_reason='Legacy corrected').actual_version==1

def test_timestamp_equivalence_and_omission(actual):
    data=values(actual,deployed_at=datetime(2026,1,1));first=run(actual,data);before=counts(actual[0][0])
    assert run(actual,{**data,'deployed_at':datetime(2026,1,1,8,tzinfo=timezone(timedelta(hours=8)))})==first
    with pytest.raises(ProductionError):run(actual,{**data,'deployed_at':None})
    assert counts(actual[0][0])==before

@pytest.mark.parametrize('changes',[{'request_id':'bad'},{'expected_version':None},{'expected_version':-1},{'expected_version':True},{'expected_version':'0'},{'correction_reason':''},{'correction_reason':'  '},{'correction_reason':'a'*2001}])
def test_invalid_http_model(actual,changes):
    data=values(actual);data.pop('deployment_no')
    with pytest.raises(ValidationError):ActualSoftwareReport(**{**data,**changes})

def test_http_response_auth_and_actor(actual,monkeypatch):
    from app.core.config import settings
    from app.authorization import AuthorizationError
    from app.models.security import ProjectMembership,SecurityPrincipal
    from test_authorization import authenticated_request
    db=actual[0][0];actor=trusted_actor(db,'operator','Trusted Operator');request=authenticated_request(db.get(SecurityPrincipal,actor.principal_id))
    monkeypatch.setattr(settings,'auth_mode','oidc')
    data=values(actual);data.pop('deployment_no');payload=ActualSoftwareReport(**data);before=counts(db)
    with pytest.raises(AuthorizationError):report_actual('DEP',payload,db,request)
    assert counts(db)==before
    grant=ProjectMembership(principal_id=actor.principal_id,project_id=actual[0][1].project_id,role='PRODUCTION_OPERATOR',status='ACTIVE');db.add(grant);db.commit()
    first=report_actual('DEP',payload,db,request)
    assert first=={'deployment_no':'DEP','status':'MATCH','actual_version':1}
    before=counts(db);assert report_actual('DEP',payload,db,request)==first and counts(db)==before
    event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==f"EVT-DA-{data['request_id'].hex}"))
    assert event.actor_principal_id==actor.principal_id and event.actor_display_name=='Trusted Operator'
    with pytest.raises(HTTPException) as exc:report_actual('DEP',ActualSoftwareReport(**{**data,'expected_version':1}),db,request)
    assert exc.value.status_code==409
    grant.status='SUSPENDED';db.commit()
    with pytest.raises(AuthorizationError):report_actual('DEP',payload,db,request)
    assert counts(db)==before
