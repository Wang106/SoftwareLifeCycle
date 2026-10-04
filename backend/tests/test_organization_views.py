import uuid
from datetime import datetime
import pytest
from sqlalchemy import event, func, select
from app.api import organization_views as v, organizations as legacy
from app.models.core import Supplier, Customer, Project, SoftwareProduct, Release, ApplicationReleaseDetail
from app.models.production import ManufacturingSite
from app.models.audit import AuditEvent
from test_impact_assessments import context
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.db import get_db
from app.main import app
from test_command_concurrency_postgres import pg


def grow(db, count=5):
    for n in range(count):
        s=Supplier(code=f'G-{n:04}',name=f'Literal_% supplier {n}',country='CN',description='Long text '*1000)
        c=Customer(code=f'G-{n:04}',name=f'Literal_% customer {n}',region='APAC' if n%2 else None)
        db.add_all([s,c]);db.flush()
        sw=SoftwareProduct(supplier_id=s.id,code=f'G-{n:04}',name='Product')
        p=Project(customer_id=c.id,project_code='SAME' if n<2 else f'G-{n:04}',name=f'Literal_% project {n}')
        db.add_all([sw,p]);db.flush()
        r=Release(software_id=sw.id,release_type='STANDARD',version='1',created_at=datetime(2026,1,1));db.add(r);db.flush()
        a=Release(software_id=sw.id,release_type='APPLICATION',version='2',created_at=datetime(2026,1,1));db.add(a);db.flush()
        db.add(ApplicationReleaseDetail(release_id=a.id,customer_id=c.id,project_id=p.id,standard_base_release_id=r.id))
        db.add(ManufacturingSite(site_code=f'G-{n:04}',name='Site',customer_id=c.id,project_id=p.id))
    db.commit()


KINDS=[('suppliers',v.supplier_catalog,v.SupplierFilters,legacy.list_suppliers,'software'),
       ('customers',v.customer_catalog,v.CustomerFilters,legacy.list_customers,'projects'),
       ('projects',v.project_catalog,v.ProjectFilters,legacy.list_projects,'sites')]


@pytest.mark.parametrize('kind,fn,filters,old,child',KINDS)
def test_legacy_parent_owned_page_parity(context,kind,fn,filters,old,child):
    db,*_=context;grow(db);original=old(db);seen=[];offset=0
    while True:
        page=fn(filters(limit=1,offset=offset),db);seen+=page['items'];assert page['total']==len(original)
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert {x['id'] for x in seen}=={x['id'] for x in original}
    by_id={x['id']:x for x in original}
    for row in seen:
        before=by_id[row['id']]
        for field in ['code','name','status']:assert row[field]==before[field]
        count_field={'suppliers':'software_count','customers':'project_count','projects':'site_count'}[kind]
        assert row[count_field]==len(before[child])
        identifier=row['id'] if kind=='projects' else row['code']
        summary=v.summary(kind,identifier,v.Empty(),db)
        if kind=='suppliers':assert summary['description']==before['description'] and 'description' not in row
        if kind=='customers':assert row['released_project_count']==sum(bool(x['release']) for x in before['projects'])
        if kind=='projects':assert row['release_id']==(before['release']['id'] if before['release'] else None)
        children=v.items(kind,identifier,v.OwnedPage(organization_id=row['id'],limit=1),db)
        assert children['total']==len(before[child]) and len(children['items'])<=1
        for x in children['items']:
            prev=next(y for y in before[child] if y['code']==x['code'])
            assert x['name']==prev['name'] and x['status']==prev['status']
            if kind=='suppliers':assert x['release_version']==prev['standard_version']
            if kind=='customers':assert x['release_id']==(prev['release']['id'] if prev['release'] else None)
        beyond=v.items(kind,identifier,v.OwnedPage(organization_id=row['id'],offset=100000),db)
        assert beyond['total']==len(before[child]) and beyond['items']==[] and beyond['next_offset'] is None
    assert fn(filters(offset=100000),db)['total']==len(original)


