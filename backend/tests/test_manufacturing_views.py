"""Bounded manufacturing reads preserve legacy stored-state and context semantics."""
import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api import manufacturing_views as v
from app.api.production import list_sites, get_site
from app.core.db import get_db
from app.main import app
from app.models.core import Customer, Project, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.distribution import SoftwareAuthorization as Authorization
from app.models.production import ManufacturingSite as Site, ProductionLine as Line, Deployment, ProductionBatch as Batch, SoftwareChangeover as Changeover
from app.models.audit import AuditEvent
from test_impact_assessments import context
from test_command_concurrency_postgres import pg


def seed(db):
    r=db.scalar(select(Release));s=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==r.id))
    c=Customer(code='MV-C',name='Customer');db.add(c);db.flush()
    p=Project(customer_id=c.id,project_code='MV-P',name='Project');db.add(p);db.flush()
    site=Site(site_code='MV-S',name='Literal_% factory',region='APAC',customer_id=c.id,project_id=p.id);db.add(site);db.flush()
    a=Authorization(authorization_no='MV-A',release_id=r.id,snapshot_id=s.id,customer_id=c.id,project_id=p.id,site_code=site.site_code,line_code='A',purpose='PRODUCTION',status='APPROVED')
    revoked=Authorization(authorization_no='MV-R',release_id=r.id,snapshot_id=s.id,customer_id=c.id,project_id=p.id,site_code=site.site_code,line_code='B',purpose='PRODUCTION',status='REVOKED')
    db.add_all([a,revoked]);db.flush();lines=[];deps=[]
    for n in range(4):
        line=Line(site_id=site.id,line_code=chr(65+n),name=f'{n} Line');db.add(line);db.flush();lines.append(line)
        if n==2:continue
        dep=Deployment(deployment_no=f'MV-D-{n}',production_line_id=line.id,authorization_id=revoked.id if n==1 else a.id,
            expected_release_id=r.id,expected_snapshot_id=s.id,status='PENDING' if n==1 else 'MATCH',
            actual_release_id=r.id if n==0 else None,actual_snapshot_id=s.id if n==0 else None,created_at=datetime(2026,1,1))
        db.add(dep);db.flush();deps.append(dep)
    db.add(Deployment(deployment_no='MV-OLD',production_line_id=lines[0].id,authorization_id=a.id,
        expected_release_id=r.id,expected_snapshot_id=s.id,status='MISMATCH',created_at=datetime(2025,1,1)))
    for n in range(2):
        db.add(Batch(batch_no=f'MV-B-{n}',deployment_id=deps[0].id,authorization_id=a.id,release_id=r.id,snapshot_id=s.id,
            status='COMPLETED' if n==0 else 'ACTIVE',started_at=datetime(2026+n,2,1),note=f'Original note {n}'))
        db.add(Changeover(changeover_no=f'MV-X-{n}',deployment_id=deps[0].id,authorization_id=a.id,
            from_release_id=r.id,to_release_id=r.id,changed_at=datetime(2026+n,2,1),status='PLANNED'))
    db.commit();return site,lines,deps


def test_catalog_scalar_counts_and_owned_line_pages_match_legacy(context):
    db,*_=context;site,ls,ds=seed(db)
    old=list_sites(db)[0];new=v.catalog(v.Filters(limit=1),db)['items'][0]
    for key in ['id','site_code','name','region','status','line_count','deployed_line_count','matching_line_count','attention_line_count']:
        assert new[key]==old[key]
    assert new['matching_line_count']==2 and new['attention_line_count']==1 # Stored MATCH retained even without actual report.
    before=get_site(site.site_code,db);summary=v.summary(site.site_code,v.Empty(),db)
    assert summary['approved_authorization_line_count']==2 and summary['first_authorization_no']=='MV-A'
    assert summary['context_batch_batch_no']=='MV-B-0' and summary['context_batch_status']=='COMPLETED'
    assert summary['first_changeover_changeover_no']=='MV-X-0'
    assert summary['first_deployment_id']==str(ds[0].id) and summary['first_expected_release_id']==str(ds[0].expected_release_id)
    seen=[];offset=0
    while True:
        page=v.lines(site.site_code,v.OwnedPage(site_id=site.id,limit=1,offset=offset),db)
        assert page['total']==4;seen+=page['items']
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert len({x['id'] for x in seen})==4
    for row,old_line in zip(seen,before['lines']):
        assert row['id']==old_line['id'] and row['line_code']==old_line['line_code']
        dep=old_line['deployment'];assert row['deployment_id']==(dep['id'] if dep else None)
        if dep:
            assert row['deployment_status']==dep['status'] and row['expected_version']==dep['expected']['version']
            assert row['authorization_no']==dep['authorization']['authorization_no']
        assert 'batches' not in row and 'changeovers' not in row
    beyond=v.lines(site.site_code,v.OwnedPage(site_id=site.id,offset=100000),db)
    assert beyond['total']==4 and beyond['items']==[] and beyond['next_offset'] is None


