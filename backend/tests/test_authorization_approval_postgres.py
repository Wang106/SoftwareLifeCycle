"""Real migrated PostgreSQL serialization, append-only evidence and revocation races."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.distribution import SoftwareAuthorization
from app.models.security import ProjectMembership,SecurityPrincipal
from app.services.admin_lock import admin_write_gate
from app.services.revocation import RevocationService
from test_authorization_approval import configure,seed_approval,actor_request,service,body,submit
from test_command_concurrency_postgres import pg,overlapping_commands,count  # noqa:F401


@pytest.fixture
def approval_pg(pg,monkeypatch):
    configure(monkeypatch);engine,_=pg
    with Session(engine,expire_on_commit=False) as db:ids=seed_approval(db)
    return engine,ids


def command(fn):
    def execute(db):
        try:result=fn(db);return SimpleNamespace(id=json.dumps(result,sort_keys=True) if isinstance(result,dict) else str(result.id))
        except HTTPException as exc:
            assert not db.in_transaction()
            return SimpleNamespace(id='denied:'+str(exc.status_code)+':'+str(exc.detail))
    return execute


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_approvals_have_one_atomic_event(approval_pg,monkeypatch,same_key):
    engine,ids=approval_pg
    with Session(engine) as db:values=body(db,ids)
    other={**values,'request_id':values['request_id'] if same_key else uuid.uuid4()}
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:submit(db,ids,values)),command(lambda db:submit(db,ids,other)))
    assert first[0]==second[0]=='ok'
    if same_key:assert first[1]==second[1]
    else:assert second[1].startswith('denied:409:')
    with Session(engine) as db:
        assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==1
        assert db.get(SoftwareAuthorization,ids['authorization']).status=='APPROVED'


def test_concurrent_same_key_different_body_is_conflict(approval_pg,monkeypatch):
    engine,ids=approval_pg
    with Session(engine) as db:values=body(db,ids)
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:submit(db,ids,values)),command(lambda db:submit(db,ids,{**values,'reason':'Changed reviewed reason'})))
    assert first[0]==second[0]=='ok' and second[1]=='denied:409:approval_request_conflict'
    with Session(engine) as db:assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==1


@pytest.mark.parametrize('revoke_first',[False,True])
def test_approval_and_revocation_serialize_without_resurrection(approval_pg,monkeypatch,revoke_first):
    engine,ids=approval_pg
    with Session(engine) as db:values=body(db,ids)
    approve=command(lambda db:submit(db,ids,values))
    revoke=lambda db:RevocationService(db).revoke('AUTHORIZATION',ids['authorization'],'Synthetic concurrent revocation',request_id=uuid.uuid4())
    first,second=overlapping_commands(engine,monkeypatch,revoke if revoke_first else approve,approve if revoke_first else revoke)
    assert first[0]=='ok'
    if revoke_first:assert second[0]=='conflict'
    else:assert second[0]=='ok'
    with Session(engine) as db:
        assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==(0 if revoke_first else 1)
        if not revoke_first:
            historical=submit(db,ids,values);assert historical['applied_status']=='APPROVED'
            assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==1


@pytest.mark.parametrize('revoked',['membership','principal'])
@pytest.mark.parametrize('administrative_gate',[True,False])
def test_current_security_revocation_blocks_waiter_before_replay(approval_pg,revoked,administrative_gate):
    engine,ids=approval_pg
    with Session(engine) as db:values=body(db,ids);submit(db,ids,values)
    ready,release=Event(),Event();pids={}
    def revoke():
        with Session(engine) as db:
            if administrative_gate:admin_write_gate(db)
            pids['holder']=db.scalar(text('SELECT pg_backend_pid()'))
            model,key=(ProjectMembership,ids['grants']['approver']) if revoked=='membership' else (SecurityPrincipal,ids['people']['approver'])
            row=db.scalar(select(model).where(model.id==key).with_for_update());row.status='SUSPENDED' if revoked=='membership' else 'DISABLED';db.flush();ready.set()
            assert release.wait(8);db.commit()
    def replay():
        with Session(engine) as db:
            pids['waiter']=db.scalar(text('SELECT pg_backend_pid()'))
            try:submit(db,ids,values)
            except HTTPException as exc:return exc.status_code
            return 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        holder=pool.submit(revoke)
        try:
            assert ready.wait(5);waiter=pool.submit(replay);deadline=time.monotonic()+5
            while True:
                with engine.connect() as db:
                    blockers=db.scalar(text('SELECT pg_blocking_pids(:pid)'),{'pid':pids.get('waiter',0)})
                if pids['holder'] in (blockers or []):break
                assert time.monotonic()<deadline,'approval replay did not block behind revocation';time.sleep(.01)
        finally:release.set()
        holder.result(timeout=10);assert waiter.result(timeout=10)==(403 if revoked=='membership' else 401)
    with Session(engine) as db:assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==1


def test_original_approval_audit_is_append_only(approval_pg):
    engine,ids=approval_pg
    with Session(engine) as db:
        receipt=submit(db,ids,body(db,ids));event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==receipt['audit_event_no']));event_id=event.id;db.rollback()
        for statement in ['UPDATE audit_events SET action=action WHERE id=:id','DELETE FROM audit_events WHERE id=:id']:
            with pytest.raises(DBAPIError):db.execute(text(statement),{'id':event_id});db.commit()
            db.rollback()


def test_same_request_key_across_targets_never_approves_second_target(approval_pg,monkeypatch):
    from app.actor import ActorContext
    from app.services.distribution import DistributionService
    engine,ids=approval_pg
    with Session(engine,expire_on_commit=False) as db:
        original=db.get(SoftwareAuthorization,ids['authorization']);creator=db.get(SecurityPrincipal,ids['people']['creator'])
        actor=ActorContext(creator.display_name,creator.id,creator.display_name,None,'AUTHENTICATED_PRINCIPAL')
        row=DistributionService(db).create_authorization(original.release_id,original.distribution_id,'PAA-OTHER-AUTH',original.customer_id,original.project_id,original.site_code,original.line_code,actor_context=actor,request_id=uuid.uuid4())
        otherids={**ids,'number':row.authorization_no,'authorization':row.id};values=body(db,ids);other={**body(db,otherids),'request_id':values['request_id']}
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:submit(db,ids,values)),command(lambda db:submit(db,otherids,other)))
    assert first[0]==second[0]=='ok' and second[1]=='denied:409:approval_request_conflict'
    with Session(engine) as db:
        assert count(db,AuditEvent,event_type='AUTHORIZATION_APPROVED')==1
        assert db.get(SoftwareAuthorization,otherids['authorization']).status=='DRAFT'
