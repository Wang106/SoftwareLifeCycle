from datetime import datetime, timezone, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event
from test_impact_assessments import context
from app.main import app
from app.models.audit import AuditEvent
from app.api.activity import AuditFilters, audit_catalog, get_activity, list_activity

@pytest.fixture
def ledger(context):
    db, issue, *_ = context
    at = datetime(2026, 9, 29, tzinfo=timezone.utc)
    rows = [AuditEvent(event_no=f'EVT-{n}', event_type='ASSESS' if n < 2 else 'LINK',
        action='RECORD', entity_type='Issue', entity_id=issue.id if n < 2 else uuid.uuid4(),
        entity_ref=issue.issue_no, actor_name='Engineer' if n < 2 else 'Other',
        summary='Literal %_ marker' if n == 0 else 'Recorded history', detail='Long details',
        payload_json={'large': 'x'*10000}, occurred_at=at + timedelta(days=n // 2)) for n in range(3)]
    db.add_all(rows); db.commit()
    return db, issue, rows, at


def test_counts_order_and_summaries(ledger):
    db, _, rows, _ = ledger
    pages=[audit_catalog(AuditFilters(limit=1,offset=n),db) for n in range(3)]
    assert all(p['total']==3 and p['event_type_counts']=={'ASSESS':2,'LINK':1} for p in pages)
    assert [p['items'][0]['event_no'] for p in pages]==['EVT-2','EVT-1','EVT-0']
    assert pages[0]['next_offset']==1 and pages[-1]['next_offset'] is None
    assert 'payload' not in pages[0]['items'][0] and 'detail' not in pages[0]['items'][0]
    assert get_activity('EVT-0',db)['payload']==rows[0].payload_json
    assert isinstance(list_activity(limit=50,db=db),list)


def test_exact_filters(ledger):
    db, issue, *_=ledger
    assert audit_catalog(AuditFilters(entity_id=issue.id),db)['total']==2
    assert audit_catalog(AuditFilters(entity_type='Issue',entity_ref=issue.issue_no,actor_name='Engineer',action='RECORD'),db)['total']==2
    assert audit_catalog(AuditFilters(entity_type='ISSUE'),db)['total']==0
    assert audit_catalog(AuditFilters(event_type='LINK'),db)['event_type_counts']=={'LINK':1}
    assert audit_catalog(AuditFilters(entity_id=uuid.uuid4()),db)['items']==[]
    assert audit_catalog(AuditFilters(offset=100),db)['next_offset'] is None


def test_literal_search(ledger):
    db,*_=ledger
    assert audit_catalog(AuditFilters(q='%_'),db)['total']==1
    assert audit_catalog(AuditFilters(q='Engineer'),db)['total']==2
    assert audit_catalog(AuditFilters(q='large'),db)['total']==0
    assert audit_catalog(AuditFilters(q='  '),db)['total']==3


def test_time_range(ledger):
    db,_,_,at=ledger
    f=AuditFilters(occurred_from='2026-09-29T08:00:00+08:00',occurred_before='2026-09-30T08:00:00+08:00')
    assert f.occurred_from==at and audit_catalog(f,db)['total']==2
    assert audit_catalog(AuditFilters(occurred_from=at+timedelta(days=1)),db)['total']==1


@pytest.mark.parametrize('values',[dict(limit=0),dict(limit=201),dict(offset=-1),dict(offset=100001),dict(entity_id='bad'),dict(q='x'*201),dict(occurred_from='2026-09-29T00:00:00'),dict(occurred_from='2026-09-30T00:00:00Z',occurred_before='2026-09-29T00:00:00Z'),dict(occurred_from='2026-09-29T00:00:00Z',occurred_before='2026-09-29T00:00:00Z'),dict(unknown='x')])
def test_validation(values):
    with pytest.raises(ValidationError):AuditFilters(**values)


def test_constant_query_budget_without_payload(ledger):
    db,*_=ledger;statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:audit_catalog(AuditFilters(limit=200),db)
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert len(statements)==3
    assert all('payload_json' not in s and 'audit_events.detail' not in s for s in statements)


@pytest.mark.parametrize('query',['limit=201','offset=-1','entity_id=bad','unknown=1','occurred_before=not-a-date','occurred_from=2026-09-29T00:00:00'])
def test_http_validation(query):
    with TestClient(app) as client:assert client.get('/api/v1/audit/events?'+query).status_code==422
