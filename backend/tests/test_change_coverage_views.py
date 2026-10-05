import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_impact_assessments import context
from test_change_coverage import coverage_context
from test_change_issue_catalog import http
from test_command_concurrency_postgres import pg
from app.api.change_coverage_views import Selection, PageFilters, summary, candidate_page, gaps_page, groups_page, items_page, group_items_page, group_summary, assignment_page
from app.services.change_coverage import report_coverage
from app.models.change import AcceptanceCriterion, ChangePoint, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.acceptance import AcceptanceDvpLink
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpPlan, DvpItem, DvpExecution, ChangePointDvpItem
from app.models.audit import AuditEvent


def filters(data,**kwargs):
    return PageFilters(**{k:data[k] for k in ['change_id','release_id','snapshot_id']},**kwargs)


def assign(db,criterion,item):
    db.add(AcceptanceDvpLink(id=uuid.uuid4(),criterion_id=criterion.id,dvp_item_id=item.id,actor_name='Declared reviewer',reason='Original reason'))
    db.commit()


def compare(db,scr,release_id=None,snapshot_no=None):
    new=summary(scr.request_no,Selection(release_id=release_id,snapshot_no=snapshot_no),db)
    old=report_coverage(db,scr.request_no,release_id,snapshot_no)
    assert new['summary']==old['summary'] and new['gap_count']==len(old['gaps'])
    page=gaps_page(scr.request_no,filters(new,limit=100),db)
    assert sorted((r['code'],r['ref'],r['message']) for r in page['items'])==sorted((r['code'],r['ref'],r['message']) for r in old['gaps'])
    for kind,key in [('acceptance','acceptance_criteria'),('points','change_points'),('issues','issues')]:
        rows=groups_page(scr.request_no,kind,filters(new,limit=100),db)['items']
        expected={r['id']:r for r in old[key]}
        assert {r['id'] for r in rows}==set(expected)
        for row in rows:
            ref=expected[row['id']]
            assert (row['ref'],row['description'],row['verification'],row['excluded_link_count'],row['item_count'])==(ref['ref'],ref['description'],ref['verification'],ref['excluded_link_count'],len(ref['dvp_items']))
    return new


@pytest.mark.parametrize('mode',['assignments','frozen','old','missing'])
def test_full_legacy_parity_and_latest_execution(coverage_context,mode):
    db,_,release,snapshot,scr,criterion,_,items=coverage_context
    assign(db,criterion,items[0]);assign(db,criterion,items[1])
    old=ReleaseSnapshot(release_id=release.id,snapshot_no='OLD-COV',snapshot_number=0,content_hash='b'*64,status='FROZEN')
    empty=Release(software_id=release.software_id,release_type='STANDARD',version='EMPTY');db.add_all([old,empty]);db.flush()
    for number,snap,result in [(1,snapshot,'PASS'),(2,snapshot,'FAIL'),(3,old,'PASS')]:
        db.add(DvpExecution(dvp_item_id=items[0].id,execution_no=number,release_id=release.id,snapshot_id=snap.id,result=result,actual_result='Original observation'))
    db.commit()
    identifier=None if mode=='assignments' else empty.id if mode=='missing' else release.id
    data=compare(db,scr,identifier,'OLD-COV' if mode=='old' else None)
    if mode=='frozen':
        row=group_summary(scr.request_no,'acceptance',criterion.id,filters(data),db)
        assert row['verification']=='FAILED' and row['assignment_count']==2
        page=group_items_page(scr.request_no,'acceptance',criterion.id,filters(data,limit=1),db)
        assert page['total']==2 and len(page['items'])==1 and page['items'][0]['result']=='FAIL'
        assert page['items'][0]['actual_result']=='Original observation'
        assignments=assignment_page(scr.request_no,criterion.id,filters(data,limit=1),db)
        assert assignments['total']==2 and assignments['items'][0]['reason']=='Original reason'


def test_duplicates_foreign_orphans_and_blank_text(coverage_context):
    db,issue,_,_,scr,criterion,points,items=coverage_context
    criterion.description=' \t\n\r\u2003\u00a0';db.add(IssueChangeRequestRelation(issue_id=issue.id,change_request_id=scr.id,relation_type='RELATED'))
    db.add_all([ChangePointDvpItem(change_point_id=points[0].id,dvp_item_id=uuid.uuid4()),AcceptanceDvpLink(id=uuid.uuid4(),criterion_id=criterion.id,dvp_item_id=uuid.uuid4(),actor_name='Reviewer',reason='Orphan')]);db.commit()
    data=compare(db,scr)
    assert data['summary']['issues']['total']==1
    row=group_summary(scr.request_no,'acceptance',criterion.id,filters(data),db)
    assert row['excluded_link_count']==1 and row['assignment_count']==1
    assert group_items_page(scr.request_no,'acceptance',criterion.id,filters(data),db)['total']==0
    assert assignment_page(scr.request_no,criterion.id,filters(data),db)['total']==1


