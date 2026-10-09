"""Offline operator controls: disabled gates, binding, privacy and recovery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON, create_engine, event, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app import admin_operator as cli
from app.core.config import Settings, settings
from app.core.db import Base
from app.models.audit import AuditEvent
from app.models.security import BrowserSession, GlobalRoleAssignment, SecurityPrincipal
from app.services.admin_operator import BootstrapAdmin, RecoverAdmin, OperatorError, apply, database_context, plan
from app.services.audit import AuditEventError, AuditEventService
from test_command_concurrency_postgres import pg


@pytest.fixture(params=['sqlite','postgres'])
def operator_db(monkeypatch,request):
    if request.param=='postgres':
        engine,_=request.getfixturevalue('pg')
    else:
        engine=create_engine('sqlite+pysqlite:///:memory:')
        monkeypatch.setattr(AuditEvent.__table__.c.payload_json,'type',JSONB().with_variant(JSON(),'sqlite'))
        Base.metadata.create_all(engine,tables=[m.__table__ for m in [SecurityPrincipal,GlobalRoleAssignment,BrowserSession,AuditEvent]])
        with engine.begin() as db:
            db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32))'))
            db.execute(text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': settings.required_db_revision})
    monkeypatch.setattr(settings,'admin_operator_enabled',True)
    monkeypatch.setattr(settings,'read_only_mode',False)
    monkeypatch.setattr(settings,'auth_mode','oidc')
    monkeypatch.setattr(settings,'oidc_issuer_url','https://operator-test.example.com')
    monkeypatch.setattr(settings,'oidc_audience','test-api')
    monkeypatch.setattr(settings,'oidc_jwks_url','https://operator-test.example.com/keys')
    with Session(engine,expire_on_commit=False) as db:
        yield db
    if request.param=='sqlite':engine.dispose()


def bootstrap(db,**changes):
    data={'event_no':'OP-'+uuid.uuid4().hex,'reason':'Approved first administrator reference',
        'approval_ref':'TEST-APPROVAL-123','acknowledge_privileged_change':True,'expected_effective_admin_count':0,
        'principal_id':uuid.uuid4(),'grant_id':uuid.uuid4(),'subject':'approved-subject-'+uuid.uuid4().hex,
        'display_name':'Approved Person','target_fingerprint':database_context(db)[0]}
    return BootstrapAdmin(**{**data,**changes})


def suspend(db,body,principal_status='ACTIVE',grant_status='SUSPENDED'):
    db.get(SecurityPrincipal,body.principal_id).status=principal_status
    db.get(GlobalRoleAssignment,body.grant_id).status=grant_status
    db.commit()


def recover(db,created,**changes):
    principal=db.get(SecurityPrincipal,created.principal_id);grant=db.get(GlobalRoleAssignment,created.grant_id)
    return RecoverAdmin(event_no='REC-'+uuid.uuid4().hex,reason='Approved administrator recovery review',
        approval_ref='TEST-RECOVERY-123',acknowledge_privileged_change=True,expected_effective_admin_count=0,
        principal_id=principal.id,grant_id=grant.id,target_fingerprint=database_context(db)[0],
        **{'expected_principal_status':principal.status,'expected_grant_status':grant.status,**changes})


def test_plan_is_bounded_read_only_and_bootstrap_replay_preserves_later_state(operator_db):
    db=operator_db
    initial=plan(db)
    assert initial['bootstrap_available'] and initial['effective_admin_count']==0
    assert 'database_role' not in initial and 'subject' not in initial
    before=db.scalar(select(func.count()).select_from(AuditEvent))
    body=bootstrap(db);result=apply(db,body)
    assert result['current_principal_status']==result['current_grant_status']=='ACTIVE'
    assert db.get(SecurityPrincipal,body.principal_id).principal_type=='USER'
    assert db.get(SecurityPrincipal,body.principal_id).email is None
    assert db.scalar(select(func.count()).select_from(AuditEvent))==before+1
    assert plan(db)['effective_admin_count']==1 and not plan(db)['bootstrap_available']
    suspend(db,body,'DISABLED')
    repeated=apply(db,body)
    assert repeated['replayed'] and repeated['applied_grant_status']=='ACTIVE'
    assert repeated['current_grant_status']=='SUSPENDED' and repeated['current_principal_status']=='DISABLED'
    audit=db.scalar(select(AuditEvent).where(AuditEvent.event_no==body.event_no))
    assert audit.actor_principal_id is None and audit.actor_name.startswith('LocalOperator/')
    assert audit.payload_json['authorization_source']=='LOCAL_OPERATOR_PROCESS_NOT_OIDC_HUMAN'
    for secret in [body.subject,body.display_name,settings.oidc_issuer_url,'password','token_digest']:
        assert secret not in str(audit.payload_json) and secret not in str(result)


@pytest.mark.parametrize('principal_status,grant_status',[('ACTIVE','SUSPENDED'),('DISABLED','ACTIVE'),('DISABLED','SUSPENDED')])
def test_recovery_activates_existing_user_and_revokes_only_own_unrevoked_sessions(operator_db,principal_status,grant_status):
    db=operator_db;body=bootstrap(db);apply(db,body);suspend(db,body,principal_status,grant_status)
    other=SecurityPrincipal(issuer=settings.oidc_issuer_url,subject='other-person',display_name='Other',principal_type='USER')
    db.add(other);db.flush();now=datetime.now(timezone.utc)
    rows=[BrowserSession(id=uuid.uuid4(),principal_id=p,token_digest='a'*64,created_at=now-timedelta(hours=2),
        expires_at=now+timedelta(hours=1) if i!=1 else now-timedelta(hours=1),
        revoked_at=now-timedelta(hours=1) if i==2 else None) for i,p in enumerate([body.principal_id]*3+[other.id])]
    db.add_all(rows);db.commit();db.expire_all();old_revoke=db.get(BrowserSession,rows[2].id).revoked_at
    request=recover(db,body);result=apply(db,request)
    assert result['revoked_browser_sessions']==2 and result['current_grant_status']==result['current_principal_status']=='ACTIVE'
    db.expire_all()
    assert all(db.get(BrowserSession,r.id).revoked_at is not None for r in rows[:3])
    assert db.get(BrowserSession,rows[2].id).revoked_at==old_revoke
    assert db.get(BrowserSession,rows[3].id).revoked_at is None
    suspend(db,body)
    repeated=apply(db,request)
    assert repeated['replayed'] and repeated['current_grant_status']=='SUSPENDED' and repeated['revoked_browser_sessions']==2


@pytest.mark.parametrize('setting,value,code',[('admin_operator_enabled',False,'operator_disabled'),('read_only_mode',True,'read_only_mode'),
    ('auth_mode','disabled','configured_oidc_required'),('oidc_issuer_url',None,'configured_oidc_required'),
    ('oidc_audience',None,'configured_oidc_required'),('oidc_jwks_url',None,'configured_oidc_required')])
def test_all_gates_reject_before_query_or_mutation(operator_db,monkeypatch,setting,value,code):
    db=operator_db;body=bootstrap(db);db.rollback()
    monkeypatch.setattr(settings,setting,value)
    statements=[]
    def capture(*args):statements.append(args[2])
    event.listen(db.get_bind(),'before_cursor_execute',capture)
    try:
        for command in [lambda:apply(db,body),lambda:plan(db)]:
            with pytest.raises(OperatorError,match=code):command()
        assert statements==[] and not db.in_transaction()
    finally:event.remove(db.get_bind(),'before_cursor_execute',capture)


@pytest.mark.parametrize('defect',['target','schema','active_admin','historical_admin','principal_id','subject','grant_id'])
def test_bootstrap_preconditions_never_adopt_existing_rows(operator_db,defect):
    db=operator_db;body=bootstrap(db);expected={'target':'operator_target_mismatch','schema':'operator_schema_not_ready',
        'active_admin':'effective_admin_exists','historical_admin':'historical_admin_requires_recovery',
        'principal_id':'operator_principal_conflict','subject':'operator_principal_conflict','grant_id':'operator_grant_conflict'}[defect]
    if defect=='target':body=body.model_copy(update={'target_fingerprint':'0'*64})
    if defect=='schema':db.execute(text("UPDATE alembic_version SET version_num='old'"));db.commit()
    if defect in ['active_admin','historical_admin']:
        other=bootstrap(db);apply(db,other)
        if defect=='historical_admin':suspend(db,other)
    if defect in ['principal_id','subject','grant_id']:
        person=SecurityPrincipal(id=body.principal_id if defect=='principal_id' else uuid.uuid4(),issuer=settings.oidc_issuer_url,
            subject=body.subject if defect=='subject' else 'another',principal_type='USER',display_name='Existing')
        db.add(person);db.flush()
        if defect=='grant_id':db.add(GlobalRoleAssignment(id=body.grant_id,principal_id=person.id,role='AUDITOR'))
        db.commit()
    before=db.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(OperatorError,match=expected):apply(db,body)
    assert not db.in_transaction()
    assert db.scalar(select(func.count()).select_from(AuditEvent))==before
    if defect!='principal_id':assert db.get(SecurityPrincipal,body.principal_id) is None


@pytest.mark.parametrize('field',['reason','approval_ref','subject','display_name','principal_id','grant_id','operator'])
def test_replay_is_exact_request_and_operator_context_bound(operator_db,monkeypatch,field):
    db=operator_db;body=bootstrap(db);apply(db,body)
    if field=='operator':
        monkeypatch.setattr('app.services.admin_operator.socket.gethostname',lambda:'different-operator-host')
        changed=body
    else:changed=body.model_copy(update={field:uuid.uuid4() if field.endswith('_id') else 'Changed-value'})
    with pytest.raises(OperatorError,match='operator_replay_conflict'):apply(db,changed)
    assert db.get(GlobalRoleAssignment,body.grant_id).status=='ACTIVE'


@pytest.mark.parametrize('defect',['missing_principal','wrong_issuer','service','wrong_grant','auditor','stale_principal','stale_grant','healthy_admin'])
def test_recovery_cannot_promote_or_rebind(operator_db,defect):
    db=operator_db;created=bootstrap(db);apply(db,created);suspend(db,created,'DISABLED')
    body=recover(db,created);expected='operator_existing_admin_grant_required'
    principal=db.get(SecurityPrincipal,created.principal_id);grant=db.get(GlobalRoleAssignment,created.grant_id)
    if defect=='missing_principal':body=body.model_copy(update={'principal_id':uuid.uuid4()});expected='operator_principal_not_found'
    if defect=='wrong_issuer':principal.issuer='https://wrong.example.com';expected='operator_recipient_ineligible'
    if defect=='service':principal.principal_type='SERVICE';expected='operator_recipient_ineligible'
    if defect=='wrong_grant':body=body.model_copy(update={'grant_id':uuid.uuid4()})
    if defect=='auditor':grant.role='AUDITOR'
    if defect=='stale_principal':body=body.model_copy(update={'expected_principal_status':'ACTIVE'});expected='operator_status_conflict'
    if defect=='stale_grant':body=body.model_copy(update={'expected_grant_status':'ACTIVE'});expected='operator_status_conflict'
    if defect=='healthy_admin':principal.status=grant.status='ACTIVE';expected='effective_admin_exists'
    db.commit()
    with pytest.raises(OperatorError,match=expected):apply(db,body)
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='ADMIN_OPERATOR_RECOVER'))==0


@pytest.mark.parametrize('operation',['bootstrap','recover'])
@pytest.mark.parametrize('failure',[RuntimeError,AuditEventError])
def test_audit_failure_rolls_back_identity_grant_and_revocation(operator_db,monkeypatch,operation,failure):
    db=operator_db;created=bootstrap(db)
    body=created
    if operation=='recover':
        apply(db,created);suspend(db,created,'DISABLED');body=recover(db,created)
        now=datetime.now(timezone.utc)
        db.add(BrowserSession(id=uuid.uuid4(),principal_id=created.principal_id,token_digest='a'*64,
            created_at=now,expires_at=now+timedelta(hours=1)));db.commit()
    def fail(*args,**kwargs):raise failure('forced audit failure')
    monkeypatch.setattr(AuditEventService,'record',fail)
    with pytest.raises(OperatorError if failure==AuditEventError else RuntimeError):apply(db,body)
    assert not db.in_transaction()
    principal=db.get(SecurityPrincipal,created.principal_id)
    if operation=='bootstrap':assert principal is None and db.get(GlobalRoleAssignment,created.grant_id) is None
    else:
        assert principal.status=='DISABLED' and db.get(GlobalRoleAssignment,created.grant_id).status=='SUSPENDED'
        assert db.scalar(select(BrowserSession.revoked_at).where(BrowserSession.principal_id==principal.id)) is None


@pytest.mark.parametrize('field,value',[('acknowledge_privileged_change',False),('acknowledge_privileged_change',1),
    ('expected_effective_admin_count',False),('expected_effective_admin_count','0'),('target_fingerprint','bad'),
    ('approval_ref','bad\nref'),('subject',' padded '),('display_name','bad\x7fname'),('role','PLATFORM_ADMIN')])
def test_privileged_request_validators_are_strict(operator_db,field,value):
    data=bootstrap(operator_db).model_dump()
    data[field]=value
    with pytest.raises(ValidationError):BootstrapAdmin(**data)


def test_cli_default_disabled_never_connects(monkeypatch,capsys):
    assert Settings(_env_file=None).admin_operator_enabled is False
    monkeypatch.setattr(settings,'admin_operator_enabled',False)
    monkeypatch.setattr(cli,'SessionLocal',lambda:pytest.fail('disabled operator must not open a database'))
    assert cli.main(['bootstrap','--request','never-read.json'])==1
    captured=capsys.readouterr()
    assert captured.out=='' and captured.err.strip()=='{"error": "operator_disabled"}'


@pytest.mark.parametrize('kind',['invalid','large','missing','runtime','database','sqlite'])
def test_cli_errors_are_sanitized_and_no_network_route_is_added(monkeypatch,tmp_path,capsys,kind):
    from app.main import app
    assert not any('operator' in getattr(r,'path','') or 'bootstrap' in getattr(r,'path','') or 'recover' in getattr(r,'path','') for r in app.routes)
    monkeypatch.setattr(cli,'preconditions',lambda:None)
    file=tmp_path/'request.json';file.write_text('private-subject-invalid-json')
    if kind=='large':file.write_text('secret'*3000)
    if kind=='missing':args=['bootstrap']
    elif kind in ['runtime','database','sqlite']:
        class DB:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def get_bind(self):return SimpleNamespace(dialect=SimpleNamespace(name='sqlite' if kind=='sqlite' else 'postgresql'))
        monkeypatch.setattr(cli,'SessionLocal',DB)
        def fail(db):
            if kind=='database':
                from sqlalchemy.exc import OperationalError
                raise OperationalError('private DSN password',{},Exception('secret'))
            raise RuntimeError('private secret')
        monkeypatch.setattr(cli,'plan',fail);args=['plan']
    else:args=['bootstrap','--request',str(file)]
    assert cli.main(args)==1
    captured=capsys.readouterr()
    assert captured.out=='' and 'private' not in captured.err and 'secret' not in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('setting',['oidc_issuer_url','oidc_audience','oidc_jwks_url','oidc_algorithms'])
def test_reviewed_target_fingerprint_binds_provider_configuration(operator_db,monkeypatch,setting):
    db=operator_db;body=bootstrap(db)
    value={'oidc_issuer_url':'https://changed.example.com','oidc_audience':'changed-api',
        'oidc_jwks_url':'https://changed.example.com/keys','oidc_algorithms':'ES256'}[setting]
    monkeypatch.setattr(settings,setting,value)
    with pytest.raises(OperatorError,match='operator_target_mismatch'):apply(db,body)
    assert db.get(SecurityPrincipal,body.principal_id) is None


def test_cli_argument_errors_do_not_echo_private_arguments(monkeypatch,capsys):
    monkeypatch.setattr(cli,'SessionLocal',lambda:pytest.fail('invalid arguments must not connect'))
    assert cli.main(['plan','--unrecognized-secret','private-value'])==1
    captured=capsys.readouterr()
    assert captured.out=='' and captured.err.strip()=='{"error": "invalid_operator_arguments"}'
