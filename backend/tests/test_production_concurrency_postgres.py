"""Real PostgreSQL production retries and shared Deployment ordering."""
import uuid
from datetime import datetime,timezone
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg,count,overlapping_commands
from app.models.core import Release
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment,ManufacturingSite,ProductionLine,SoftwareChangeover,ProductionBatch
from app.models.snapshot import ReleaseSnapshot
from app.models.audit import AuditEvent
from app.services.production import ProductionService,ProductionError
from app.services.audit import AuditEventService

KINDS=('deployment','changeover')
MODEL=dict(deployment=Deployment,changeover=SoftwareChangeover)
@pytest.fixture
def production(pg):
    engine,ids=pg
    with Session(engine,expire_on_commit=False) as db:
        auth=db.get(SoftwareAuthorization,ids['authorization'])
        line=db.scalar(select(ProductionLine));site=db.get(ManufacturingSite,line.site_id)
        previous=Release(software_id=db.get(Release,ids['release']).software_id,release_type='STANDARD',version='0')
        other_site=ManufacturingSite(site_code='OTHER',customer_id=site.customer_id,project_id=site.project_id,name='Other',status='ACTIVE')
        db.add_all([previous,other_site]);db.flush()
        other_line=ProductionLine(site_id=other_site.id,line_code='OTHER',name='Other',status='ACTIVE')
        other_auth=SoftwareAuthorization(authorization_no='OTHER',release_id=auth.release_id,snapshot_id=auth.snapshot_id,customer_id=auth.customer_id,project_id=auth.project_id,site_code='OTHER',line_code='OTHER',status='APPROVED')
        db.add_all([other_line,other_auth]);db.commit()
        ids={**ids,'line':line.id,'site':site.id,'other_line':other_line.id,'other_authorization':other_auth.id,'previous':previous.id,'snapshot':auth.snapshot_id}
    return engine,ids

def run(db,kind,ids,key,other=False,number='NEW',**changes):
    if kind=='deployment':values=dict(deployment_no=number,authorization_id=ids['other_authorization'] if other else ids['authorization'],production_line_id=ids['other_line'] if other else ids['line'])
    else:values=dict(deployment_no='DEP-2' if other else 'DEP-1',changeover_no=number,from_release_id=ids['previous'])
    return getattr(ProductionService(db),'create_'+kind)(**{**values,**changes},request_id=key)
def counts(db):return {m:count(db,m) for m in (Deployment,SoftwareChangeover,ProductionBatch,AuditEvent)}

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('case',['replay','changed','duplicate','different'])
def test_same_parent_concurrent_retry_and_history_contract(production,monkeypatch,kind,case):
    engine,ids=production;key=uuid.uuid4();other_key=key if case in ('replay','changed') else uuid.uuid4()
    changes={'deployment_no':'CHANGED'} if kind=='deployment' else {'note':'Changed'}
    with Session(engine) as db:before=counts(db)
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:run(db,kind,ids,key),
        lambda db:run(db,kind,ids,other_key,number='OTHER' if case=='different' else 'NEW',**(changes if case=='changed' else {})))
    assert first[0]=='ok' and second[0]==('ok' if case in ('replay','different') else 'conflict')
    if case=='replay':assert first[1]==second[1]
    with Session(engine) as db:
        added=2 if case=='different' else 1
        assert count(db,MODEL[kind])==before[MODEL[kind]]+added and count(db,AuditEvent)==before[AuditEvent]+added

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('collision',['key','number'])
def test_global_unique_races_across_independent_parents(production,monkeypatch,kind,collision):
    engine,ids=production;key=uuid.uuid4()
    with Session(engine) as db:before=counts(db)
    results=overlapping_commands(engine,monkeypatch,
        lambda db:run(db,kind,ids,key),
        lambda db:run(db,kind,ids,key if collision=='key' else uuid.uuid4(),other=True,number='OTHER' if collision=='key' else 'NEW'))
    assert results[0][0]=='ok' and results[1][0]=='conflict'
    with Session(engine) as db:assert count(db,MODEL[kind])==before[MODEL[kind]]+1 and count(db,AuditEvent)==before[AuditEvent]+1

@pytest.mark.parametrize('kind',['deployment','changeover','actual'])
def test_audit_failure_full_rollback_and_lock_release(production,monkeypatch,kind):
    engine,ids=production;key=uuid.uuid4();original=AuditEventService.record
    def call(db):
        if kind=='actual':return ProductionService(db).report_actual('DEP-1',ids['release'],ids['snapshot'])
        return run(db,kind,ids,key)
    def fail(*a,**kw):original(*a,**kw);raise RuntimeError('after audit flush')
    with Session(engine) as db:
        before=counts(db);dep=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'));before_state=(dep.actual_release_id,dep.actual_snapshot_id,dep.status)
        monkeypatch.setattr(AuditEventService,'record',fail)
        with pytest.raises(RuntimeError):call(db)
        assert not db.in_transaction() and counts(db)==before
        assert (dep.actual_release_id,dep.actual_snapshot_id,dep.status)==before_state
    monkeypatch.setattr(AuditEventService,'record',original)
    with Session(engine) as db:call(db)