def test_empty_report_and_null_percent(context):
    db,_,_,_,scr=context
    data=compare(db,scr)
    assert data['summary']['acceptance']['assignment_percent'] is None
    assert data['summary']['dvp']=={'total':0,'executed':None,'passed':None}


def test_full_candidate_count_and_direct_selection_beyond_100(coverage_context):
    db,_,release,_,scr,*_=coverage_context
    for n in range(120):db.add(Release(software_id=release.software_id,release_type='STANDARD',version=f'EXTRA-{n}'))
    db.commit();data=summary(scr.request_no,Selection(release_id=release.id),db)
    assert data['candidate_count']==121
    page=candidate_page(scr.request_no,filters(data,limit=1,offset=120),db)
    assert page['total']==121 and len(page['items'])==1
    empty=candidate_page(scr.request_no,filters(data,offset=999),db)
    assert empty['total']==121 and empty['items']==[]


def test_snapshot_pin_survives_new_freeze_and_missing_context_rejects_change(coverage_context):
    db,_,release,snapshot,scr,_,_,items=coverage_context
    first=summary(scr.request_no,Selection(release_id=release.id),db)
    empty=Release(software_id=release.software_id,release_type='STANDARD',version='NO-FREEZE');db.add(empty);db.commit()
    missing=summary(scr.request_no,Selection(release_id=empty.id),db)
    for rel,num,no in [(release,2,'NEW-COV'),(empty,1,'FIRST-COV')]:
        db.add(ReleaseSnapshot(release_id=rel.id,snapshot_number=num,snapshot_no=no,status='FROZEN',content_hash='e'*64))
    db.commit()
    assert items_page(scr.request_no,filters(first),db)['snapshot_id']==str(snapshot.id)
    assert summary(scr.request_no,Selection(release_id=release.id,snapshot_id=snapshot.id),db)['snapshot_id']==str(snapshot.id)
    with pytest.raises(HTTPException) as error:items_page(scr.request_no,filters(missing),db)
    assert error.value.status_code==409


@pytest.mark.parametrize('endpoint',['candidates','gaps','groups/acceptance','groups/points','groups/issues','items'])
def test_http_strict_pins_and_filters(http,context,endpoint):
    scr=context[-1];base='/api/v1/change-coverage-views/'+scr.request_no+'/'+endpoint
    pin='change_id='+str(scr.id)+'&release_id=none&snapshot_id=none'
    assert http.get(base+'?'+pin+'&limit=1').status_code==200
    for query in ['limit=101','limit=0','offset=-1','offset=100001','unknown=1','limit=bad']:
        assert http.get(base+'?'+pin+'&'+query).status_code==422
    assert http.get(base).status_code==422
    assert http.get(base+'?'+pin.replace(str(scr.id),str(uuid.uuid4()))).status_code==404


