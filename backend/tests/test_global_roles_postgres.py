"""Real PostgreSQL serialization, privilege races and guarded schema rollback."""
import uuid

import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.global_roles import RegisterGlobalRole, GlobalRoleStatusChange, register_global_role, change_global_role_status
from app.api.principal_admin import PrincipalStatusChange, change_principal_status
from app.models.audit import AuditEvent
from app.services.audit import AuditEventService
from app.models.security import GlobalRoleAssignment, SecurityPrincipal
from app.core.config import settings
from test_command_concurrency_postgres import pg, overlapping_commands
from test_principal_admin_postgres import setup, command, outcome


def status(event='G-SUSPEND', after='SUSPENDED'):
    return GlobalRoleStatusChange(event_no=event, expected_status='ACTIVE' if after=='SUSPENDED' else 'SUSPENDED',
        status=after, reason='Approved access review')


def grant(engine, identifier):
    with Session(engine) as db:
        return db.scalar(select(GlobalRoleAssignment.id).where(GlobalRoleAssignment.principal_id==identifier,
                                                             GlobalRoleAssignment.role=='PLATFORM_ADMIN'))


@pytest.mark.parametrize('pattern',['self','cross','same_target'])
def test_competing_admin_suspensions_wait_and_preserve_one_effective_admin(pg,monkeypatch,pattern):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    grants=[grant(engine,i) for i in ids[:2]]
    first_target=grants[0] if pattern=='self' else grants[1]
    second_target=grants[0] if pattern=='cross' else grants[1]
    one,two=overlapping_commands(engine,monkeypatch,
        command(lambda db:change_global_role_status(first_target,status(),requests[0],db)),
        command(lambda db:change_global_role_status(second_target,status('G-SECOND'),requests[1],db)))
    assert outcome(one)['current_status']=='SUSPENDED'
    assert outcome(two)==('error:last_active_admin_protected' if pattern=='self' else 'error:platform_admin_required')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(GlobalRoleAssignment).where(
            GlobalRoleAssignment.role=='PLATFORM_ADMIN',GlobalRoleAssignment.status=='ACTIVE'))==1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='GLOBAL_ROLE_STATUS_CHANGED'))==1


@pytest.mark.parametrize('same_event',[False,True])
@pytest.mark.parametrize('same_actor',[False,True])
def test_competing_registration_has_one_grant_exact_owner_retry(pg,monkeypatch,same_event,same_actor):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    body=RegisterGlobalRole(event_no='G-REGISTER',grant_id=uuid.uuid4(),principal_id=ids[2],role='AUDITOR',reason='Approved access review')
    second=body if same_event else body.model_copy(update={'event_no':'G-OTHER'})
    one,two=overlapping_commands(engine,monkeypatch,
        command(lambda db:register_global_role(body,requests[0],db)),
        command(lambda db:register_global_role(second,requests[0 if same_actor else 1],db)))
    assert outcome(one)['replayed'] is False
    if same_actor and same_event:assert outcome(two)['replayed'] is True
    else:assert outcome(two)==('error:audit_event_conflict' if same_event else 'error:global_role_registration_conflict')
    with Session(engine) as db:
        assert db.get(GlobalRoleAssignment,body.grant_id).status=='SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==body.grant_id))==1


@pytest.mark.parametrize('same_event',[False,True])
@pytest.mark.parametrize('same_actor',[False,True])
def test_competing_status_rechecks_state_or_replays(pg,monkeypatch,same_event,same_actor):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    with Session(engine,expire_on_commit=False) as db:
        row=GlobalRoleAssignment(principal_id=ids[2],role='AUDITOR');db.add(row);db.commit();identifier=row.id
    body=status();second=body if same_event else status('G-OTHER')
    one,two=overlapping_commands(engine,monkeypatch,
        command(lambda db:change_global_role_status(identifier,body,requests[0],db)),
        command(lambda db:change_global_role_status(identifier,second,requests[0 if same_actor else 1],db)))
    assert outcome(one)['replayed'] is False
    if same_actor and same_event:assert outcome(two)['replayed'] is True
    else:assert outcome(two)==('error:audit_event_conflict' if same_event else 'error:global_role_status_conflict')


@pytest.mark.parametrize('disable_first',[False,True])
def test_principal_disable_and_global_registration_follow_same_transaction_gate(pg,monkeypatch,disable_first):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    body=RegisterGlobalRole(event_no='G-REGISTER',grant_id=uuid.uuid4(),principal_id=ids[2],role='AUDITOR',reason='Approved access review')
    disable=PrincipalStatusChange(event_no='P-DISABLE',expected_status='ACTIVE',status='DISABLED',reason='Approved access review')
    register=command(lambda db:register_global_role(body,requests[0],db))
    disable_cmd=command(lambda db:change_principal_status(ids[2],disable,requests[1],db))
    one,two=overlapping_commands(engine,monkeypatch,disable_cmd if disable_first else register,register if disable_first else disable_cmd)
    assert outcome(one)['replayed'] is False
    if disable_first:assert outcome(two)=='error:recipient_inactive'
    else:assert outcome(two)['current_status']=='DISABLED'
    with Session(engine) as db:
        assert db.get(SecurityPrincipal,ids[2]).status=='DISABLED'
        row=db.get(GlobalRoleAssignment,body.grant_id)
        assert row is None if disable_first else row.status=='SUSPENDED'