@pytest.mark.parametrize('stale',['authorization','site','line','line_scope','deployment'])
def test_refresh_cached_parent_before_validation(production,stale):
    engine,ids=production
    with Session(engine,expire_on_commit=False) as db:
        models={'authorization':SoftwareAuthorization,'site':ManufacturingSite,'line':ProductionLine,'line_scope':ProductionLine}
        if stale=='deployment':cached=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'))
        else:cached=db.get(models[stale],ids['line' if stale=='line_scope' else stale])
        db.commit()
        with Session(engine) as writer:
            row=writer.get(type(cached),cached.id)
            if stale=='deployment':row.expected_release_id=ids['previous']
            elif stale=='line_scope':row.line_code='WRONG'
            else:row.status='INACTIVE'
            writer.commit()
        before=counts(db)
        with pytest.raises(ProductionError):run(db,'changeover' if stale=='deployment' else 'deployment',ids,uuid.uuid4())
        assert not db.in_transaction() and counts(db)==before

def test_changeover_naive_time_is_utc_and_replays(production):
    engine,ids=production;key=uuid.uuid4()
    with Session(engine) as db:row=run(db,'changeover',ids,key,changed_at=datetime(2026,1,1));assert row.changed_at==datetime(2026,1,1,tzinfo=timezone.utc)
    with Session(engine) as db:assert run(db,'changeover',ids,key,changed_at=datetime(2026,1,1,tzinfo=timezone.utc)).id==key

def test_actual_reports_serialize_and_audit_before_state_is_not_stale(production,monkeypatch):
    engine,ids=production
    with Session(engine) as db:
        previous_snapshot=ReleaseSnapshot(release_id=ids['previous'],snapshot_no='PREVIOUS',snapshot_number=1,content_hash='a'*64,status='FROZEN');db.add(previous_snapshot);db.commit();snapshot_id=previous_snapshot.id
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:ProductionService(db).report_actual('DEP-1',ids['previous'],snapshot_id),
        lambda db:ProductionService(db).report_actual('DEP-1',ids['release'],ids['snapshot']))
    assert first[0]==second[0]=='ok'
    with Session(engine) as db:
        events=db.scalars(select(AuditEvent).where(AuditEvent.action=='ACTUAL_REPORTED').order_by(AuditEvent.created_at)).all()
        assert len(events)==2 and events[1].payload_json['before']==events[0].payload_json['after']
        assert events[1].payload_json['before']['status']=='MISMATCH' and events[1].payload_json['after']['status']=='MATCH'

@pytest.mark.parametrize('first_actual',[True,False])
def test_actual_and_batch_share_deployment_ordering(production,monkeypatch,first_actual):
    engine,ids=production
    with Session(engine) as db:
        snapshot=ReleaseSnapshot(release_id=ids['previous'],snapshot_no='PREVIOUS',snapshot_number=1,content_hash='a'*64,status='FROZEN');db.add(snapshot);db.commit();snapshot_id=snapshot.id
    actual=lambda db:ProductionService(db).report_actual('DEP-1',ids['previous'],snapshot_id)
    batch=lambda db:ProductionService(db).create_batch('DEP-1','B',request_id=uuid.uuid4())
    first,second=overlapping_commands(engine,monkeypatch,actual if first_actual else batch,batch if first_actual else actual)
    assert first[0]=='ok' and second[0]==('conflict' if first_actual else 'ok')
    with Session(engine) as db:
        assert count(db,ProductionBatch)==(0 if first_actual else 1)
        assert db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1')).status=='MISMATCH'

def test_batch_then_duplicate_deployment_creation_does_not_reverse_lock_order(production,monkeypatch):
    engine,ids=production
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:ProductionService(db).create_batch('DEP-1','B',request_id=uuid.uuid4()),
        lambda db:run(db,'deployment',ids,uuid.uuid4(),number='DEP-1'))
    assert first[0]=='ok' and second[0]=='conflict'

@pytest.mark.parametrize('kind',['actual','batch'])
def test_changeover_orders_with_other_deployment_commands(production,monkeypatch,kind):
    engine,ids=production
    def second(db):
        if kind=='actual':return ProductionService(db).report_actual('DEP-1',ids['release'],ids['snapshot'])
        return ProductionService(db).create_batch('DEP-1','B',request_id=uuid.uuid4())
    results=overlapping_commands(engine,monkeypatch,lambda db:run(db,'changeover',ids,uuid.uuid4()),second)
    assert all(r[0]=='ok' for r in results)
