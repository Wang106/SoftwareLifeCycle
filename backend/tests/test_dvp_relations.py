"""Full counts, bounded SQL, exact ownership and PostgreSQL parity."""
import uuid
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.api.dvp_catalog import dvp_profile, dvp_relations, RelationPage
from app.core.db import get_db
from app.main import app
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, SoftwareChangeRequest
from app.models.testing import DvpItem, DvpPlan, ChangePointDvpItem, IssueDvpItem
from app.models.acceptance import AcceptanceDvpLink
from app.models.core import Release
from app.models.audit import AuditEvent
from test_impact_assessments import context
from test_change_coverage import coverage_context
from test_dvp_catalog import executed
from test_command_concurrency_postgres import pg


def grow(db, scr, item, stop=105):
    for n in range(stop):
        c=AcceptanceCriterion(change_request_id=scr.id,criterion_no='TIE',description=f'Criterion {n}')
        p=ChangePoint(change_request_id=scr.id,change_no='TIE',title=f'Point {n}')
        i=Issue(issue_no=f'GROW-{n:04}',title=f'Issue {n}',scope='STANDARD',severity='LOW')
        db.add_all([c,p,i]);db.flush()
        db.add_all([AcceptanceDvpLink(id=uuid.uuid4(),criterion_id=c.id,dvp_item_id=item.id,actor_name='Engineer',reason='Assignment'),ChangePointDvpItem(change_point_id=p.id,dvp_item_id=item.id),IssueDvpItem(issue_id=i.id,dvp_item_id=item.id)])
    db.commit()


def bounded(db,item,kind,**kw):return dvp_relations(item.id,kind,RelationPage(dvp_item_id=item.id,**kw),db)


def verify_pages(db,item):
    profile=dvp_profile(item.id,db);assert not any(k.startswith('linked_') for k in profile)
    for kind in ('criteria','points','issues'):
        seen=[];offset=0
        while True:
            page=bounded(db,item,kind,limit=7,offset=offset)
            assert page['total']==profile['relation_counts'][kind] and len(page['items'])<=7
            seen.extend(row['id'] for row in page['items'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        assert len(seen)==len(set(seen))==profile['relation_counts'][kind]
        assert seen[:100]==[row['id'] for row in bounded(db,item,kind,limit=100)['items']]
        assert bounded(db,item,kind,offset=100000)['items']==[]


def test_growth_keeps_profile_and_relation_selects_bounded(executed):
    db,_,_,_,scr,_,_,items=executed;engine=db.get_bind();queries=[]
    def record(conn,cursor,statement,parameters,context,many):queries.append(statement.lower())
    def read():
        db.expire_all();queries.clear()
        profile=dvp_profile(items[0].id,db);pages=[bounded(db,items[0],k,limit=2) for k in ('criteria','points','issues')]
        return profile,pages,list(queries)
    event.listen(engine,'before_cursor_execute',record)
    try:small=read();grow(db,scr,items[0]);large=read()
    finally:event.remove(engine,'before_cursor_execute',record)
    assert len(small[2])==len(large[2]) and all(len(p['items'])==2 for p in large[1])
    assert large[0]['relation_counts']==dict(criteria=105,points=106,issues=106)
    for statement in large[2]:
        if any(t in statement for t in ('acceptance_criteria','change_points','issues')) and 'count(' not in statement:assert 'limit' in statement
    verify_pages(db,items[0])
    assert dvp_profile(items[1].id,db)['relation_counts']==dict(criteria=0,points=0,issues=0)


@pytest.mark.parametrize('kind',['criteria','points','issues'])
def test_http_strict_bounds_owned_pin_and_no_write(executed,kind):
    db,*_,items=executed;ids=[str(i.id) for i in items]
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    def sessions():
        with Session(engine) as s:yield s
    old=dict(app.dependency_overrides);app.dependency_overrides[get_db]=sessions
    try:
        client=TestClient(app);root=f'/api/v1/testing/dvp/id/{ids[0]}/relations/{kind}'
        for suffix in ['', '?dvp_item_id=bad',*[f'?dvp_item_id={ids[0]}&{q}' for q in ('limit=0','limit=101','offset=-1','offset=100001','unknown=1')]]:assert client.get(root+suffix).status_code==422
        assert client.get(root+'?dvp_item_id='+ids[1]).status_code==404
        response=client.get(root+'?dvp_item_id='+ids[0]+'&limit=1');assert response.status_code==200 and response.json()['item_id']==ids[0]
        assert client.get(f'/api/v1/testing/dvp/id/{uuid.uuid4()}/relations/{kind}?dvp_item_id={uuid.uuid4()}').status_code==404
        with Session(engine) as s:assert s.scalar(select(func.count()).select_from(AuditEvent))==0
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(old);engine.dispose()


def test_real_postgresql_relation_growth_and_sibling_isolation(pg):
    engine,ids=pg
    with Session(engine) as db:
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        release=db.get(Release,ids['release']);scr=SoftwareChangeRequest(request_no='DVP-GROW',title='Growth',source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=release.software_id)
        db.add(scr);db.flush();plan=DvpPlan(change_request_id=scr.id,plan_no='DVP-GROW',title='Growth');db.add(plan);db.flush()
        item=DvpItem(plan_id=plan.id,item_no='SAME',title='Growth',scope='SOFTWARE_TEST');db.add(item);db.flush()
        sibling=DvpItem(plan_id=plan.id,item_no='OTHER',title='Sibling',scope='SOFTWARE_TEST');db.add(sibling);db.flush()
        grow(db,scr,item);verify_pages(db,item)
        assert dvp_profile(sibling.id,db)['relation_counts']==dict(criteria=0,points=0,issues=0)
        assert dvp_profile(item.id,db)['relation_counts']==dict(criteria=105,points=105,issues=105)
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