def test_literal_exact_filters_ambiguous_project(context):
    db,*_=context;grow(db)
    assert v.supplier_catalog(v.SupplierFilters(q='_%',country='CN',status='ACTIVE'),db)['total']==5
    assert v.supplier_catalog(v.SupplierFilters(country='cn'),db)['total']==0
    assert v.customer_catalog(v.CustomerFilters(region='UNASSIGNED',q='_%'),db)['total']==3
    assert v.customer_catalog(v.CustomerFilters(region='APAC'),db)['total']==2
    customer=db.scalar(select(Customer).where(Customer.code=='G-0000'))
    assert v.project_catalog(v.ProjectFilters(customer_id=customer.id),db)['total']==1
    with pytest.raises(v.HTTPException) as e:v.parent('projects','SAME',db)
    assert e.value.status_code==409
    project=db.scalar(select(Project).where(Project.customer_id==customer.id))
    assert v.parent('projects',str(project.id),db)['id']==str(project.id)


def test_customer_release_membership_does_not_infer_customer_from_project(context):
    db,*_=context;grow(db,2)
    c0=db.scalar(select(Customer).where(Customer.code=='G-0000'));c1=db.scalar(select(Customer).where(Customer.code=='G-0001'))
    p=db.scalar(select(Project).where(Project.customer_id==c0.id))
    detail=db.scalar(select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.project_id==p.id))
    detail.customer_id=c1.id;db.commit()
    assert v.parent('customers',c0.code,db)['released_project_count']==0
    assert v.items('customers',c0.code,v.OwnedPage(organization_id=c0.id),db)['items'][0]['release_id'] is None
    assert v.parent('projects',str(p.id),db)['release_id']==str(detail.release_id)


@pytest.mark.parametrize('kind,fn,filters,old,child',KINDS)
def test_two_constant_scalar_catalog_queries_as_parents_grow(context,kind,fn,filters,old,child):
    db,*_=context;calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();baseline=fn(filters(limit=2),db)['total'];small=list(calls)
        grow(db,205);db.expunge_all();calls.clear();page=fn(filters(limit=2),db)
        assert page['total']==baseline+205 and len(page['items'])==2
        assert calls==small and len(calls)==2 and not db.identity_map
        assert 'LIMIT' in calls[-1] and 'description' not in calls[-1] and ' IN (' not in calls[-1]
    finally:event.remove(db.bind,'before_cursor_execute',capture)


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001','unknown=1','q='+('x'*201),'status='+('x'*31),'limit=1&limit=invalid'])
def test_strict_shared_filters(http,query):
    for kind,*_ in KINDS:assert http.get('/api/v1/organization-views/'+kind+'?'+query).status_code==422


