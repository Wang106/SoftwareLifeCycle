"""Complete owned step navigation and scalar summaries, including PostgreSQL."""
import uuid
import pytest
from sqlalchemy import create_engine,event,func,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import get_db
from app.api.governance_catalog import approval_summary,step_history,StepFilters
from app.models.approval import ApprovalRequest,ApprovalStep
from app.models.audit import AuditEvent
from test_impact_assessments import context
from test_governance_catalog import governance
from test_command_concurrency_postgres import pg


def page(db,a,**kw):return step_history(a.approval_no,StepFilters(approval_id=a.id,**kw),db)

def complete(db,a):
    summary=approval_summary(a.approval_no,db)
    assert 'steps' not in summary and 'steps_truncated' not in summary
    seen=[];offset=0
    while True:
        p=page(db,a,limit=17,offset=offset)
        assert p['total']==summary['step_total'] and len(p['items'])<=17
        seen.extend(row['id'] for row in p['items'])
        if p['next_offset'] is None:break
        offset=p['next_offset']
    assert len(seen)==len(set(seen))==summary['step_total']
    assert page(db,a,offset=100000)['items']==[]
    assert [r['step_order'] for r in page(db,a,limit=100)['items']]==list(range(100))


def test_summary_and_pages_stay_bounded_beyond_200_steps(governance):
    db,_,_,_,approvals,*_=governance;a=approvals[2];queries=[]
    def record(conn,cursor,statement,parameters,context,many):queries.append(statement.lower())
    event.listen(db.bind,'before_cursor_execute',record)
    try:
        approval_summary(a.approval_no,db);page(db,a,limit=1);small=len(queries)
        db.add_all([ApprovalStep(approval_request_id=a.id,step_order=n,role_name='Role') for n in range(205)]);db.commit();queries.clear()
        approval_summary(a.approval_no,db);p=page(db,a,limit=1);large=list(queries)
    finally:event.remove(db.bind,'before_cursor_execute',record)
    assert len(large)==small and p['total']==205 and len(p['items'])==1
    assert all('limit' in q for q in large if 'approval_steps' in q and 'count(' not in q)
    complete(db,a)
    assert approval_summary(approvals[0].approval_no,db)['step_total']==1


def test_http_pin_validation_and_no_audit_write(governance):
    db,_,_,_,approvals,*_=governance;a,b=approvals[:2];aid,bid=str(a.id),str(b.id)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    def sessions():
        with Session(engine) as session:yield session
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=sessions
    try:
        client=TestClient(app);root='/api/v1/governance/approvals/'+a.approval_no
        for query in ['', '?approval_id=bad',*[f'?approval_id={aid}&{q}' for q in ('limit=0','limit=101','offset=-1','offset=100001','unknown=1')]]:assert client.get(root+'/steps'+query).status_code==422
        assert client.get(root+'/steps?approval_id='+bid).status_code==404
        assert client.get(root+'/actions?approval_id='+bid).status_code==404
        assert client.get(root+'/steps?approval_id='+aid+'&limit=1').json()['approval_id']==aid
        assert client.get(root+'/actions?approval_id='+aid).json()['approval_id']==aid
        assert client.get('/api/v1/governance/approvals/MISSING/steps?approval_id='+aid).status_code==404
        with Session(engine) as s:assert s.scalar(select(func.count()).select_from(AuditEvent))==0
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(previous);engine.dispose()


def test_real_postgresql_complete_steps_and_unchanged_audit(pg):
    engine,ids=pg
    with Session(engine) as db:
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        a=ApprovalRequest(approval_no='GROW',target_type='RELEASE',target_id=ids['release']);db.add(a);db.flush()
        db.add_all([ApprovalStep(approval_request_id=a.id,step_order=n,role_name='Role') for n in range(205)]);db.commit()
        complete(db,a)
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
