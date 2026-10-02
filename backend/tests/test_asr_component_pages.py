"""Exact stored baseline links, anti-association scope and bounded ASR reads."""
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
from app.api.asr_components import ComponentPage, SummarySelection, component_summary, component_declarations, unlinked_base_components
from app.api.dashboard import application_release_components
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import ApplicationReleaseDetail, ComponentDefinition, Customer, Project, Release, ReleaseComponent, SoftwareProduct


def seed(db, base, customer=None, project=None):
    product=db.get(SoftwareProduct,base.software_id)
    other_product=SoftwareProduct(supplier_id=product.supplier_id,code='OTHER-'+uuid.uuid4().hex[:10],name='Other')
    db.add(other_product);db.flush()
    asr=Release(software_id=base.software_id,release_type='APPLICATION',version='same')
    sibling=Release(software_id=other_product.id,release_type='APPLICATION',version='same')
    foreign=Release(software_id=other_product.id,release_type='STANDARD',version=base.version)
    d=ComponentDefinition(code='D-'+uuid.uuid4().hex,name='Controller',is_active=False)
    other=ComponentDefinition(code='X-'+uuid.uuid4().hex,name='Other')
    db.add_all([asr,sibling,foreign,d,other]);db.flush()
    db.add(ApplicationReleaseDetail(release_id=asr.id,customer_id=customer or uuid.uuid4(),project_id=project or uuid.uuid4(),standard_base_release_id=base.id))
    bases=[ReleaseComponent(release_id=base.id,component_definition_id=d.id,version=None if n==0 else 'same') for n in range(4)]
    fb=ReleaseComponent(release_id=foreign.id,component_definition_id=d.id,version='foreign')
    db.add_all(bases+[fb]);db.flush()
    rows=[ReleaseComponent(id=uuid.UUID('a0000000-0000-4000-8000-'+f'{n+1:012x}'),release_id=asr.id,component_definition_id=definition,version='same',base_component_id=link,delta_type='UNCHANGED') for n,(definition,link) in enumerate([
        (d.id,None),(d.id,fb.id),(other.id,bases[1].id),(d.id,bases[0].id),(d.id,bases[0].id),(d.id,bases[2].id)])]
    db.add_all(rows+[ReleaseComponent(release_id=sibling.id,component_definition_id=d.id,base_component_id=bases[3].id)])
    db.commit();return asr,bases,rows


@pytest.fixture
def components(context):
    db,_,base,*_=context;asr,bases,rows=seed(db,base);return db,base,asr,bases,rows


def parity(db,asr):
    legacy=application_release_components(asr.id,db)
    summary=component_summary(asr.id,SummarySelection(),db)
    assert summary=={k:v for k,v in legacy.items() if k not in ['components','unlinked_base_components']}|{'component_count':len(legacy['components']),'unlinked_base_count':len(legacy['unlinked_base_components'])}
    for fn,key in [(component_declarations,'components'),(unlinked_base_components,'unlinked_base_components')]:
        assert fn(asr.id,ComponentPage(),db)['items']==legacy[key]
    return summary


def test_legacy_parity_exact_links_duplicate_valid_and_null_version(components):
    db,base,asr,bases,rows=components;summary=parity(db,asr)
    assert summary['component_count']==6 and summary['unlinked_base_count']==2
    result=component_declarations(asr.id,ComponentPage(),db)
    assert [r['base_link_status'] for r in result['items']]==['NOT_RECORDED','INVALID','INVALID','VALID','VALID','VALID']
    assert result['items'][3]['base_component_version'] is None and result['items'][3]['name']=='Controller'
    assert {r['id'] for r in unlinked_base_components(asr.id,ComponentPage(),db)['items']}=={str(bases[n].id) for n in [1,3]}


def test_antijoin_uses_declarations_beyond_page_and_ignores_other_asr(components):
    db,base,asr,bases,rows=components
    assert component_declarations(asr.id,ComponentPage(limit=1),db)['items'][0]['base_link_status']=='NOT_RECORDED'
    unlinked=unlinked_base_components(asr.id,ComponentPage(limit=100),db)
    assert unlinked['total']==2 and str(bases[2].id) not in {r['id'] for r in unlinked['items']}
    assert str(bases[3].id) in {r['id'] for r in unlinked['items']}


@pytest.mark.parametrize('fn',[component_declarations,unlinked_base_components])
def test_independent_stable_pages_and_beyond_end(components,fn):
    db,base,asr,*_=components;whole=fn(asr.id,ComponentPage(),db)
    ids=[]
    for n in range(whole['total']):
        p=fn(asr.id,ComponentPage(limit=1,offset=n),db)
        assert p['release_id']==str(asr.id) and p['base_release_id']==str(base.id) and p['total']==whole['total']
        assert p['next_offset']==(n+1 if n+1<whole['total'] else None)
        ids.append(p['items'][0]['id'])
    assert ids==[r['id'] for r in whole['items']] and len(set(ids))==len(ids)
    p=fn(asr.id,ComponentPage(offset=100),db);assert p['items']==[] and p['total']==whole['total'] and p['next_offset'] is None


