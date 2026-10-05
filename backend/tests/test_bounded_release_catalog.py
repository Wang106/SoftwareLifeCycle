"""Catalog parity, growth, exact ambiguity and strict HTTP contracts."""
import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.release_catalog import Filters, Resolution, release_catalog, resolve_application
from app.api.dashboard import list_application_releases, list_standard_releases
from app.core.db import get_db
from app.main import app
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot
from app.models.audit import AuditEvent


def applications(db, r, n=3):
    customer=Customer(code=str(uuid.uuid4()),name='Customer_%');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='P',name='Project');db.add(project);db.flush()
    rows=[]
    for i in range(n):
        a=Release(software_id=r.software_id,release_type='APPLICATION',version=f'v{i}',created_at=datetime(2026,1,1));db.add(a);db.flush()
        db.add(ApplicationReleaseDetail(release_id=a.id,customer_id=customer.id,project_id=project.id,standard_base_release_id=r.id))
        for number in range(1,4):
            db.add(ReleaseSnapshot(release_id=a.id,snapshot_no=f'S-{a.id}-{number}',snapshot_number=number,content_hash='a'*64,status='FROZEN'))
        rows.append(a)
    db.commit();return rows


@pytest.mark.parametrize('kind',['application','standard'])
def test_legacy_row_parity_and_all_pages(context,kind):
    db,_,r,*_=context;applications(db,r)
    legacy=(list_application_releases if kind=='application' else list_standard_releases)(db)
    result=release_catalog(kind,Filters(limit=1),db);rows=[]
    while True:
        rows+=result['items']
        if result['next_offset'] is None:break
        result=release_catalog(kind,Filters(limit=1,offset=result['next_offset']),db)
    assert rows==legacy and result['total']==len(legacy)
    assert release_catalog(kind,Filters(offset=999),db)['items']==[]
    assert release_catalog(kind,Filters(offset=999),db)['total']==len(legacy)


def test_filters_escape_and_missing_metadata(context):
    db,_,r,*_=context;rows=applications(db,r)
    assert release_catalog('application',Filters(q='_%',status='DRAFT',software_id=r.software_id),db)['total']==3
    assert release_catalog('application',Filters(q='not-found'),db)['total']==0
    assert release_catalog('standard',Filters(status='DRAFT'),db)['total']==0
    assert release_catalog('standard',Filters(q='BMS'),db)['total']==1
    db.delete(db.get(ApplicationReleaseDetail,rows[0].id));db.commit()
    item=next(x for x in release_catalog('application',Filters(),db)['items'] if x['id']==str(rows[0].id))
    assert item['customer'] is item['project'] is item['base_id'] is item['base_version'] is None
    # Broken optional metadata stays visible rather than removing its release.
    detail=db.get(ApplicationReleaseDetail,rows[1].id);detail.customer_id=uuid.uuid4();detail.project_id=uuid.uuid4();detail.standard_base_release_id=uuid.uuid4();db.commit()
    item=next(x for x in release_catalog('application',Filters(),db)['items'] if x['id']==str(rows[1].id))
    assert item['customer'] is item['project'] is item['base_version'] is None and item['base_id']==str(detail.standard_base_release_id)


def test_resolution_exact_version_uuid_ambiguity_and_missing(context):
    db,_,r,*_=context;a=applications(db,r,1)[0]
    for identifier in [a.version,str(a.id)]:
        result=resolve_application(Resolution(identifier=identifier),db)
        assert result=={'state':'unique','release':{'id':str(a.id),'version':a.version}}
    for identifier in [r.version,str(r.id),'absent','V0',' v0']:
        assert resolve_application(Resolution(identifier=identifier),db)=={'state':'missing','release':None}
    product=SoftwareProduct(supplier_id=db.get(SoftwareProduct,r.software_id).supplier_id,code='OTHER',name='Other');db.add(product);db.flush()
    other=Release(software_id=product.id,release_type='APPLICATION',version=a.version);db.add(other);db.commit()
    assert resolve_application(Resolution(identifier=a.version),db)['state']=='ambiguous'
    other.version=str(a.id);db.commit()
    assert resolve_application(Resolution(identifier=str(a.id)),db)['state']=='ambiguous'


