"""Withdrawal acceptance on a migrated, disposable real PostgreSQL schema."""
import uuid
from dataclasses import replace
from types import SimpleNamespace
import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg, overlapping_commands
from test_evidence_audit_postgres import evidence_context, command_input
from test_impact_supersession_postgres import root, corrected, command
from test_command_audit import trusted_actor
from app.api.issue_views import Empty, Pages, SnapshotSelection, assessments_page, candidates_page, evidence_summary, summary
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.impact import IssueImpactAssessment
from app.services.audit import AuditEventService
from app.services.impact_assessment import AssessmentError, record_assessment
from app.services.impact_withdrawal import WithdrawalInput, record_withdrawal
from app.services.impact_history import terminal_id


def withdrawal(ids, predecessor, **changes):
    return WithdrawalInput(**(dict(request_id=uuid.uuid4(),release_id=ids['release'],snapshot_id=ids['snapshot'],
        supersedes_id=predecessor,actor_name='Declared engineer',reason='撤销原判断',correction_reason='Independent review') | changes))


def withdraw_command(body):
    def execute(db):
        try:
            row, _ = record_withdrawal(db, 'ISSUE-ORIGINAL', body); db.commit(); return row
        except AssessmentError as exc:
            db.rollback(); return SimpleNamespace(id='conflict:' + str(exc))
    return execute


@pytest.mark.parametrize('pattern', ['same_request','competing','changed_body','supersede','plain_assess'])
def test_issue_lock_serializes_withdrawal_with_every_writer(evidence_context, monkeypatch, pattern):
    engine, ids=evidence_context; original=root(engine,ids); body=withdrawal(ids,original.request_id)
    if pattern=='supersede': second=command(corrected(ids,original))
    elif pattern=='plain_assess': second=command(command_input('impact',ids))
    else:
        retry=body if pattern=='same_request' else body.model_copy(update={'reason':'Changed'}) if pattern=='changed_body' else withdrawal(ids,original.request_id)
        second=withdraw_command(retry)
    one,two=overlapping_commands(engine,monkeypatch,withdraw_command(body),second,hold_after_audit=True)
    assert one[1]==body.request_id
    assert two[1]==body.request_id if pattern=='same_request' else str(two[1]).startswith('conflict:')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(IssueImpactAssessment))==2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='ISSUE_IMPACT'))==2
        result=evidence_summary('ISSUE-ORIGINAL',ids['release'],SnapshotSelection(),db)
        assert result['assessment'] is None and result['terminal_event_id']==str(body.request_id)


def test_explicit_new_judgments_serialize_and_old_withdrawal_replay_keeps_new_terminal(evidence_context,monkeypatch):
    engine,ids=evidence_context;original=root(engine,ids);body=withdrawal(ids,original.request_id)
    with Session(engine) as db:
        record_withdrawal(db,'ISSUE-ORIGINAL',body);db.commit()
        original_audit=dict(db.scalar(select(AuditEvent).where(AuditEvent.event_no==f'EVT-IMPACT-{body.request_id}')).payload_json)
    first=command_input('impact',ids).model_copy(update={'after_withdrawal_id':body.request_id})
    second=command_input('impact',ids).model_copy(update={'after_withdrawal_id':body.request_id})
    one,two=overlapping_commands(engine,monkeypatch,command(first),command(second))
    assert one[1]==first.request_id and str(two[1]).startswith('conflict:')
    with Session(engine) as db:
        row,created=record_withdrawal(db,'ISSUE-ORIGINAL',body);db.commit()
        assert not created and row.id==body.request_id
        assert evidence_summary('ISSUE-ORIGINAL',ids['release'],SnapshotSelection(),db)['assessment']['id']==str(first.request_id)
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_no==f'EVT-IMPACT-{body.request_id}')).payload_json==original_audit
        assert db.scalar(select(func.count()).select_from(IssueImpactAssessment))==3