def test_exact_filters_empty_results_and_uuid_or_code_identity(context):
    db,*_=context;site,_,_=seed(db)
    assert v.catalog(v.Filters(q='_%',region='APAC',status='ACTIVE',customer_id=site.customer_id,project_id=site.project_id),db)['total']==1
    assert v.catalog(v.Filters(q='NOT PRESENT'),db)['total']==0
    assert v.catalog(v.Filters(region='apac'),db)['total']==0
    assert v.catalog(v.Filters(customer_id=uuid.uuid4()),db)['total']==0
    assert v.parent(str(site.id).upper(),db)['id']==str(site.id)
    assert v.parent(str(site.id).replace('-',''),db)['id']==str(site.id)
    other=Site(site_code=str(site.id),name='Collision',customer_id=site.customer_id,project_id=site.project_id);db.add(other);db.commit()
    with pytest.raises(v.HTTPException) as e:v.parent(str(site.id),db)
    assert e.value.status_code==409


def test_empty_site_and_missing_metadata_do_not_invent_context(context):
    db,*_=context;site,ls,ds=seed(db)
    empty=Site(site_code='EMPTY',name='Empty',customer_id=site.customer_id,project_id=site.project_id);db.add(empty);db.commit()
    row=v.parent(empty.site_code,db)
    assert row['line_count']==row['matching_line_count']==row['approved_authorization_line_count']==0
    assert row['first_deployment_id'] is None and row['context_batch_id'] is None
    ds[0].authorization_id=uuid.uuid4();ds[0].expected_release_id=uuid.uuid4();db.delete(db.get(Customer,site.customer_id));db.commit()
    row=v.parent(site.site_code,db)
    assert row['customer_name'] is None and row['customer_id']==str(site.customer_id)
    assert row['first_authorization_id']==str(ds[0].authorization_id) and row['first_authorization_no'] is None
    assert row['first_expected_release_id']==str(ds[0].expected_release_id) and row['first_expected_version'] is None
    assert row['line_count']==4 and row['approved_authorization_line_count']==1


def test_context_ignores_older_deployment_history_and_foreign_site(context):
    db,*_=context;site,ls,ds=seed(db)
    old=db.scalar(select(Deployment).where(Deployment.deployment_no=='MV-OLD'))
    db.add(Batch(batch_no='OLD-BATCH',deployment_id=old.id,authorization_id=old.authorization_id,release_id=old.expected_release_id,snapshot_id=old.expected_snapshot_id,started_at=datetime(2020,1,1)))
    other=Site(site_code='FOREIGN',name='0 Foreign',customer_id=site.customer_id,project_id=site.project_id);db.add(other);db.flush()
    line=Line(site_id=other.id,line_code='A',name='0 Line');db.add(line);db.flush()
    dep=Deployment(deployment_no='FOREIGN-D',production_line_id=line.id,authorization_id=old.authorization_id,expected_release_id=old.expected_release_id,expected_snapshot_id=old.expected_snapshot_id,status='MATCH');db.add(dep);db.flush()
    db.add(Batch(batch_no='FOREIGN-B',deployment_id=dep.id,authorization_id=dep.authorization_id,release_id=dep.expected_release_id,snapshot_id=dep.expected_snapshot_id,started_at=datetime(2019,1,1)));db.commit()
    row=v.parent(site.site_code,db);assert row['context_batch_batch_no']=='MV-B-0' and row['line_count']==4