@pytest.mark.parametrize('case',['missing_detail','missing_base','wrong_base_type'])
def test_recorded_baseline_legacy_semantics(components,case):
    db,base,asr,*_=components;detail=db.get(ApplicationReleaseDetail,asr.id)
    if case=='missing_detail':db.delete(detail)
    elif case=='missing_base':detail.standard_base_release_id=uuid.uuid4()
    else:base.release_type='APPLICATION'
    db.commit();s=parity(db,asr)
    if case!='wrong_base_type':assert s['base_release'] is None and s['unlinked_base_count']==0
    else:assert s['base_release']['id']==str(base.id)


def test_orphan_pointer_and_definition_kept_as_invalid_not_hidden(components):
    db,base,asr,*_=components
    row=ReleaseComponent(release_id=asr.id,component_definition_id=uuid.uuid4(),base_component_id=uuid.uuid4(),version='orphan')
    db.add(row);db.commit();parity(db,asr)
    r=next(r for r in component_declarations(asr.id,ComponentPage(),db)['items'] if r['id']==str(row.id))
    assert r['code'] is r['name'] is r['base_component_version'] is None and r['base_link_status']=='INVALID'


@pytest.mark.parametrize('case',['missing','standard'])
def test_exact_application_parent_404(components,case):
    db,base,asr,*_=components;rid=uuid.uuid4() if case=='missing' else base.id
    for fn,q in [(component_summary,SummarySelection()),(component_declarations,ComponentPage()),(unlinked_base_components,ComponentPage())]:
        with pytest.raises(HTTPException) as e:fn(rid,q,db)
        assert e.value.status_code==404


@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'unknown':1}])
def test_strict_page_parameters(kw):
    with pytest.raises(ValidationError):ComponentPage(**kw)


def test_empty_application(context):
    db,_,base,*_=context;asr=Release(software_id=base.software_id,release_type='APPLICATION',version='empty');db.add(asr);db.commit()
    s=parity(db,asr);assert s['component_count']==s['unlinked_base_count']==0


def test_growth_fixed_queries_no_component_orm_or_python_id_expansion(components):
    db,base,asr,bases,_=components;rid,bid,did=asr.id,base.id,bases[0].component_definition_id;calls=[]
    def capture(_conn,_cursor,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();calls.clear();s=component_summary(rid,SummarySelection(),db)
        pages=[fn(rid,ComponentPage(limit=2),db) for fn in [component_declarations,unlinked_base_components]]
        assert not any(isinstance(x,(ReleaseComponent,ComponentDefinition)) for x in db.identity_map.values())
        return s,pages,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        for _ in range(120):db.add_all([ReleaseComponent(release_id=rid,component_definition_id=did),ReleaseComponent(release_id=bid,component_definition_id=did)])
        db.commit();grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['component_count']==126 and grown[0]['unlinked_base_count']==122
    assert all(len(p['items'])==2 for p in grown[1])
    assert small[2]==grown[2] and any('exists' in q for q in grown[2]) and 'limit' in grown[2][-1]


def test_http_validation_and_readonly(components,monkeypatch):
    from app import main
    db,_,asr,*_=components;rid=asr.id;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root=f'/api/v1/releases/application/id/{rid}/components'
            assert client.get(root+'/summary').json()['component_count']==6
            assert client.get(root+'/summary?unknown=1').status_code==422
            for name in ['declarations','unlinked-base']:
                assert len(client.get(root+'/'+name+'?limit=1').json()['items'])==1
                for q in ['?limit=101','?offset=-1','?unknown=1','?limit=invalid']:assert client.get(root+'/'+name+q).status_code==422
            assert client.get('/api/v1/releases/application/id/bad/components/summary').status_code==422
            response=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()


def test_real_postgresql_antijoin_pages_and_no_audit_write(pg):
    engine,ids=pg
    with Session(engine) as db:
        base=db.get(Release,ids['release']);customer=db.scalar(select(Customer.id));project=db.scalar(select(Project.id))
        asr,bases,rows=seed(db,base,customer,project);before=db.scalar(select(func.count()).select_from(AuditEvent))
        s=parity(db,asr);assert s['component_count']==6 and s['unlinked_base_count']==3 # fixture also has one base component
        assert component_declarations(asr.id,ComponentPage(limit=1),db)['next_offset']==1
        ids_seen=[]
        for offset in range(3):ids_seen.extend(r['id'] for r in unlinked_base_components(asr.id,ComponentPage(limit=1,offset=offset),db)['items'])
        assert len(set(ids_seen))==3 and str(bases[2].id) not in ids_seen and str(bases[3].id) in ids_seen
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
