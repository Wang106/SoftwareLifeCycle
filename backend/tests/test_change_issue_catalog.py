"""Bounded directory parity, complete statistics, literal filters and growth."""
import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.change_catalog import ChangeFilters, IssueFilters, change_catalog, issue_catalog
from app.api.dashboard import list_changes, list_issues
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.change import SoftwareChangeRequest, Issue
from app.models.core import Customer, Project


def add_rows(db, software_id, count=5):
    rows=[]
    states=['IN_TEST','READY_FOR_RELEASE','PRETEST_READY','test_ready','DRAFT']
    for n in range(count):
        c=SoftwareChangeRequest(request_no=f'GROW-{n:04}',title=f'Literal_% title {n}',
            source='ISSUE' if n%2 else 'INTERNAL',scope='APPLICATION' if n%2 else 'STANDARD',
            change_type='BUG_FIX',software_id=software_id,status=states[n%5],created_at=datetime(2026,1,1))
        i=Issue(issue_no=f'GROW-{n:04}',title=f'Literal_% title {n}',scope=c.scope,
            severity='HIGH' if n%2 else 'LOW',status='CLOSED' if n%2 else 'OPEN',description='Long text '*2000)
        db.add_all([c,i]);rows.append(c)
    db.commit();return rows


@pytest.mark.parametrize('kind',['changes','issues'])
def test_directory_projection_parity_and_complete_pages(context,kind):
    db,_,r,*_=context;add_rows(db,r.software_id)
    fn,q,legacy=(change_catalog,ChangeFilters,list_changes) if kind=='changes' else (issue_catalog,IssueFilters,list_issues)
    original=legacy(db);rows=[];offset=0
    while True:
        page=fn(q(limit=1,offset=offset),db);rows+=page['items'];assert page['total']==len(original)
        if page['next_offset'] is None:break
        offset=page['next_offset']
    expected=[{k:v for k,v in x.items() if k!='description'} for x in original]
    assert {x['id']:x for x in rows}=={x['id']:x for x in expected}
    empty=fn(q(offset=999),db);assert empty['total']==len(original) and empty['items']==[] and empty['next_offset'] is None


def test_scr_complete_case_sensitive_statistics_not_current_page(context):
    db,_,r,*_=context;add_rows(db,r.software_id)
    page=change_catalog(ChangeFilters(limit=1),db)
    assert page['total']==6 and page['in_verification']==2 and page['ready_for_release']==2
    beyond=change_catalog(ChangeFilters(offset=999),db)
    assert beyond['in_verification']==beyond['ready_for_release']==2 and beyond['items']==[]
    filtered=change_catalog(ChangeFilters(status='test_ready'),db)
    assert filtered['total']==1 and filtered['in_verification']==filtered['ready_for_release']==0
    empty=change_catalog(ChangeFilters(q='no match'),db)
    assert empty['total']==empty['in_verification']==empty['ready_for_release']==0


def test_filters_are_literal_exact_and_keep_scoped_associations(context):
    db,_,r,*_=context;rows=add_rows(db,r.software_id)
    customer=Customer(code='SCOPE',name='Customer');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='P',name='Project');db.add(project);db.flush()
    rows[0].customer_id=customer.id;rows[0].project_id=project.id;db.commit()
    assert change_catalog(ChangeFilters(q='_%'),db)['total']==5
    assert change_catalog(ChangeFilters(q='_%',scope='APPLICATION',source='ISSUE',change_type='BUG_FIX',software_id=r.software_id),db)['total']==2
    assert change_catalog(ChangeFilters(project_id=project.id,customer_id=customer.id),db)['total']==1
    assert change_catalog(ChangeFilters(software_id=uuid.uuid4()),db)['total']==0
    assert issue_catalog(IssueFilters(q='_%',scope='APPLICATION',severity='HIGH',status='CLOSED'),db)['total']==2
    assert issue_catalog(IssueFilters(severity='not-known'),db)['total']==0


@pytest.mark.parametrize('kind',['changes','issues'])
def test_constant_query_shape_bounded_scalar_transfer_as_catalog_grows(context,kind):
    db,_,r,*_=context;software_id=r.software_id
    fn,q=(change_catalog,ChangeFilters) if kind=='changes' else (issue_catalog,IssueFilters)
    calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        db.expunge_all();first=fn(q(limit=2),db);small=list(calls)
        add_rows(db,software_id,205);db.expunge_all();calls.clear();large=fn(q(limit=2),db)
        assert large['total']==206 and len(large['items'])==2 and calls==small and len(calls)==2
        assert not db.identity_map and 'LIMIT' in calls[-1]
        assert 'description' not in calls[-1] and 'change_points' not in calls[-1]
    finally:event.remove(db.bind,'before_cursor_execute',capture)


def test_tied_scr_times_and_issue_numbers_page_without_duplicates(context):
    db,_,r,*_=context;add_rows(db,r.software_id)
    for fn,q in [(change_catalog,ChangeFilters),(issue_catalog,IssueFilters)]:
        first=fn(q(limit=2),db);second=fn(q(limit=2,offset=2),db)
        assert len({x['id'] for x in first['items']+second['items']})==4
        assert first==fn(q(limit=2),db)


@pytest.fixture
def http(context):
    db,*_=context;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    with Session(engine) as route_db:
        app.dependency_overrides[get_db]=lambda:route_db
        try:
            with TestClient(app) as client:yield client
        finally:app.dependency_overrides.pop(get_db,None)
    engine.dispose()


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001','unknown=1','status='+('x'*41),'q='+('x'*201),'limit=1&limit=invalid'])
def test_strict_http_shared_filters(http,query):
    for endpoint in ['requests','issues']:
        assert http.get('/api/v1/change-catalog/'+endpoint+'?'+query).status_code==422


def test_strict_http_kind_specific_fields_and_readonly(http,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    for query in ['software_id=bad','project_id=bad','customer_id=bad','severity=HIGH']:
        assert http.get('/api/v1/change-catalog/requests?'+query).status_code==422
    for query in ['software_id='+str(uuid.uuid4()),'source=ISSUE','severity='+('x'*21)]:
        assert http.get('/api/v1/change-catalog/issues?'+query).status_code==422
    for endpoint in ['requests','issues']:
        response=http.get('/api/v1/change-catalog/'+endpoint+'?limit=1');assert response.status_code==200 and response.json()['total']==1
    response=http.post('/api/v1/deployments',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}


def test_migrated_postgresql_complete_totals_and_case_sensitive_statistics(pg):
    engine,ids=pg
    with Session(engine) as db:
        from app.models.core import Release
        r=db.get(Release,ids['release']);add_rows(db,r.software_id,205)
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        for fn,q in [(change_catalog,ChangeFilters),(issue_catalog,IssueFilters)]:
            page=fn(q(limit=1,offset=204),db);assert page['total']==205 and len(page['items'])==1 and page['next_offset'] is None
        stats=change_catalog(ChangeFilters(limit=1),db);assert stats['in_verification']==stats['ready_for_release']==82
        assert change_catalog(ChangeFilters(status='test_ready'),db)['in_verification']==0
        assert issue_catalog(IssueFilters(q='_%',severity='HIGH'),db)['total']==102
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
