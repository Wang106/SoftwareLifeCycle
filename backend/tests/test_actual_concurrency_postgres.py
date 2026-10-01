"""Migrated PostgreSQL proves actual retry/optimistic locking and global key races."""
import uuid
from datetime import datetime, timezone
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg, count, overlapping_commands
from app.models.audit import AuditEvent
from app.models.production import Deployment, ProductionBatch
from app.services.production import ProductionService, ProductionError
from app.services.audit import AuditEventService

@pytest.fixture
def actual(pg):
    engine, ids = pg
    with Session(engine) as db:
        dep = db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'))
        ids = {**ids,'snapshot':dep.expected_snapshot_id}
        for dep in db.scalars(select(Deployment)):
            dep.actual_release_id=dep.actual_snapshot_id=dep.deployed_at=None;dep.status='PENDING'
        db.commit()
    return engine, ids

def report(db,ids,key,**changes):
    return ProductionService(db).report_actual(**{**dict(deployment_no='DEP-1',actual_release_id=ids['release'],actual_snapshot_id=ids['snapshot'],request_id=key,expected_version=0),**changes})

@pytest.mark.parametrize('case',['replay','changed','different_key'])
def test_concurrent_reports_serialize_and_detect_stale_versions(actual,monkeypatch,case):
    engine,ids=actual;key=uuid.uuid4()
    with Session(engine) as db:before=count(db,AuditEvent)
    changes={'deployed_at':datetime(2026,1,1)} if case=='changed' else {}
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:report(db,ids,key),
        lambda db:report(db,ids,uuid.uuid4() if case=='different_key' else key,**changes))
    assert first[0]=='ok' and second[0]==('ok' if case=='replay' else 'conflict')
    with Session(engine) as db:
        dep=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'))
        assert dep.actual_version==1 and count(db,AuditEvent)==before+1
        assert count(db,Deployment)==2


def test_global_same_key_on_different_deployments_rolls_back_loser(actual,monkeypatch):
    engine,ids=actual;key=uuid.uuid4()
    with Session(engine) as db:before=count(db,AuditEvent)
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:report(db,ids,key),lambda db:report(db,ids,key,deployment_no='DEP-2'),hold_after_audit=True)
    assert first[0]=='ok' and second[0]=='conflict'
    with Session(engine) as db:
        loser=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-2'))
        assert loser.actual_version==0 and loser.actual_release_id is None and loser.status=='PENDING'
        assert count(db,AuditEvent)==before+1
        assert report(db,ids,uuid.uuid4(),deployment_no='DEP-2').actual_version==1


def test_cached_deployment_version_is_refreshed_before_conflict(actual):
    engine,ids=actual
    with Session(engine,expire_on_commit=False) as stale:
        dep=stale.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'));stale.commit()
        with Session(engine) as writer:report(writer,ids,uuid.uuid4())
        assert dep.actual_version==0
        with pytest.raises(ProductionError,match='actual_version'):report(stale,ids,uuid.uuid4())
        assert not stale.in_transaction()
        with Session(engine) as db:assert db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1')).actual_version==1


def test_replay_original_result_after_correction_and_legacy_write(actual):
    engine,ids=actual;key=uuid.uuid4()
    with Session(engine) as db:first=report(db,ids,key,deployed_at=datetime(2026,1,1))
    assert first.deployed_at==datetime(2026,1,1,tzinfo=timezone.utc)
    with Session(engine) as db:report(db,ids,uuid.uuid4(),expected_version=1,correction_reason='Correct timestamp',deployed_at=datetime(2026,1,2))
    with Session(engine) as db:report(db,ids,None,expected_version=None)
    with Session(engine) as db:
        before=count(db,AuditEvent)
        assert report(db,ids,key,deployed_at=datetime(2026,1,1))==first
        assert count(db,AuditEvent)==before
        assert db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1')).actual_version==3


@pytest.mark.parametrize('failure',['audit_after_flush','commit'])
@pytest.mark.parametrize('correction',[False,True])
def test_failed_transaction_releases_lock_rolls_back_version_and_key(actual,monkeypatch,failure,correction):
    engine,ids=actual;key=uuid.uuid4();changes={}
    if correction:
        with Session(engine) as db:report(db,ids,uuid.uuid4())
        changes=dict(expected_version=1,correction_reason='Correction')
    with Session(engine) as db:
        before=count(db,AuditEvent)
        dep=db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1'))
        old=(dep.actual_version,dep.actual_release_id,dep.actual_snapshot_id,dep.status,dep.deployed_at)
        with monkeypatch.context() as patch:
            if failure=='audit_after_flush':
                original=AuditEventService.record
                def fail(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('audit failure')
                patch.setattr(AuditEventService,'record',fail)
            else:
                def fail(*args,**kwargs):raise RuntimeError('commit failure')
                patch.setattr(db,'commit',fail)
            with pytest.raises(RuntimeError):report(db,ids,key,**changes)
        assert not db.in_transaction()
        assert count(db,AuditEvent)==before
        assert (dep.actual_version,dep.actual_release_id,dep.actual_snapshot_id,dep.status,dep.deployed_at)==old
    # Independent session succeeds only if the previous transaction released its lock.
    with Session(engine) as db:
        db.execute(text("SET LOCAL lock_timeout='1s'"))
        assert report(db,ids,key,**changes).actual_version==(2 if correction else 1)


def test_correction_competition_same_expected_version(actual,monkeypatch):
    engine,ids=actual
    with Session(engine) as db:report(db,ids,uuid.uuid4())
    first,second=overlapping_commands(engine,monkeypatch,
        lambda db:report(db,ids,uuid.uuid4(),expected_version=1,correction_reason='First correction'),
        lambda db:report(db,ids,uuid.uuid4(),expected_version=1,correction_reason='Second correction'))
    assert first[0]=='ok' and second[0]=='conflict'
    with Session(engine) as db:
        events=db.scalars(select(AuditEvent).where(AuditEvent.entity_ref=='DEP-1').order_by(AuditEvent.created_at)).all()
        assert len(events)==2 and events[1].action=='ACTUAL_CORRECTED'
        assert events[1].payload_json['before']==events[0].payload_json['after']
        assert db.scalar(select(Deployment).where(Deployment.deployment_no=='DEP-1')).actual_version==2


def test_actual_then_batch_observes_committed_match(actual,monkeypatch):
    engine,ids=actual
    results=overlapping_commands(engine,monkeypatch,lambda db:report(db,ids,uuid.uuid4()),
        lambda db:ProductionService(db).create_batch('DEP-1','B',request_id=uuid.uuid4()))
    assert all(r[0]=='ok' for r in results)
    with Session(engine) as db:assert count(db,ProductionBatch)==1


def test_migration_preserves_existing_actual_state_and_initializes_zero(pg):
    engine,_=pg
    with engine.connect() as connection:
        before=connection.execute(text('SELECT id,actual_release_id,actual_snapshot_id,status FROM deployments ORDER BY deployment_no')).all()
    config=Config('alembic.ini')
    command.downgrade(config,'0016_authenticated_audit_actors')
    command.upgrade(config,'head')
    with engine.connect() as connection:
        after=connection.execute(text('SELECT id,actual_release_id,actual_snapshot_id,status FROM deployments ORDER BY deployment_no')).all()
        assert before==after
        assert connection.execute(text('SELECT actual_version FROM deployments')).scalars().all()==[0,0]
    with Session(engine) as db:
        dep=db.scalar(select(Deployment));dep.actual_version=-1
        with pytest.raises(IntegrityError):db.commit()
        db.rollback();assert dep.actual_version==0
