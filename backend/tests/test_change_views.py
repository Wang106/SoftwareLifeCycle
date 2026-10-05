import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from app.api.change_views import Selection, PageFilters, change_summary, criteria_page, issues_page, points_page, plans_page, point_items_page, plan_items_page
from app.models.change import AcceptanceCriterion, ChangePoint, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import DvpPlan, DvpItem, ChangePointDvpItem
from app.models.audit import AuditEvent
from test_impact_assessments import context
from test_command_concurrency_postgres import pg


def children(db, scr, count=3):
    points, plans = [], []
    for n in range(count):
        criterion = AcceptanceCriterion(change_request_id=scr.id, criterion_no='same', description=f'Criterion {n}')
        point = ChangePoint(change_request_id=scr.id, change_no='same', title=f'Point {n}', description='Original notes')
        plan = DvpPlan(change_request_id=scr.id, plan_no=str(uuid.uuid4()), title='Plan')
        db.add_all([criterion, point, plan]); db.flush()
        item = DvpItem(plan_id=plan.id, item_no='same', title='Test', scope='SOFTWARE_TEST')
        db.add(item); db.flush()
        db.add(ChangePointDvpItem(change_point_id=point.id, dvp_item_id=item.id))
        points.append(point.id); plans.append(plan.id)
    db.commit()
    return points, plans


def read(db, scr, points, plans, limit=100, offset=0):
    filters = PageFilters(change_id=scr.id, limit=limit, offset=offset)
    return [criteria_page(scr.request_no, filters, db), issues_page(scr.request_no, filters, db),
            points_page(scr.request_no, filters, db), plans_page(scr.request_no, filters, db),
            point_items_page(scr.request_no, points[0], filters, db), plan_items_page(scr.request_no, plans[0], filters, db)]


def test_summary_and_independent_children(context):
    db, issue, _, _, scr = context
    points, plans = children(db, scr)
    db.add(IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type='RELATED')); db.commit()
    summary = change_summary(scr.request_no, Selection(), db)
    assert summary['id'] == str(scr.id) and summary['software'] == {'code':'B','name':'BMS'}
    assert [summary[k] for k in ['criterion_count','issue_count','point_count','plan_count','point_item_count','plan_item_count']] == [3,2,3,3,3,3]
    pages = read(db, scr, points, plans)
    assert [p['total'] for p in pages] == [3,2,3,3,1,1]
    assert sorted((r['criterion_no'],r['description']) for r in pages[0]['items']) == [('same',f'Criterion {n}') for n in range(3)]
    assert {r['relation_type'] for r in pages[1]['items']} == {'FIXES','RELATED'}
    assert all(r['item_count'] == 1 and 'dvp_items' not in r for r in pages[2]['items'])
    assert all(r['item_count'] == 1 and 'items' not in r for r in pages[3]['items'])
    assert pages[4]['items'][0]['id'] == pages[5]['items'][0]['id']


def test_cross_plan_binding_and_orphan_semantics(context):
    db, issue, _, _, scr = context
    points, plans = children(db, scr, 1)
    other = SoftwareChangeRequest(request_no='OTHER', title='Other', source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=scr.software_id)
    db.add(other); db.flush()
    _, other_plans = children(db, other, 1)
    item = db.scalar(select(DvpItem).where(DvpItem.plan_id == other_plans[0]))
    db.add_all([ChangePointDvpItem(change_point_id=points[0],dvp_item_id=item.id),
                ChangePointDvpItem(change_point_id=points[0],dvp_item_id=uuid.uuid4()),
                IssueChangeRequestRelation(issue_id=uuid.uuid4(),change_request_id=scr.id,relation_type='RELATED')]); db.commit()
    summary = change_summary(scr.request_no, Selection(), db)
    assert (summary['point_item_count'],summary['plan_item_count'],summary['issue_count']) == (2,1,1)
    result = point_items_page(scr.request_no,points[0],PageFilters(change_id=scr.id),db)
    assert str(item.plan_id) in {r['plan_id'] for r in result['items']}
    with pytest.raises(HTTPException) as error:
        plan_items_page(scr.request_no,other_plans[0],PageFilters(change_id=scr.id),db)
    assert error.value.status_code == 404


@pytest.mark.parametrize('index',range(6))
def test_beyond_end_and_wrong_parent_pin(context,index):
    db, _, _, _, scr = context
    points, plans = children(db,scr)
    result = read(db,scr,points,plans,1,100)[index]
    assert result['total'] > 0 and result['items'] == [] and result['next_offset'] is None
    funcs = [criteria_page,issues_page,points_page,plans_page,point_items_page,plan_items_page]
    args = [scr.request_no]
    if index >= 4: args.append(points[0] if index == 4 else plans[0])
    with pytest.raises(HTTPException) as error:
        funcs[index](*args,PageFilters(change_id=uuid.uuid4()),db)
    assert error.value.status_code == 404


