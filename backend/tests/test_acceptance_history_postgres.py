"""Migrated PostgreSQL: correction locks, immutable history and downgrade safety."""
import uuid
from types import SimpleNamespace
import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg, overlapping_commands
from test_evidence_audit_postgres import evidence_context, command_input
from app.core.config import settings
from app.models.acceptance import AcceptanceDvpLink
from app.models.audit import AuditEvent
from app.models.change import AcceptanceCriterion
from app.models.testing import DvpItem
from app.services.change_coverage import CoverageError, record_assignment
from app.services.acceptance_history import effective
from app.services.audit import AuditEventService


def setup(engine, ids):
    original = command_input('acceptance',ids)
    with Session(engine) as db:
        record_assignment(db,'SCR-ORIGINAL',original); db.commit()
        old = db.get(DvpItem,ids['dvp'])
        item = DvpItem(plan_id=old.plan_id,item_no='DVP-2',title='Replacement',scope='SOFTWARE_TEST')
        db.add(item); db.commit()
        return original,item.id


def corrected(original,item_id,**changes):
    return original.model_copy(update={'request_id':uuid.uuid4(),'dvp_item_id':item_id,
        'action':'SUPERSEDE','supersedes_id':original.request_id,'reason':'Correct test assignment',**changes})


def execute(body):
    def run(db):
        try:
            row,_ = record_assignment(db,'SCR-ORIGINAL',body); db.commit(); return row
        except CoverageError as exc:
            db.rollback(); return SimpleNamespace(id='conflict:'+str(exc))
    return run


@pytest.mark.parametrize('pattern',['same_request','competing','withdraw_vs_replace','assign_vs_replace','changed_reason'])
def test_relationship_commands_share_scr_lock(evidence_context,monkeypatch,pattern):
    engine,ids = evidence_context; original,item = setup(engine,ids)
    one = corrected(original,item)
    two = one if pattern=='same_request' else corrected(original,item)
    if pattern=='withdraw_vs_replace': two = corrected(original,ids['dvp'],action='WITHDRAW')
    if pattern=='assign_vs_replace': two = corrected(original,item,action='ASSIGN',supersedes_id=None)
    if pattern=='changed_reason': two = one.model_copy(update={'reason':'Different reason'})
    first,second = overlapping_commands(engine,monkeypatch,execute(one),execute(two))
    assert first[1] == one.request_id
    if pattern=='same_request': assert second[1] == one.request_id
    else: assert str(second[1]).startswith('conflict:')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AcceptanceDvpLink)) == 2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='ACCEPTANCE_DVP')) == 2
        assert db.scalars(select(AcceptanceDvpLink.id).where(effective())).all() == [one.request_id]


def test_atomic_audit_failure_preserves_predecessor_and_releases_lock(evidence_context,monkeypatch):
    engine,ids = evidence_context; original,item = setup(engine,ids); body = corrected(original,item)
    record = AuditEventService.record
    def interrupt(self,**kwargs): record(self,**kwargs); raise RuntimeError('after audit flush')
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            patch.setattr(AuditEventService,'record',interrupt)
            with pytest.raises(RuntimeError):
                try: record_assignment(db,'SCR-ORIGINAL',body); db.commit()
                except Exception: db.rollback(); raise
        assert db.get(AcceptanceDvpLink,body.request_id) is None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_no==f'EVT-AC-{body.request_id}')) is None
        assert db.scalars(select(AcceptanceDvpLink.id).where(effective())).all() == [original.request_id]
    with Session(engine) as db:
        record_assignment(db,'SCR-ORIGINAL',body); db.commit()


def test_migration_preserves_legacy_and_guards_history(evidence_context):
    engine,ids = evidence_context; original,item = setup(engine,ids); config = Config('alembic.ini')
    migration.downgrade(config,'0021_impact_supersession')
    with engine.connect() as db:
        assert db.scalar(text('SELECT reason FROM acceptance_dvp_links WHERE id=:id'),{'id':original.request_id}) == original.reason
    migration.upgrade(config,'head')
    with Session(engine) as db:
        legacy = db.get(AcceptanceDvpLink,original.request_id)
        assert legacy.action=='ASSIGN' and legacy.supersedes_id is None
        body = corrected(original,item); record_assignment(db,'SCR-ORIGINAL',body); db.commit()
        withdrawn = corrected(body,item,action='WITHDRAW'); record_assignment(db,'SCR-ORIGINAL',withdrawn); db.commit()
        reassign = original.model_copy(update={'request_id':uuid.uuid4()}); record_assignment(db,'SCR-ORIGINAL',reassign); db.commit()
        for row in (original,body,withdrawn,reassign):
            for verb in ('UPDATE acceptance_dvp_links SET reason=reason','DELETE FROM acceptance_dvp_links'):
                with pytest.raises(DBAPIError,match='append-only'):
                    db.execute(text(verb+' WHERE id=:id'),{'id':row.request_id})
                db.rollback()
    with pytest.raises(DBAPIError,match='Cannot downgrade while acceptance corrections exist'):
        migration.downgrade(config,'0021_impact_supersession')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == settings.required_db_revision
        assert db.scalar(text('SELECT count(*) FROM acceptance_dvp_links')) == 4


@pytest.mark.parametrize('case',['self','missing','foreign_criterion','duplicate_child','assign_with_predecessor','withdraw_without_predecessor'])
def test_schema_relationship_guards(evidence_context,case):
    engine,ids = evidence_context; original,item = setup(engine,ids)
    identifier = uuid.uuid4(); predecessor = original.request_id; criterion = ids['criterion']; action = 'SUPERSEDE'
    with Session(engine) as db:
        if case=='self': predecessor=identifier
        if case=='missing': predecessor=uuid.uuid4()
        if case=='foreign_criterion':
            row=AcceptanceCriterion(change_request_id=ids['scr'],criterion_no='OTHER',description='Other')
            db.add(row);db.commit();criterion=row.id
        if case=='duplicate_child': record_assignment(db,'SCR-ORIGINAL',corrected(original,item));db.commit()
        if case=='assign_with_predecessor': action='ASSIGN'
        if case=='withdraw_without_predecessor': action='WITHDRAW';predecessor=None
        db.add(AcceptanceDvpLink(id=identifier,criterion_id=criterion,dvp_item_id=item,
            actor_name='Engineer',reason='Correction',action=action,supersedes_id=predecessor))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
