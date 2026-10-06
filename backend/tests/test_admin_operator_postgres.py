"""Actual migrated PostgreSQL operator/API/session transaction overlaps."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.browser_sessions import CreateSession, create_session
from app.api.global_roles import RegisterGlobalRole, register_global_role
from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, SecurityPrincipal
from app.services.admin_operator import BootstrapAdmin, RecoverAdmin, OperatorError, apply, database_context
from app.services.audit import AuditEventService
from test_command_concurrency_postgres import pg, overlapping_commands


def configure(monkeypatch):
    for name,value in {'admin_operator_enabled':True,'read_only_mode':False,'auth_mode':'oidc',
        'oidc_issuer_url':'https://operator-test.example.com','oidc_audience':'test-api',
        'oidc_jwks_url':'https://operator-test.example.com/keys'}.items():monkeypatch.setattr(settings,name,value)


def bootstrap_body(engine,event=None):
    with Session(engine) as db:
        return BootstrapAdmin(event_no=event or 'OP-'+uuid.uuid4().hex,reason='Approved test bootstrap review',
            approval_ref='TEST-APPROVAL-123',acknowledge_privileged_change=True,expected_effective_admin_count=0,
            target_fingerprint=database_context(db)[0],principal_id=uuid.uuid4(),grant_id=uuid.uuid4(),
            subject='test-person-'+uuid.uuid4().hex,display_name='Test person')


def dormant(engine,principal_status='ACTIVE'):
    created=bootstrap_body(engine)
    with Session(engine) as db:
        apply(db,created)
        principal=db.get(SecurityPrincipal,created.principal_id);principal.status=principal_status
        grant=db.get(GlobalRoleAssignment,created.grant_id);grant.status='SUSPENDED';db.commit()
        body=RecoverAdmin(event_no='REC-'+uuid.uuid4().hex,reason='Approved test recovery review',
            approval_ref='TEST-RECOVERY-123',acknowledge_privileged_change=True,expected_effective_admin_count=0,
            target_fingerprint=database_context(db)[0],principal_id=principal.id,grant_id=grant.id,
            expected_principal_status=principal_status,expected_grant_status='SUSPENDED')
        request=Request({'type':'http','headers':[(b'authorization',b'Bearer verified-test-token')]})
        request.state.principal=AuthenticatedPrincipal(principal.id,principal.issuer,principal.subject,
            principal.principal_type,principal.display_name,None)
        request.state.token_expires=int(datetime.now(timezone.utc).timestamp())+600
    return body,request


def command(fn):
    def execute(db):
        try:return SimpleNamespace(id=json.dumps(fn(db),default=str,sort_keys=True))
        except OperatorError as exc:
            assert not db.in_transaction()
            return SimpleNamespace(id='error:'+str(exc))
        except HTTPException as exc:
            db.rollback()
            return SimpleNamespace(id='error:'+exc.detail)
    return execute


def outcome(value):
    return value[1] if value[1].startswith('error:') else json.loads(value[1])


@pytest.mark.parametrize('mode',['exact_retry','another_bootstrap','same_key_changed'])
def test_two_bootstraps_wait_and_create_one_admin_or_exact_replay(pg,monkeypatch,mode):
    engine,_=pg;configure(monkeypatch);one=bootstrap_body(engine)
    two=one if mode=='exact_retry' else bootstrap_body(engine,one.event_no if mode=='same_key_changed' else None)
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:apply(db,one)),command(lambda db:apply(db,two)))
    assert outcome(first)['replayed'] is False
    if mode=='exact_retry':assert outcome(second)['replayed'] is True
    else:assert outcome(second)==('error:operator_replay_conflict' if mode=='same_key_changed' else 'error:effective_admin_exists')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(GlobalRoleAssignment).where(GlobalRoleAssignment.role=='PLATFORM_ADMIN'))==1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='ADMIN_OPERATOR_BOOTSTRAP'))==1


@pytest.mark.parametrize('mode',['exact_retry','another_event','another_target'])
def test_competing_recoveries_wait_and_recheck_zero_admin_precondition(pg,monkeypatch,mode):
    engine,_=pg;configure(monkeypatch);one,_=dormant(engine)
    if mode=='another_target':
        with Session(engine) as db:
            principal=SecurityPrincipal(issuer=settings.oidc_issuer_url,subject='another',principal_type='USER',display_name='Another')
            db.add(principal);db.flush();grant=GlobalRoleAssignment(principal_id=principal.id,role='PLATFORM_ADMIN',status='SUSPENDED')
            db.add(grant);db.commit()
            two=one.model_copy(update={'principal_id':principal.id,'grant_id':grant.id,'event_no':'REC-OTHER'})
    else:two=one if mode=='exact_retry' else one.model_copy(update={'event_no':'REC-OTHER'})
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:apply(db,one)),command(lambda db:apply(db,two)))
    assert outcome(first)['replayed'] is False
    if mode=='exact_retry':assert outcome(second)['replayed'] is True
    else:assert outcome(second)=='error:effective_admin_exists'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(GlobalRoleAssignment).where(GlobalRoleAssignment.status=='ACTIVE'))==1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='ADMIN_OPERATOR_RECOVER'))==1


def test_api_admin_writer_waits_on_same_gate_and_rechecks_restored_actor_grant(pg,monkeypatch):
    engine,_=pg;configure(monkeypatch);body,request=dormant(engine)
    register=RegisterGlobalRole(event_no='G-AFTER-RECOVERY',grant_id=uuid.uuid4(),principal_id=body.principal_id,
                               role='AUDITOR',reason='Approved access review')
    first,second=overlapping_commands(engine,monkeypatch,command(lambda db:apply(db,body)),
        command(lambda db:register_global_role(register,request,db)))
    assert outcome(first)['current_grant_status']=='ACTIVE'
    assert outcome(second)['current_status']=='SUSPENDED'


@pytest.mark.parametrize('session_first',[False,True])
def test_session_registration_shares_recipient_lock_and_recovery_revokes_committed_sessions(pg,monkeypatch,session_first):
    engine,_=pg;configure(monkeypatch);body,request=dormant(engine)
    cookie=CreateSession(id=uuid.uuid4(),expires_at=int(datetime.now(timezone.utc).timestamp())+300)
    recover=command(lambda db:apply(db,body));register=command(lambda db:create_session(cookie,request,db))
    one,two=overlapping_commands(engine,monkeypatch,register if session_first else recover,recover if session_first else register)
    result=outcome(two if session_first else one)
    assert result['revoked_browser_sessions']==(1 if session_first else 0)
    with Session(engine) as db:
        assert (db.get(BrowserSession,cookie.id).revoked_at is not None)==session_first


@pytest.mark.parametrize('operation',['bootstrap','recover'])
def test_unrelated_transaction_audit_key_collision_rolls_back_all_operator_state(pg,monkeypatch,operation):
    engine,_=pg;configure(monkeypatch)
    body=bootstrap_body(engine) if operation=='bootstrap' else dormant(engine,'DISABLED')[0]
    original=AuditEventService.record
    def collide(service,**kwargs):
        with Session(engine) as other:
            original(AuditEventService(other),event_no=kwargs['event_no'],event_type='UNRELATED',action='NOISE',
                entity_type='NOISE',entity_ref='different',actor_name='Test',summary='Committed competing key')
            other.commit()
        return original(service,**kwargs)
    monkeypatch.setattr(AuditEventService,'record',collide)
    with Session(engine) as db:
        result=command(lambda db:apply(db,body))(db)
        assert result.id=='error:operator_write_conflict'
    with Session(engine) as db:
        if operation=='bootstrap':assert db.get(SecurityPrincipal,body.principal_id) is None
        else:assert db.get(SecurityPrincipal,body.principal_id).status=='DISABLED' and db.get(GlobalRoleAssignment,body.grant_id).status=='SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_no==body.event_no))==1


def test_executable_cli_plan_bootstrap_recovery_and_retry_are_real_postgres_only(pg,monkeypatch,tmp_path,capsys):
    from app import admin_operator as cli
    from sqlalchemy.orm import sessionmaker
    engine,_=pg;configure(monkeypatch)
    monkeypatch.setattr(cli,'SessionLocal',sessionmaker(bind=engine,expire_on_commit=False))
    assert cli.main(['plan'])==0
    view=json.loads(capsys.readouterr().out)
    assert view['bootstrap_available'] and view['effective_admin_count']==0
    first=bootstrap_body(engine)
    file=tmp_path/'reviewed.json';file.write_text(first.model_dump_json())
    assert cli.main(['bootstrap','--request',str(file)])==0
    response=json.loads(capsys.readouterr().out)
    assert response['principal_id']==str(first.principal_id) and response['replayed'] is False
    with Session(engine) as db:
        db.get(GlobalRoleAssignment,first.grant_id).status='SUSPENDED';db.commit()
        recovery=RecoverAdmin(event_no='CLI-RECOVERY',reason='Approved test recovery review',approval_ref='TEST-RECOVERY-123',
            acknowledge_privileged_change=True,expected_effective_admin_count=0,target_fingerprint=database_context(db)[0],
            principal_id=first.principal_id,grant_id=first.grant_id,expected_principal_status='ACTIVE',expected_grant_status='SUSPENDED')
    file.write_text(recovery.model_dump_json())
    for repeated in [False,True]:
        assert cli.main(['recover','--request',str(file)])==0
        response=json.loads(capsys.readouterr().out)
        assert response['replayed'] is repeated and response['current_grant_status']=='ACTIVE'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.in_(
            ['ADMIN_OPERATOR_BOOTSTRAP','ADMIN_OPERATOR_RECOVER'])))==2


def test_schema_plan_rejects_view_or_fallback_instead_of_coherent_migrated_tables(pg,monkeypatch):
    from sqlalchemy import text
    engine,_=pg;configure(monkeypatch);body=bootstrap_body(engine)
    with engine.begin() as db:
        db.execute(text('ALTER TABLE browser_sessions RENAME TO hidden_browser_sessions'))
        db.execute(text('CREATE VIEW browser_sessions AS SELECT * FROM hidden_browser_sessions'))
    with Session(engine) as db:
        with pytest.raises(OperatorError,match='operator_schema_not_ready'):apply(db,body)
        assert not db.in_transaction()
        assert db.scalar(select(func.count()).select_from(SecurityPrincipal))==0
