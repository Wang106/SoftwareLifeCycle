"""Real locks: exact role uniqueness, global audit collisions and principal disable."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.api.membership_registration import RegisterMembership,register_membership
from app.api.principal_admin import PrincipalStatusChange,change_principal_status
from app.models.audit import AuditEvent
from app.models.core import Project,SoftwareProduct
from app.models.security import ProjectMembership,SecurityPrincipal,SoftwareMembership
from test_principal_admin_postgres import setup
from test_command_concurrency_postgres import pg,overlapping_commands


def body_for(engine,identifier,scope):
    with Session(engine) as db:target=db.scalar(select(Project.id if scope=='PROJECT' else SoftwareProduct.id))
    return RegisterMembership(event_no='ROLE-REGISTER',reason='Register approved exact role',membership_id=uuid.uuid4(),
        principal_id=identifier,scope_id=target,role='PROJECT_VIEWER' if scope=='PROJECT' else 'SOFTWARE_VIEWER')


def command(fn):
    def execute(db):
        try:
            result=fn(db)
            return SimpleNamespace(id='replay' if result['replayed'] else 'created')
        except HTTPException as error:
            assert not db.in_transaction()
            return SimpleNamespace(id='error:'+error.detail)
    return execute


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('same_admin',[False,True])
@pytest.mark.parametrize('same_event',[False,True])
def test_role_registration_serializes_on_recipient_and_replays_only_original_admin(pg,monkeypatch,scope,same_admin,same_event):
    engine,_=pg;ids,requests=setup(engine,monkeypatch);body=body_for(engine,ids[2],scope)
    second=body if same_event else body.model_copy(update={'event_no':'OTHER-EVENT','membership_id':uuid.uuid4()})
    one,two=overlapping_commands(engine,monkeypatch,
        command(lambda db:register_membership(scope,body,requests[0],db)),
        command(lambda db:register_membership(scope,second,requests[0 if same_admin else 1],db)))
    assert one[1]=='created'
    assert two[1]==('replay' if same_event and same_admin else 'error:'+('audit_event_conflict' if same_event else 'membership_registration_conflict'))
    model=ProjectMembership if scope=='PROJECT' else SoftwareMembership
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(model))==1
        assert db.get(model,body.membership_id).status=='SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='MEMBERSHIP_REGISTERED'))==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
@pytest.mark.parametrize('disable_first',[False,True])
def test_role_registration_and_principal_disable_share_recipient_lock(pg,monkeypatch,scope,disable_first):
    engine,_=pg;ids,requests=setup(engine,monkeypatch);body=body_for(engine,ids[2],scope)
    disabled=PrincipalStatusChange(event_no='DISABLE-RECIPIENT',expected_status='ACTIVE',status='DISABLED',reason='Disable pending review')
    create=command(lambda db:register_membership(scope,body,requests[0],db))
    disable=command(lambda db:change_principal_status(ids[2],disabled,requests[1],db))
    one,two=overlapping_commands(engine,monkeypatch,disable if disable_first else create,create if disable_first else disable)
    assert one[1]=='created'
    assert two[1]==('error:recipient_inactive' if disable_first else 'created')
    model=ProjectMembership if scope=='PROJECT' else SoftwareMembership
    with Session(engine) as db:
        assert db.get(SecurityPrincipal,ids[2]).status=='DISABLED'
        row=db.get(model,body.membership_id)
        assert row is None if disable_first else row.status=='SUSPENDED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='MEMBERSHIP_REGISTERED'))==(0 if disable_first else 1)
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='PRINCIPAL_STATUS_CHANGED'))==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_global_audit_key_collision_rolls_back_second_recipient_membership(pg,monkeypatch,scope):
    engine,_=pg;ids,requests=setup(engine,monkeypatch);body=body_for(engine,ids[2],scope)
    with Session(engine) as db:
        row=SecurityPrincipal(issuer='https://test.example.com',subject='second-recipient',principal_type='USER',display_name='Recipient')
        db.add(row);db.commit();identifier=row.id
    second=body.model_copy(update={'principal_id':identifier,'membership_id':uuid.uuid4()})
    one,two=overlapping_commands(engine,monkeypatch,
        command(lambda db:register_membership(scope,body,requests[0],db)),
        command(lambda db:register_membership(scope,second,requests[1],db)),hold_after_audit=True)
    # The admin gate makes the committed key visible at the entry replay check.
    assert one[1]=='created' and two[1]=='error:audit_event_conflict'
    model=ProjectMembership if scope=='PROJECT' else SoftwareMembership
    with Session(engine) as db:
        assert db.get(model,body.membership_id).status=='SUSPENDED'
        assert db.get(model,second.membership_id) is None
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_no==body.event_no))==1


@pytest.mark.parametrize('scope',['PROJECT','SOFTWARE'])
def test_other_transaction_commits_audit_key_after_entry_check_before_record(pg,monkeypatch,scope):
    from app.services.audit import AuditEventService
    engine,_=pg;ids,requests=setup(engine,monkeypatch);body=body_for(engine,ids[2],scope)
    original=AuditEventService.record
    def committed_elsewhere(service,**kwargs):
        with Session(engine) as other:
            original(AuditEventService(other),event_no=body.event_no,event_type='UNRELATED',action='READ',
                entity_type='OTHER',entity_ref='other transaction',actor_name='Historical actor',summary='Other evidence')
            other.commit()
        return original(service,**kwargs)
    monkeypatch.setattr(AuditEventService,'record',committed_elsewhere)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as caught:register_membership(scope,body,requests[0],db)
        assert caught.value.status_code==409 and caught.value.detail=='membership_registration_conflict'
        assert not db.in_transaction()
    model=ProjectMembership if scope=='PROJECT' else SoftwareMembership
    with Session(engine) as db:
        assert db.get(model,body.membership_id) is None
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_no==body.event_no))==1
        assert db.scalar(select(AuditEvent.event_type).where(AuditEvent.event_no==body.event_no))=='UNRELATED'