@pytest.mark.parametrize('resume_first',[False,True])
def test_admin_resume_and_disable_keep_admin_principal_protected(pg,monkeypatch,resume_first):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    with Session(engine,expire_on_commit=False) as db:
        row=GlobalRoleAssignment(principal_id=ids[2],role='PLATFORM_ADMIN',status='SUSPENDED');db.add(row);db.commit();identifier=row.id
    resume=command(lambda db:change_global_role_status(identifier,status('G-RESUME','ACTIVE'),requests[0],db))
    disable=PrincipalStatusChange(event_no='P-DISABLE',expected_status='ACTIVE',status='DISABLED',reason='Approved access review')
    # Protected disable rejects before audit. When it goes first there is no write
    # to hold, so verify rejection then overlap two resumes instead.
    if not resume_first:
        with Session(engine) as db:
            assert outcome(('ok',command(lambda db:change_principal_status(ids[2],disable,requests[1],db))(db).id))=='error:admin_principal_protected'
        one,two=overlapping_commands(engine,monkeypatch,resume,
            command(lambda db:change_global_role_status(identifier,status('G-SECOND','ACTIVE'),requests[1],db)))
        assert outcome(two)=='error:global_role_status_conflict'
    else:
        one,two=overlapping_commands(engine,monkeypatch,resume,
            command(lambda db:change_principal_status(ids[2],disable,requests[1],db)))
        assert outcome(two)=='error:admin_principal_protected'
    assert outcome(one)['current_status']=='ACTIVE'


def test_existing_grants_remain_active_and_downgrade_cannot_reactivate_suspended_grants(pg):
    engine,_=pg
    config=Config('alembic.ini')
    migration.downgrade(config,'0019_browser_sessions')
    identifier=uuid.uuid4();principal=uuid.uuid4()
    with engine.begin() as db:
        db.execute(text("INSERT INTO security_principals (id,issuer,subject,principal_type,display_name,status,created_at) VALUES (:id,'https://legacy.example.com','legacy','USER','Legacy','ACTIVE',now())"),{'id':principal})
        db.execute(text("INSERT INTO global_role_assignments (id,principal_id,role,created_at) VALUES (:id,:principal,'PLATFORM_ADMIN',now())"),{'id':identifier,'principal':principal})
    migration.upgrade(config,'head')
    with Session(engine) as db:
        assert db.get(GlobalRoleAssignment,identifier).status=='ACTIVE'
        db.get(GlobalRoleAssignment,identifier).status='SUSPENDED';db.commit()
    with pytest.raises(DBAPIError,match='Cannot downgrade while suspended global grants exist'):
        migration.downgrade(config,'0019_browser_sessions')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))==settings.required_db_revision
        assert db.scalar(text('SELECT status FROM global_role_assignments WHERE id=:id'),{'id':identifier})=='SUSPENDED'
    with Session(engine) as db:
        db.get(GlobalRoleAssignment,identifier).status='ACTIVE';db.commit()
    migration.downgrade(config,'0019_browser_sessions')
    migration.upgrade(config,'head')
    with Session(engine) as db:
        assert db.get(GlobalRoleAssignment,identifier).status=='ACTIVE'
        db.get(GlobalRoleAssignment,identifier).status='INVALID'
        with pytest.raises(IntegrityError):db.commit()


@pytest.mark.parametrize('operation',['register','status'])
def test_other_transaction_commits_audit_key_after_entry_check_and_state_rolls_back(pg,monkeypatch,operation):
    engine,_=pg;ids,requests=setup(engine,monkeypatch)
    identifier=uuid.uuid4()
    if operation=='status':
        with Session(engine) as db:
            db.add(GlobalRoleAssignment(id=identifier,principal_id=ids[2],role='AUDITOR',status='SUSPENDED'));db.commit()
    original=AuditEventService.record
    def collision(service,**kwargs):
        with Session(engine) as other:
            original(AuditEventService(other),event_no=kwargs['event_no'],event_type='UNRELATED',
                action='NOISE',entity_type='NOISE',entity_ref='different',actor_name='Test',summary='Competing audit')
            other.commit()
        return original(service,**kwargs)
    monkeypatch.setattr(AuditEventService,'record',collision)
    with Session(engine) as db:
        if operation=='register':
            body=RegisterGlobalRole(event_no='G-COLLISION',grant_id=identifier,principal_id=ids[2],role='AUDITOR',reason='Approved access review')
            result=command(lambda db:register_global_role(body,requests[0],db))(db)
        else:result=command(lambda db:change_global_role_status(identifier,status('G-COLLISION','ACTIVE'),requests[0],db))(db)
        assert result.id==('error:global_role_registration_conflict' if operation=='register' else 'error:audit_event_conflict')
    with Session(engine) as db:
        row=db.get(GlobalRoleAssignment,identifier)
        assert row is None if operation=='register' else row.status=='SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_no=='G-COLLISION'))==1
