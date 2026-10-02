"""Counts and catalog scope preserve the exact legacy direct-parent chain."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,event,func,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_distribution_catalog import chain
from test_production_catalog import production
from test_command_concurrency_postgres import pg
from app.api.dashboard import application_release_downstream,application_release_downstream_summary
from app.api.production_catalog import ProductionFilters,production_catalog
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.distribution import DeliveryPackage,Distribution,SoftwareAuthorization
from app.models.production import Deployment,ProductionBatch,SoftwareChangeover

@pytest.fixture
def asr(production):
    db,release,*_=production;release.release_type='APPLICATION';db.commit();return production

def test_exact_counts_observations_and_legacy_shape(asr):
    db,r,*_=asr;result=application_release_downstream_summary(r.id,db)
    assert result=={'release_id':str(r.id),'history_counts':{'deliveries':2,'distributions':2,'authorizations':2,'deployments':2,'changeovers':1,'batches':2},'actual_release_observations':{'same_release':1,'different_release':0,'not_reported':1},'batch_release_observations':{'same_release':2,'different_release':0}}
    legacy=application_release_downstream(r.id,db)
    assert result['history_counts']=={k:len(v) for k,v in legacy.items()}
    assert not any(isinstance(v,list) for v in result.values())

def test_empty_and_same_version_sibling_scope(asr):
    db,r,*_=asr;other=Release(software_id=uuid.uuid4(),release_type='APPLICATION',version=r.version);db.add(other);db.commit()
    result=application_release_downstream_summary(other.id,db)
    assert result['release_id']==str(other.id)
    for k in ['history_counts','actual_release_observations','batch_release_observations']:assert not any(result[k].values())

@pytest.mark.parametrize('case',['missing','standard'])
def test_missing_or_wrong_type_404(asr,case):
    db,r,*_=asr;target=uuid.uuid4()
    if case=='standard':r.release_type='STANDARD';db.commit();target=r.id
    with pytest.raises(HTTPException) as error:application_release_downstream_summary(target,db)
    assert error.value.status_code==404

@pytest.mark.parametrize('case,obs',[('different',{'same_release':0,'different_release':1,'not_reported':1}),('empty',{'same_release':0,'different_release':0,'not_reported':2}),('partial',{'same_release':1,'different_release':0,'not_reported':1})])
def test_observations_do_not_trust_status_or_claim_snapshot_match(asr,case,obs):
    db,r,_,_,_,dep,*_=asr
    if case=='different':dep.actual_release_id=uuid.uuid4()
    elif case=='empty':dep.actual_release_id=dep.actual_snapshot_id=None
    else:dep.actual_snapshot_id=None
    db.commit();assert dep.status=='MATCH'
    assert application_release_downstream_summary(r.id,db)['actual_release_observations']==obs

@pytest.mark.parametrize('kind',['deployments','changeovers','batches'])
def test_authorization_scope_keeps_mismatches_pagination_and_filter_intersection(asr,kind):
    db,r,_,_,_,dep,pending,co,batches,*_=asr
    other=Release(software_id=uuid.uuid4(),release_type='APPLICATION',version=r.version);db.add(other);db.flush()
    dep.expected_release_id=pending.expected_release_id=dep.actual_release_id=other.id;co.to_release_id=other.id
    for b in batches:b.release_id=other.id
    db.commit();expected={'deployments':2,'changeovers':1,'batches':2}[kind]
    filters=ProductionFilters(authorization_release_id=r.id,limit=1);page=production_catalog(kind,filters,db)
    assert page['total']==expected and not page['items'][0]['context_consistent']
    for query,total in [({'release_id':r.id},0),({'authorization_release_id':other.id},0),({'authorization_release_id':r.id,'release_id':other.id},expected),({'authorization_release_id':r.id,'release_id':r.id},0)]:assert production_catalog(kind,ProductionFilters(**query),db)['total']==total
    if expected>1:
        following=production_catalog(kind,filters.model_copy(update={'offset':page['next_offset']}),db)
        assert following['total']==expected and following['next_offset'] is None and following['items'][0]['id']!=page['items'][0]['id']
    result=application_release_downstream_summary(r.id,db);assert result['history_counts'][kind]==expected
    assert result['actual_release_observations']['different_release']==1 and result['batch_release_observations']=={'same_release':0,'different_release':2}

@pytest.mark.parametrize('case',['deployment_authorization','batch_deployment','batch_authorization','line'])
def test_broken_references_keep_original_parent_semantics(asr,case):
    db,r,_,_,_,dep,_,_,batches,*_=asr
    if case=='deployment_authorization':dep.authorization_id=uuid.uuid4()
    elif case=='batch_deployment':batches[0].deployment_id=uuid.uuid4()
    elif case=='batch_authorization':batches[0].authorization_id=uuid.uuid4()
    else:dep.production_line_id=uuid.uuid4()
    db.commit();summary=application_release_downstream_summary(r.id,db);legacy=application_release_downstream(r.id,db)
    assert summary['history_counts']=={k:len(v) for k,v in legacy.items()}
    for kind in ['deployments','changeovers','batches']:assert production_catalog(kind,ProductionFilters(authorization_release_id=r.id),db)['total']==summary['history_counts'][kind]

def test_growth_has_seven_queries_no_child_rows_id_lists_or_large_payload(asr):
    db,r,_,old,auth,dep,*_=asr;calls=[]
    def capture(_conn,_cursor,statement,*_args):calls.append(statement.lower())
    def read():
        rid=r.id;db.expire_all();calls.clear();result=application_release_downstream_summary(rid,db);return result,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        _,initial=read()
        for n in range(105):
            p=DeliveryPackage(package_no=f'G-{n}',release_id=r.id,snapshot_id=old.id,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION');db.add(p);db.flush()
            db.add(Distribution(distribution_no=f'G-D-{n}',delivery_package_id=p.id,recipient_type='CUSTOMER',recipient_code='C',note='private body'*1000))
            db.add(SoftwareAuthorization(authorization_no=f'G-A-{n}',release_id=r.id,snapshot_id=old.id,customer_id=auth[0].customer_id,project_id=auth[0].project_id,site_code='SITE',line_code='LINE',restriction_note='private body'*1000))
            d=Deployment(deployment_no=f'G-DEP-{n}',authorization_id=auth[0].id,production_line_id=dep.production_line_id,expected_release_id=r.id,expected_snapshot_id=old.id);db.add(d);db.flush()
            db.add_all([SoftwareChangeover(changeover_no=f'G-CO-{n}',deployment_id=d.id,authorization_id=auth[0].id,from_release_id=r.id,to_release_id=r.id,note='private body'*1000),ProductionBatch(batch_no=f'G-B-{n}',deployment_id=d.id,authorization_id=auth[0].id,release_id=r.id,snapshot_id=old.id,status='COMPLETED',note='private body'*1000)])
        db.commit();result,grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert result['history_counts']=={'deliveries':107,'distributions':107,'authorizations':107,'deployments':107,'changeovers':106,'batches':107}
    assert len(initial)==len(grown)==7 and all('count(' in q for q in grown[1:])
    assert not any('.note' in q or '.restriction_note' in q or 'from release_snapshots' in q for q in grown)
    assert 'private body' not in str(result)

def test_http_read_only_validation_and_catalog_scope(asr,monkeypatch):
    from app import main
    db,r,*_=asr;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as conn:db.connection().connection.driver_connection.backup(conn.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            base='/api/v1/releases/application/id/';path='/api/v1/production/catalog/batches'
            assert client.get(base+str(r.id)+'/downstream-summary').json()['history_counts']['batches']==2
            assert client.get(base+'bad/downstream-summary').status_code==422
            assert client.get(base+str(uuid.uuid4())+'/downstream-summary').status_code==404
            response=client.get(path,params={'authorization_release_id':str(r.id),'limit':1});assert response.status_code==200 and response.json()['total']==2
            assert client.get(path+'?authorization_release_id=bad').status_code==422
            assert client.post('/api/v1/deployments/DEP/batches',json={}).json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()

def test_migrated_postgres_aggregates_filter_and_no_audit_write(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);r.release_type='APPLICATION';other=Release(software_id=r.software_id,release_type='STANDARD',version='other');db.add(other);db.flush()
        dep=db.scalars(select(Deployment).order_by(Deployment.deployment_no)).first();dep.actual_release_id=other.id
        db.add_all([ProductionBatch(batch_no='MISMATCH',deployment_id=dep.id,authorization_id=ids['authorization'],release_id=other.id,snapshot_id=dep.actual_snapshot_id),SoftwareChangeover(changeover_no='HISTORY',deployment_id=dep.id,authorization_id=ids['authorization'],from_release_id=r.id,to_release_id=other.id)]);db.commit()
        before=db.scalar(select(func.count()).select_from(AuditEvent));result=application_release_downstream_summary(r.id,db)
        assert result['history_counts']=={'deliveries':0,'distributions':0,'authorizations':1,'deployments':2,'changeovers':1,'batches':1}
        assert result['actual_release_observations']=={'same_release':1,'different_release':1,'not_reported':0} and result['batch_release_observations']=={'same_release':0,'different_release':1}
        for kind in ['deployments','changeovers','batches']:assert production_catalog(kind,ProductionFilters(authorization_release_id=r.id),db)['total']==result['history_counts'][kind]
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