def test_old_release_beyond_200_and_constant_queries(context):
    db,_,r,*_=context;rows=applications(db,r,205);rid=r.id;old_version=rows[-1].version
    calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql.lower())
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();result=release_catalog('application',Filters(limit=2,offset=200),db)
        assert result['total']==205 and len(result['items'])==2 and result['next_offset']==202
        assert len(calls)==2 and 'limit' in calls[-1]
        assert not db.identity_map
        calls.clear();resolved=resolve_application(Resolution(identifier=old_version),db)
        assert resolved['state']=='unique' and len(calls)==1 and 'limit' in calls[0]
    finally:event.remove(db.bind,'before_cursor_execute',capture)


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001','unknown=1','software_id=bad','limit=1&limit=invalid'])
def test_http_strict_invalid_filters(context,query):
    db,*_=context;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as conn:db.connection().connection.driver_connection.backup(conn.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db]=lambda:route_db
        try:
            with TestClient(app) as client:
                assert client.get('/api/v1/release-catalog/application?'+query).status_code==422
        finally:app.dependency_overrides.pop(get_db,None)
    engine.dispose()


def test_http_resolver_and_readonly(context,monkeypatch):
    from app import main
    db,_,r,*_=context;a=applications(db,r,1)[0]
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as conn:db.connection().connection.driver_connection.backup(conn.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
        try:
            with TestClient(app) as client:
                assert client.get('/api/v1/release-catalog/application/resolve',params={'identifier':str(a.id)}).json()['state']=='unique'
                for q in ['', '?identifier=', '?identifier=x&unknown=1','?identifier='+('x'*101)]:
                    assert client.get('/api/v1/release-catalog/application/resolve'+q).status_code==422
                assert client.get('/api/v1/release-catalog/invalid').status_code==422
                assert client.get('/api/v1/release-catalog/standard?limit=1').json()['total']==1
                assert client.post(f'/api/v1/releases/{r.id}/create-snapshot',json={}).json()=={'detail':'read_only_mode'}
        finally:app.dependency_overrides.pop(get_db,None)
    engine.dispose()


def test_migrated_postgresql_old_pages_and_no_audit(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);rows=applications(db,r,205)
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        data=release_catalog('application',Filters(limit=1,offset=204),db)
        assert data['total']==205 and len(data['items'])==1 and data['next_offset'] is None
        assert resolve_application(Resolution(identifier=rows[-1].version),db)['state']=='unique'
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before


def test_standard_growth_and_nullable_metadata(context):
    db,_,r,*_=context
    for i in range(205):db.add(Release(software_id=r.software_id,release_type='STANDARD',version=f'S{i}'))
    db.commit()
    result=release_catalog('standard',Filters(limit=1,offset=205),db)
    assert result['total']==206 and len(result['items'])==1 and result['next_offset'] is None
    product=db.get(SoftwareProduct,r.software_id);db.delete(product);db.commit()
    assert all(x['software'] is x['supplier'] is None for x in release_catalog('standard',Filters(limit=2),db)['items'])


def test_snapshot_growth_preserves_single_latest_projection(context):
    db,_,r,*_=context;a=applications(db,r,1)[0];aid=a.id;calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();small=release_catalog('application',Filters(limit=1),db);initial=list(calls)
        for n in range(4,124):db.add(ReleaseSnapshot(release_id=aid,snapshot_no=f'NEW-{n}',snapshot_number=n,content_hash='b'*64,status='FROZEN'))
        db.commit();db.expunge_all();calls.clear();large=release_catalog('application',Filters(limit=1),db)
        assert large['total']==small['total']==1 and large['items'][0]['snapshot_no']=='NEW-123'
        assert calls==initial and not db.identity_map
    finally:event.remove(db.bind,'before_cursor_execute',capture)