def test_exact_owned_pins_kind_filters_and_readonly(http,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    for kind,*_ in KINDS:
        row=http.get('/api/v1/organization-views/'+kind+'?limit=1').json()['items'][0]
        identifier=row['id'] if kind=='projects' else row['code'];base=f'/api/v1/organization-views/{kind}/{identifier}'
        assert http.get(base+'/summary').status_code==200
        for suffix in ['/summary?limit=1','/items','/items?organization_id=bad']:assert http.get(base+suffix).status_code==422
        assert http.get(base+'/items?organization_id='+str(uuid.uuid4())).status_code==404
        assert http.get(base+'/items?organization_id='+row['id']+'&limit=1').status_code==200
    for kind,query in [('customers','region=bad'),('suppliers','region=APAC'),('projects','customer_id=bad'),('customers','country=CN')]:
        assert http.get(f'/api/v1/organization-views/{kind}?{query}').status_code==422
    assert http.get('/api/v1/organization-views/unknown/no/summary').status_code==404
    assert http.post('/api/v1/deployments',json={}).json()=={'detail':'read_only_mode'}


def test_real_postgresql_full_counts_latest_ties_and_no_audit_writes(pg):
    engine,_=pg
    with v.Session(engine) as db:
        grow(db,205);before=db.scalar(select(func.count()).select_from(AuditEvent))
        for kind,fn,filters,*_ in KINDS:
            page=fn(filters(q='_%',limit=1,offset=204),db)
            assert page['total']==205 and len(page['items'])==1 and page['next_offset'] is None
        s=db.scalar(select(Supplier).where(Supplier.code=='G-0000'));sw=db.scalar(select(SoftwareProduct).where(SoftwareProduct.supplier_id==s.id))
        db.add(Release(software_id=sw.id,release_type='STANDARD',version='tied',created_at=datetime(2026,1,1)));db.commit()
        expected=db.scalar(select(Release.id).where(Release.software_id==sw.id,Release.release_type=='STANDARD')
            .order_by(Release.created_at.desc(),Release.id.desc()).limit(1))
        assert v.items('suppliers',s.code,v.OwnedPage(organization_id=s.id,limit=1),db)['items'][0]['release_id']==str(expected)
        assert v.customer_catalog(v.CustomerFilters(region='APAC'),db)['total']==102
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before


@pytest.fixture
def http(context):
    db,*_=context;grow(db,2)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db]=lambda:route_db
        try:
            with TestClient(app) as client:yield client
        finally:app.dependency_overrides.pop(get_db,None)
    engine.dispose()


@pytest.mark.parametrize('kind',['suppliers','customers','projects'])
def test_owned_child_growth_fixed_shape_complete_counts_and_disjoint_pages(context,kind):
    db,*_=context;grow(db,1)
    model={'suppliers':Supplier,'customers':Customer,'projects':Project}[kind]
    owner=db.scalar(select(model).where(model.code=='G-0000')) if kind!='projects' else db.scalar(select(Project).where(Project.project_code=='SAME'))
    key=owner.id;identifier=str(key) if kind=='projects' else owner.code
    calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();v.items(kind,identifier,v.OwnedPage(organization_id=key,limit=2),db);small=list(calls)
        for n in range(120):
            if kind=='suppliers':x=SoftwareProduct(supplier_id=key,code=f'CH-{n:04}',name='Child')
            elif kind=='customers':x=Project(customer_id=key,project_code=f'CH-{n:04}',name='Child')
            else:
                customer_id=db.scalar(select(Project.customer_id).where(Project.id==key))
                x=ManufacturingSite(site_code=f'CH-{n:04}',name='Child',customer_id=customer_id,project_id=key)
            db.add(x)
        db.commit();db.expunge_all();calls.clear()
        first=v.items(kind,identifier,v.OwnedPage(organization_id=key,limit=2),db)
        assert first['total']==121 and len(first['items'])==2 and calls==small and len(calls)==3 and not db.identity_map
        second=v.items(kind,identifier,v.OwnedPage(organization_id=key,limit=2,offset=2),db)
        assert len({x['id'] for x in first['items']+second['items']})==4
    finally:event.remove(db.bind,'before_cursor_execute',capture)


def test_project_survives_missing_optional_customer_display_metadata(context):
    db,*_=context;grow(db,1)
    p=db.scalar(select(Project).where(Project.project_code=='SAME'));key=p.id
    c=db.get(Customer,p.customer_id);db.delete(c);db.commit()
    row=v.parent('projects',str(key),db)
    assert row['id']==str(key) and row['customer_name'] is None and row['customer_code'] is None and row['site_count']==1


def test_blank_region_is_all_and_country_unassigned_is_literal(context):
    db,*_=context;grow(db,1)
    assert v.customer_catalog(v.CustomerFilters(region=''),db)['total']==1
    s=db.scalar(select(Supplier).where(Supplier.code=='G-0000'));s.country='UNASSIGNED';db.commit()
    page=v.supplier_catalog(v.SupplierFilters(country='UNASSIGNED'),db)
    assert page['total']==1 and page['items'][0]['country']=='UNASSIGNED'