def test_missing_metadata_and_owned_child(context):
    db, _, _, _, scr = context
    scr.software_id = uuid.uuid4(); scr.customer_id = uuid.uuid4(); scr.project_id = uuid.uuid4(); db.commit()
    summary = change_summary(scr.request_no,Selection(),db)
    assert summary['software'] is summary['customer'] is summary['project'] is None
    assert summary['criterion_count'] == summary['point_count'] == summary['plan_count'] == 0
    for func in [point_items_page,plan_items_page]:
        with pytest.raises(HTTPException) as error: func(scr.request_no,uuid.uuid4(),PageFilters(change_id=scr.id),db)
        assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error: change_summary('missing',Selection(),db)
    assert error.value.status_code == 404


def test_growth_has_fixed_scalar_sql_shape(context):
    db, _, _, _, scr = context
    points, plans = children(db,scr,1); number, identifier = scr.request_no, scr.id
    statements = []
    def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(db.bind,'before_cursor_execute',capture)
    def probe():
        db.expunge_all(); statements.clear()
        summary = change_summary(number,Selection(),db)
        # A detached scalar-only owner keeps the fixture from loading an ORM graph.
        owner = type('Owner',(),{'id':identifier,'request_no':number})()
        pages = read(db,owner,points,plans,1)
        assert not db.identity_map
        return summary, pages, list(statements)
    try:
        _, _, first = probe()
        owner = type('Owner',(),{'id':identifier,'request_no':number})()
        children(db,owner,120)
        for n in range(120):
            item = DvpItem(plan_id=plans[0],item_no=f'extra-{n}',title='Extra',scope='SOFTWARE_TEST')
            db.add(item); db.flush(); db.add(ChangePointDvpItem(change_point_id=points[0],dvp_item_id=item.id))
        db.commit()
        summary, pages, grown = probe()
        assert first == grown
        assert summary['point_count'] == 121 and summary['point_item_count'] == summary['plan_item_count'] == 241
        assert all(len(p['items']) <= 1 for p in pages)
        assert pages[4]['total'] == pages[5]['total'] == 121
    finally: event.remove(db.bind,'before_cursor_execute',capture)


def test_postgres_projection_and_no_audit_writes(pg):
    from sqlalchemy.orm import Session
    from app.models.core import Release
    engine, ids = pg
    db = Session(engine)
    release = db.get(Release, ids['release'])
    scr = SoftwareChangeRequest(request_no='PG-VIEW',title='PG',source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=release.software_id)
    db.add(scr); db.flush(); points, plans = children(db,scr,120)
    before = db.scalar(select(func.count(AuditEvent.id)))
    summary = change_summary(scr.request_no,Selection(),db)
    assert summary['point_count'] == summary['plan_count'] == summary['criterion_count'] == 120
    pages = read(db,scr,points,plans,1,119)
    assert len(pages[0]['items']) == len(pages[2]['items']) == len(pages[3]['items']) == 1
    assert pages[4]['total'] == pages[5]['total'] == 1
    assert db.scalar(select(func.count(AuditEvent.id))) == before
    db.close()

from test_change_issue_catalog import http

@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001','unknown=1','change_id=bad'])
def test_http_strict_filters(http,context,query):
    scr = context[-1]
    for endpoint in ['criteria','issues','points','plans']:
        pin = '' if query.startswith('change_id=') else 'change_id='+str(scr.id)+'&'
        assert http.get('/api/v1/change-views/'+scr.request_no+'/'+endpoint+'?'+pin+query).status_code == 422

def test_http_identity_and_read_only(http,context,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    scr = context[-1]; path='/api/v1/change-views/'+scr.request_no
    assert http.get(path+'/summary').status_code == 200
    assert http.get(path+'/summary?unknown=1').status_code == 422
    for endpoint in ['criteria','issues','points','plans']:
        assert http.get(path+'/'+endpoint).status_code == 422
        assert http.get(path+'/'+endpoint+'?change_id='+str(uuid.uuid4())).status_code == 404
        assert http.get(path+'/'+endpoint+'?change_id='+str(scr.id)).status_code == 200
    assert http.get(path+'/points/bad/items?change_id='+str(scr.id)).status_code == 422
    response=http.post('/api/v1/deployments',json={})
    assert response.status_code == 403 and response.json() == {'detail':'read_only_mode'}