def test_withdrawal_original_actor_audit_and_atomic_interruption(evidence_context,monkeypatch):
    engine,ids=evidence_context;original=root(engine,ids);body=withdrawal(ids,original.request_id)
    record=AuditEventService.record
    def interrupt(service,**kwargs):
        record(service,**kwargs);raise RuntimeError('after original audit flush')
    with Session(engine) as db:
        actor=replace(trusted_actor(db,'withdraw-engineer','Authenticated engineer'),declared_name=body.actor_name)
        db.commit()
        with monkeypatch.context() as patch:
            patch.setattr(AuditEventService,'record',interrupt)
            with pytest.raises(RuntimeError):
                try:record_withdrawal(db,'ISSUE-ORIGINAL',body,actor);db.commit()
                except Exception:db.rollback();raise
        assert db.get(IssueImpactAssessment,body.request_id) is None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_no==f'EVT-IMPACT-{body.request_id}')) is None
        record_withdrawal(db,'ISSUE-ORIGINAL',body,actor);db.commit()
        receipt=db.scalar(select(AuditEvent).where(AuditEvent.event_no==f'EVT-IMPACT-{body.request_id}'))
        assert receipt.actor_principal_id==actor.principal_id and receipt.declared_actor_name==body.actor_name
        audit=dict(receipt.payload_json)
        record_withdrawal(db,'ISSUE-ORIGINAL',body,actor);db.commit()
        assert receipt.payload_json==audit
        with pytest.raises(AssessmentError):record_withdrawal(db,'ISSUE-ORIGINAL',body,replace(actor,name='Different actor'))
        db.rollback()
        for table in ['issue_impact_assessments','audit_events']:
            for verb in ['UPDATE '+table+' SET id=id WHERE id=:id','DELETE FROM '+table+' WHERE id=:id']:
                with pytest.raises(DBAPIError,match='append-only'):
                    db.execute(text(verb),{'id':body.request_id if table=='issue_impact_assessments' else receipt.id})
                db.rollback()


def insert_legacy(connection,ids,body):
    connection.execute(text('''INSERT INTO issue_impact_assessments
        (id,issue_id,release_id,snapshot_id,decision,reason,evidence_ref,actor_name,created_at)
        VALUES (:id,:issue,:release,:snapshot,:decision,:reason,:evidence,:actor,'2099-01-01')'''),
        dict(id=body.request_id,issue=ids['issue'],release=ids['release'],snapshot=ids['snapshot'],
            decision=body.decision,reason=body.reason,evidence=body.evidence_ref,actor=body.actor_name))


def test_old_schema_roundtrip_preserves_original_body_audit_and_refuses_new_history_loss(evidence_context):
    engine,ids=evidence_context;config=Config('alembic.ini');body=command_input('impact',ids)
    migration.downgrade(config,'0022_acceptance_history')
    with engine.begin() as db:insert_legacy(db,ids,body)
    with Session(engine) as db:
        AuditEventService(db).record(event_no=f'EVT-IMPACT-{body.request_id}',event_type='ISSUE_IMPACT',
            action='ASSESS',entity_type='Issue',entity_id=ids['issue'],entity_ref='ISSUE-ORIGINAL',
            actor_name=body.actor_name,summary='Legacy original',detail=body.reason,payload={'legacy':'original'})
        db.commit()
    with engine.connect() as db:
        before=dict(db.execute(text('SELECT id,decision,reason,evidence_ref,actor_name,created_at FROM issue_impact_assessments')).mappings().one())
        audit=dict(db.execute(text('SELECT * FROM audit_events WHERE event_no=:no'),{'no':f'EVT-IMPACT-{body.request_id}'}).mappings().one())
    for _ in range(2):
        migration.upgrade(config,'head')
        with engine.connect() as db:
            assert dict(db.execute(text('SELECT id,decision,reason,evidence_ref,actor_name,created_at FROM issue_impact_assessments')).mappings().one())==before
            assert dict(db.execute(text('SELECT * FROM audit_events WHERE event_no=:no'),{'no':f'EVT-IMPACT-{body.request_id}'}).mappings().one())==audit
            assert db.execute(text('SELECT action,context_seq,after_withdrawal_id FROM issue_impact_assessments')).one()==(None,None,None)
        migration.downgrade(config,'0022_acceptance_history')
    migration.upgrade(config,'head')
    with Session(engine) as db:
        record_withdrawal(db,'ISSUE-ORIGINAL',withdrawal(ids,body.request_id));db.commit()
    with pytest.raises(DBAPIError,match='lose terminal semantics'):migration.downgrade(config,'0022_acceptance_history')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))==settings.required_db_revision
        assert db.scalar(text('SELECT count(*) FROM issue_impact_assessments'))==2
        assert dict(db.execute(text('SELECT * FROM audit_events WHERE event_no=:no'),{'no':f'EVT-IMPACT-{body.request_id}'}).mappings().one())==audit