@pytest.mark.parametrize('kind',['catalog','summary','lines'])
def test_parent_and_child_growth_constant_sql_shapes_no_orm_graph(context,kind):
    db,*_=context;site,ls,ds=seed(db);site_id=site.id;code=site.site_code;customer_id=site.customer_id;project_id=site.project_id
    authorization_id=ds[0].authorization_id; release_id=ds[0].expected_release_id; snapshot_id=ds[0].expected_snapshot_id
    calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql)
    def read():
        return v.catalog(v.Filters(limit=2),db) if kind=='catalog' else v.parent(code,db) if kind=='summary' else v.lines(code,v.OwnedPage(site_id=site_id,limit=2),db)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();read();small=list(calls)
        for n in range(120):
            db.add(Site(site_code=f'G-{n}',name='Growth',customer_id=customer_id,project_id=project_id))
            line=Line(site_id=site_id,line_code=f'G-{n}',name='Tied growth');db.add(line);db.flush()
            db.add(Deployment(deployment_no=f'G-D-{n}',production_line_id=line.id,authorization_id=authorization_id,expected_release_id=release_id,expected_snapshot_id=snapshot_id,status='MATCH'))
        db.commit();db.expunge_all();calls.clear();data=read()
        assert calls==small and len(calls)=={'catalog':2,'summary':1,'lines':3}[kind] and not db.identity_map
        assert ' IN (' not in calls[-1]
        if kind=='catalog':assert data['total']==121 and len(data['items'])==2
        elif kind=='summary':assert data['line_count']==124
        else:
            assert data['total']==124 and len(data['items'])==2
            second=v.lines(code,v.OwnedPage(site_id=site_id,limit=2,offset=2),db)
            assert len({x['id'] for x in data['items']+second['items']})==4
    finally:event.remove(db.bind,'before_cursor_execute',capture)


@pytest.fixture
def http(context):
    db,*_=context;seed(db)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db]=lambda:route_db
        try:
            with TestClient(app) as client:yield client
        finally:app.dependency_overrides.pop(get_db,None)
    engine.dispose()


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001','unknown=1','q='+('x'*201),'region='+('x'*101),'customer_id=bad','project_id=bad','limit=1&limit=bad'])
def test_http_strict_catalog_filters(http,query):
    assert http.get('/api/v1/manufacturing-views/sites?'+query).status_code==422


def test_http_exact_pins_summary_validation_and_readonly(http,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    row=http.get('/api/v1/manufacturing-views/sites?limit=1').json()['items'][0];base='/api/v1/manufacturing-views/sites/'+row['id']
    assert http.get(base+'/summary').status_code==200 and http.get(base+'/summary?limit=1').status_code==422
    for query in ['', 'site_id=bad', 'site_id='+row['id']+'&limit=101']:
        assert http.get(base+'/lines?'+query).status_code==422
    assert http.get(base+'/lines?site_id='+str(uuid.uuid4())).status_code==404
    assert http.get(base+'/lines?site_id='+row['id']+'&limit=1').json()['total']==4
    assert http.get('/api/v1/manufacturing-views/sites/MISSING/summary').status_code==404
    assert http.post('/api/v1/deployments',json={}).json()=={'detail':'read_only_mode'}


def test_http_encoded_site_code_supported(http):
    db=app.dependency_overrides[get_db]();site=db.scalar(select(Site).where(Site.site_code=='MV-S'));site.site_code='MV / S';db.commit()
    response=http.get('/api/v1/manufacturing-views/sites/MV%20%2F%20S/summary');assert response.status_code==200 and response.json()['id']==str(site.id)
    assert http.get('/api/v1/manufacturing-views/sites/MV%20%2F%20S/lines?site_id='+str(site.id)).json()['total']==4


def test_real_postgresql_latest_ties_full_counts_context_and_read_purity(pg):
    engine,_=pg
    with Session(engine) as db:
        site,ls,ds=seed(db);before=db.scalar(select(func.count()).select_from(AuditEvent))
        # Same timestamp: higher exact UUID wins, independent of insertion order.
        newer=Deployment(id=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'),deployment_no='TIED',production_line_id=ls[0].id,authorization_id=ds[0].authorization_id,expected_release_id=ds[0].expected_release_id,expected_snapshot_id=ds[0].expected_snapshot_id,status='MISMATCH',created_at=datetime(2026,1,1));db.add(newer)
        for n in range(205):db.add(Line(site_id=site.id,line_code=f'G-{n}',name='Tied line'))
        db.commit()
        row=v.parent(site.site_code,db);assert row['line_count']==209 and row['first_deployment_id']==str(newer.id)
        assert row['matching_line_count']==1 and row['attention_line_count']==2 and row['context_batch_id'] is None
        page=v.lines(site.site_code,v.OwnedPage(site_id=site.id,limit=1,offset=208),db)
        assert page['total']==209 and len(page['items'])==1 and page['next_offset'] is None
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before


def test_first_empty_line_does_not_hide_later_recorded_batch(context):
    db,*_=context;site,ls,ds=seed(db)
    db.add(Line(site_id=site.id,line_code='FIRST',name='-1 Empty first'));db.commit()
    row=v.parent(site.site_code,db)
    assert row['first_deployment_id'] is None and row['first_authorization_no'] is None
    assert row['context_batch_batch_no']=='MV-B-0' and row['approved_authorization_line_count']==2
