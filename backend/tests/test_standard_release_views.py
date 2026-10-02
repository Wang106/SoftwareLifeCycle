"""Exact stored SSR associations, bounded transfer and migrated PostgreSQL."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.standard_release_views import CollectionPage, SummarySelection, standard_summary, standard_components, standard_applications
from app.api.dashboard import standard_release_profile
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, ComponentDefinition, Customer, Project, Release, ReleaseComponent, StandardReleaseDetail


def add_children(db, release, count=3, customer_id=None, project_id=None, prefix='C'):
    definition=ComponentDefinition(code=f'{prefix}-{uuid.uuid4()}',name='Controller');db.add(definition);db.flush()
    for n in range(count):
        db.add(ReleaseComponent(release_id=release.id,component_definition_id=definition.id,version='same'))
        application=Release(software_id=release.software_id,release_type='APPLICATION',version=f'{prefix}-{n}',status='DRAFT');db.add(application);db.flush()
        db.add(ApplicationReleaseDetail(release_id=application.id,customer_id=customer_id or uuid.uuid4(),project_id=project_id or uuid.uuid4(),standard_base_release_id=release.id))
    db.commit()


@pytest.fixture
def standard(context):
    db,_,release,*_=context
    db.add(StandardReleaseDetail(release_id=release.id,git_branch='main',git_commit='raw-commit'));add_children(db,release)
    return db,release


def test_summary_legacy_metadata_and_full_all_status_totals(standard):
    db,r=standard;legacy=standard_release_profile(r.id,db);summary=standard_summary(r.id,SummarySelection(),db)
    assert summary==({k:v for k,v in legacy.items() if k not in ['components','applications']}|{'component_count':3,'application_count':3})
    assert 'components' not in summary and 'applications' not in summary
    for fn,key in [(standard_components,'components'),(standard_applications,'applications')]:
        assert {i['id'] for i in fn(r.id,CollectionPage(),db)['items']}=={i['id'] for i in legacy[key]}


@pytest.mark.parametrize('fn',[standard_components,standard_applications])
def test_duplicate_stable_pages_and_beyond_end(standard,fn):
    db,r=standard;ids=[]
    for offset in range(3):
        result=fn(r.id,CollectionPage(limit=1,offset=offset),db)
        assert result['release_id']==str(r.id) and result['total']==3 and result['offset']==offset and result['limit']==1
        assert len(result['items'])==1 and result['next_offset']==(offset+1 if offset<2 else None)
        ids.append(result['items'][0]['id'])
    assert len(set(ids))==3
    assert [fn(r.id,CollectionPage(limit=1,offset=n),db)['items'][0]['id'] for n in range(3)]==ids
    beyond=fn(r.id,CollectionPage(offset=30),db);assert beyond['items']==[] and beyond['total']==3 and beyond['next_offset'] is None


def test_same_version_sibling_and_unlinked_releases_do_not_leak(standard):
    db,r=standard;sibling=Release(software_id=uuid.uuid4(),release_type='STANDARD',version=r.version)
    db.add_all([sibling,Release(software_id=r.software_id,release_type='APPLICATION',version='UNLINKED')]);db.flush();add_children(db,sibling,prefix='OTHER')
    summary=standard_summary(r.id,SummarySelection(),db);assert summary['component_count']==summary['application_count']==3
    left={i['id'] for i in standard_applications(r.id,CollectionPage(),db)['items']}
    right={i['id'] for i in standard_applications(sibling.id,CollectionPage(),db)['items']}
    assert len(right)==3 and not left&right


def test_missing_component_metadata_kept_missing_release_binding_excluded(standard):
    db,r=standard;missing=ReleaseComponent(release_id=r.id,component_definition_id=uuid.uuid4(),version='unknown-definition');db.add(missing)
    db.add(ApplicationReleaseDetail(release_id=uuid.uuid4(),customer_id=uuid.uuid4(),project_id=uuid.uuid4(),standard_base_release_id=r.id));db.commit()
    summary=standard_summary(r.id,SummarySelection(),db);assert summary['component_count']==4 and summary['application_count']==3
    row=next(i for i in standard_components(r.id,CollectionPage(),db)['items'] if i['id']==str(missing.id))
    assert row=={'id':str(missing.id),'code':None,'name':None,'version':'unknown-definition'}


@pytest.mark.parametrize('case',['missing','application'])
def test_exact_standard_parent_404(standard,case):
    db,r=standard;rid=uuid.uuid4()
    if case=='application':r.release_type='APPLICATION';db.commit();rid=r.id
    for fn,q in [(standard_summary,SummarySelection()),(standard_components,CollectionPage()),(standard_applications,CollectionPage())]:
        with pytest.raises(HTTPException) as error:fn(rid,q,db)
        assert error.value.status_code==404


def test_empty_optional_metadata_and_wrong_previous_type(context):
    db,_,r,*_=context;other=Release(software_id=r.software_id,release_type='APPLICATION',version='previous');db.add(other);db.flush()
    db.add(StandardReleaseDetail(release_id=r.id,previous_release_id=other.id));db.commit()
    result=standard_summary(r.id,SummarySelection(),db);assert result['previous_release'] is None and result['component_count']==result['application_count']==0
    for fn in [standard_components,standard_applications]:assert fn(r.id,CollectionPage(),db)['items']==[]
    db.delete(db.get(StandardReleaseDetail,r.id));db.commit();assert standard_summary(r.id,SummarySelection(),db)['source'] is None


@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'unknown':'value'}])
def test_strict_pagination_validation(kw):
    with pytest.raises(ValidationError):CollectionPage(**kw)


def test_growth_fixed_queries_no_child_orm_or_growing_ids(standard):
    db,r=standard;rid=r.id;calls=[]
    def capture(_conn,_cursor,statement,*_):calls.append(statement.lower())
    def read():
        db.expunge_all();calls.clear();summary=standard_summary(rid,SummarySelection(),db)
        components=standard_components(rid,CollectionPage(limit=2),db);applications=standard_applications(rid,CollectionPage(limit=2),db)
        assert not any(isinstance(row,(ReleaseComponent,ComponentDefinition,ApplicationReleaseDetail)) for row in db.identity_map.values())
        return summary,components,applications,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:small=read();add_children(db,db.get(Release,rid),count=120,prefix='GROW');grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['component_count']==grown[0]['application_count']==123 and len(grown[1]['items'])==len(grown[2]['items'])==2
    assert len(small[3])==len(grown[3]) and [len(s) for s in small[3]]==[len(s) for s in grown[3]] and 'limit' in grown[3][-1]


def test_http_strict_validation_readonly(standard,monkeypatch):
    from app import main
    db,r=standard;rid=r.id;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            base=f'/api/v1/releases/standard/id/{rid}';assert client.get(base+'/summary').json()['application_count']==3
            assert client.get(base+'/summary?unexpected=1').status_code==422
            for name in ['components','applications']:
                assert len(client.get(base+'/'+name+'?limit=1').json()['items'])==1
                for query in ['?limit=101','?offset=-1','?unknown=1']:assert client.get(base+'/'+name+query).status_code==422
            assert client.get('/api/v1/releases/standard/id/bad/summary').status_code==422
            response=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()


def test_real_migrated_postgresql_pages_no_audit_write(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);customer=db.scalar(select(Customer.id));project=db.scalar(select(Project.id))
        legacy=standard_release_profile(r.id,db)
        expected={'components':len(legacy['components'])+120,'applications':len(legacy['applications'])+120}
        add_children(db,r,count=120,customer_id=customer,project_id=project,prefix='PG');before=db.scalar(select(func.count()).select_from(AuditEvent))
        summary=standard_summary(r.id,SummarySelection(),db)
        assert summary['component_count']==expected['components'] and summary['application_count']==expected['applications']
        for fn,key in [(standard_components,'components'),(standard_applications,'applications')]:
            first=fn(r.id,CollectionPage(limit=1),db);second=fn(r.id,CollectionPage(limit=1,offset=1),db)
            assert first['total']==second['total']==expected[key] and first['next_offset']==1 and first['items'][0]['id']!=second['items'][0]['id']
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