def test_http_invalid_summary_selection_and_read_only(http,context,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    base='/api/v1/change-coverage-views/'+context[-1].request_no
    for q in ['snapshot_no=X','release_id=bad','snapshot_id=none','unknown=1','release_id='+str(context[2].id)+'&snapshot_id=none&snapshot_no=X']:
        assert http.get(base+'/summary?'+q).status_code==422
    response=http.post('/api/v1/deployments',json={});assert response.status_code==403


def test_growth_scalar_shape_and_bounded_children(coverage_context):
    db,_,release,_,scr,criterion,points,items=coverage_context
    assign(db,criterion,items[0]);number=scr.request_no;identifier=scr.id;release_id=release.id;plan_id=items[0].plan_id;criterion_id=criterion.id
    statements=[]
    def capture(conn,cursor,statement,parameters,ctx,executemany):statements.append(statement)
    event.listen(db.bind,'before_cursor_execute',capture)
    def probe():
        db.expunge_all();statements.clear()
        data=summary(number,Selection(release_id=release_id),db);f=filters(data,limit=1)
        pages=[gaps_page(number,f,db),groups_page(number,'acceptance',f,db),items_page(number,f,db),group_items_page(number,'acceptance',criterion_id,f,db),assignment_page(number,criterion_id,f,db)]
        assert not db.identity_map and all(len(p['items'])<=1 for p in pages)
        return data,pages,list(statements)
    try:
        _,_,before=probe()
        for n in range(120):
            db.add_all([AcceptanceCriterion(change_request_id=identifier,criterion_no='same',description=' '),ChangePoint(change_request_id=identifier,change_no='same',title='Point')])
            item=DvpItem(plan_id=plan_id,item_no=f'GROW-{n}',title='Test',scope='SOFTWARE_TEST');db.add(item);db.flush()
            db.add(AcceptanceDvpLink(id=uuid.uuid4(),criterion_id=criterion_id,dvp_item_id=item.id,actor_name='Reviewer',reason='Reason'))
        db.commit();data,pages,after=probe()
        assert before==after and data['summary']['acceptance']['total']==121
        assert pages[3]['total']==pages[4]['total']==121
    finally:event.remove(db.bind,'before_cursor_execute',capture)


def test_real_postgres_projection_parity_and_no_writes(pg):
    engine,ids=pg
    with Session(engine) as db:
        release=db.get(Release,ids['release']);scr=SoftwareChangeRequest(request_no='PG-COV',title='PG',source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=release.software_id,requirement='Requirement')
        db.add(scr);db.flush();plan=DvpPlan(change_request_id=scr.id,plan_no='PG-COV-PLAN',title='Plan');db.add(plan);db.flush()
        for n in range(120):
            criterion=AcceptanceCriterion(change_request_id=scr.id,criterion_no='same',description=' \t\n\u2003\u00a0' if n==0 else 'Criterion')
            item=DvpItem(plan_id=plan.id,item_no=str(n),title='Test',scope='SOFTWARE_TEST');db.add_all([criterion,item]);db.flush()
            db.add(AcceptanceDvpLink(id=uuid.uuid4(),criterion_id=criterion.id,dvp_item_id=item.id,actor_name='Reviewer',reason='Reason'))
        db.commit();before=db.scalar(select(func.count()).select_from(AuditEvent))
        data=summary(scr.request_no,Selection(release_id=release.id),db)
        assert data['summary']==report_coverage(db,scr.request_no,release.id)['summary']
        assert groups_page(scr.request_no,'acceptance',filters(data,limit=1,offset=119),db)['total']==120
        assert gaps_page(scr.request_no,filters(data,limit=1),db)['total']==data['gap_count']
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before

@pytest.mark.parametrize('result,state',[('PASS','PASSED'),('FAIL','FAILED'),('ERROR','FAILED'),('CANCELLED','FAILED'),('SKIPPED','PENDING')])
def test_latest_result_states(coverage_context,result,state):
    db,_,release,snapshot,scr,criterion,_,items=coverage_context
    assign(db,criterion,items[0])
    for number,value in [(1,'PASS'),(2,result)]:db.add(DvpExecution(dvp_item_id=items[0].id,execution_no=number,release_id=release.id,snapshot_id=snapshot.id,result=value))
    db.commit();data=compare(db,scr,release.id)
    assert group_summary(scr.request_no,'acceptance',criterion.id,filters(data),db)['verification']==state


def test_foreign_group_and_wrong_snapshot_context(coverage_context):
    db,_,release,snapshot,scr,*_=coverage_context
    data=summary(scr.request_no,Selection(release_id=release.id),db)
    for kind in ['acceptance','points','issues']:
        with pytest.raises(HTTPException) as error:group_items_page(scr.request_no,kind,uuid.uuid4(),filters(data),db)
        assert error.value.status_code==404
    with pytest.raises(HTTPException) as error:summary(scr.request_no,Selection(release_id=release.id,snapshot_id=uuid.uuid4()),db)
    assert error.value.status_code==409


def test_exact_candidate_software_customer_project_scope(coverage_context):
    from app.models.core import Customer, Project, ApplicationReleaseDetail
    db,_,release,_,scr,*_=coverage_context
    customers=[Customer(code='A',name='Same name'),Customer(code='B',name='Same name')];db.add_all(customers);db.flush()
    projects=[Project(customer_id=c.id,project_code='SAME',name='Same name') for c in customers];db.add_all(projects);db.flush()
    apps=[Release(software_id=release.software_id,release_type='APPLICATION',version=str(n)) for n in range(3)];db.add_all(apps);db.flush()
    for app,customer,project in zip(apps,customers,projects):
        db.add(ApplicationReleaseDetail(release_id=app.id,customer_id=customer.id,project_id=project.id,standard_base_release_id=release.id))
    scr.customer_id=customers[0].id;scr.project_id=projects[0].id;db.commit()
    data=summary(scr.request_no,Selection(),db)
    assert data['candidate_count']==2
    assert {r['id'] for r in candidate_page(scr.request_no,filters(data),db)['items']}=={str(release.id),str(apps[0].id)}
    assert summary(scr.request_no,Selection(release_id=apps[0].id),db)['release_id']==str(apps[0].id)
    for app in apps[1:]:
        with pytest.raises(HTTPException) as error:summary(scr.request_no,Selection(release_id=app.id),db)
        assert error.value.status_code==409