@pytest.mark.parametrize('invalid',['null_action','null_sequence','zero_sequence','duplicate_sequence','withdraw_decision','withdraw_evidence','foreign_predecessor','restore_self'])
def test_database_guards_new_history_shapes_and_context(evidence_context,invalid):
    engine,ids=evidence_context;original=root(engine,ids)
    values=dict(id=uuid.uuid4(),issue_id=ids['issue'],release_id=ids['release'],snapshot_id=ids['snapshot'],
        action='WITHDRAW',context_seq=2,decision=None,evidence_ref=None,reason='Withdraw',actor_name='Reviewer',
        supersedes_id=original.request_id,correction_reason='Review')
    if invalid=='null_action':values['action']=None
    if invalid=='null_sequence':values['context_seq']=None
    if invalid=='zero_sequence':values['context_seq']=0
    if invalid=='duplicate_sequence':values['context_seq']=1
    if invalid=='withdraw_decision':values['decision']='AFFECTED'
    if invalid=='withdraw_evidence':values['evidence_ref']='Not allowed'
    if invalid=='foreign_predecessor':values['supersedes_id']=uuid.uuid4()
    if invalid=='restore_self':values.update(action='ASSESS',decision='AFFECTED',supersedes_id=None,correction_reason=None,after_withdrawal_id=values['id'])
    with Session(engine) as db:
        db.add(IssueImpactAssessment(**values))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback();assert db.get(IssueImpactAssessment,values['id']) is None


def test_ten_thousand_legacy_roots_do_not_revive_and_reads_are_bounded(evidence_context):
    engine,ids=evidence_context;config=Config('alembic.ini')
    migration.downgrade(config,'0022_acceptance_history')
    rows=[dict(id=uuid.uuid4(),issue=ids['issue'],release=ids['release'],snapshot=ids['snapshot']) for _ in range(10000)]
    with engine.begin() as db:
        db.execute(text('''INSERT INTO issue_impact_assessments (id,issue_id,release_id,snapshot_id,decision,reason,actor_name,created_at)
            VALUES (:id,:issue,:release,:snapshot,'AFFECTED','Legacy','Reviewer','2099-01-01')'''),rows)
        chain=[uuid.uuid4() for _ in range(1024)]
        db.execute(text('''INSERT INTO issue_impact_assessments
            (id,issue_id,release_id,snapshot_id,decision,reason,actor_name,created_at,supersedes_id,correction_reason)
            VALUES (:id,:issue,:release,:snapshot,'AFFECTED','Legacy chain','Reviewer','2099-01-01',:previous,:correction)'''),
            [dict(id=identifier,issue=ids['issue'],release=ids['release'],snapshot=ids['snapshot'],
                previous=chain[i-1] if i else None,correction='Legacy correction' if i else None)
             for i,identifier in enumerate(chain)])
    migration.upgrade(config,'head')
    with Session(engine) as db:
        statement=select(terminal_id(ids['issue'],ids['release'],ids['snapshot']))
        compiled=str(statement.compile(engine,compile_kwargs={'literal_binds':True}))
        plan=db.scalar(text('EXPLAIN (ANALYZE, FORMAT JSON) '+compiled))
        assert plan[0]['Plan']['Actual Rows']==1
        indexes=db.scalars(text("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename='issue_impact_assessments'")).all()
        assert 'ix_impact_terminal' in indexes and 'uq_impact_supersedes' in indexes
        predecessor=evidence_summary('ISSUE-ORIGINAL',ids['release'],SnapshotSelection(),db)['assessment']['id']
        body=withdrawal(ids,uuid.UUID(predecessor));record_withdrawal(db,'ISSUE-ORIGINAL',body);db.commit()
        statements=[]
        def capture(_c,_u,statement,_p,_ctx,_many):statements.append(statement)
        event.listen(engine,'before_cursor_execute',capture)
        try:
            result=evidence_summary('ISSUE-ORIGINAL',ids['release'],SnapshotSelection(),db)
            assert result['assessment'] is None and result['terminal_event_id']==str(body.request_id)
            page=assessments_page('ISSUE-ORIGINAL',Pages(issue_id=ids['issue'],limit=2,offset=9999),db)
            assert len(page['items'])==2 and not any(x['is_context_terminal'] for x in page['items'])
            candidate=candidates_page('ISSUE-ORIGINAL',Pages(issue_id=ids['issue'],limit=1),db)['items'][0]
            assert candidate['decision'] is None and candidate['context_state']=='WITHDRAWN'
            counts=summary('ISSUE-ORIGINAL',Empty(),db)
            assert counts['history_count']==11025 and counts['assessment_count']==11024
        finally:event.remove(engine,'before_cursor_execute',capture)
        assert len(statements)<30
        history_queries=[s for s in statements if 'FROM issue_impact_assessments' in s and 'count(' not in s.lower()]
        assert history_queries and all('LIMIT' in s or ' IN (' in s for s in history_queries)
        new=command_input('impact',ids).model_copy(update={'after_withdrawal_id':body.request_id})
        record_assessment(db,'ISSUE-ORIGINAL',new);db.commit()
        assert evidence_summary('ISSUE-ORIGINAL',ids['release'],SnapshotSelection(),db)['assessment']['id']==str(new.request_id)
