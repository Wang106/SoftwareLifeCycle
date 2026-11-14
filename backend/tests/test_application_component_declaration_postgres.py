"""Independent sessions in normal CI disposable migrated PostgreSQL only."""
import uuid
import pytest
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.core import ReleaseComponent
from app.models.audit import AuditEvent
from test_command_concurrency_postgres import pg,overlapping_commands,count
from test_application_release_creation import configure,seed,formal_standard
from test_application_release_creation_postgres import command
from test_application_component_declaration import seed_components,body,submit,service,request

@pytest.fixture
def component_pg(pg,monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    engine,_=pg
    with Session(engine,expire_on_commit=False) as db: ids=seed_components(db,seed(db))
    return engine,ids

@pytest.mark.parametrize('race',['same_key','different_body','same_version','different_version'])
def test_serialized_replay_and_independent_versions(component_pg,monkeypatch,race):
    engine,ids=component_pg
    with Session(engine) as db: values=body(db,ids);other=body(db,ids)
    if race=='same_key': other=dict(values)
    elif race=='different_body': other={**values,'reason':'Different'}
    elif race=='different_version': other['version']='v2'
    one,two=overlapping_commands(engine,monkeypatch,command(lambda db:submit(db,ids,values)),command(lambda db:submit(db,ids,other)))
    assert one[0]==two[0]=='ok'
    if race=='same_key': assert one[1]==two[1]
    elif race=='different_body': assert two[1].startswith('denied:409:')
    else: assert not two[1].startswith('denied:')
    with Session(engine) as db:
        expected=1 if race in ('same_key','different_body') else 2
        assert count(db,ReleaseComponent,release_id=ids['release'])==expected
        assert count(db,AuditEvent,event_type='APPLICATION_COMPONENT_DECLARED')==expected
        assert service(db).receipt(values['request_id'],request(db,ids))['applied_status']=='DRAFT'

@pytest.mark.parametrize('revoke_first',[False,True])
def test_standard_revocation_serializes(component_pg,monkeypatch,revoke_first):
    from app.services.revocation import RevocationService
    engine,ids=component_pg
    with Session(engine) as db: formal_standard(db,ids);values=body(db,ids,True)
    declare=command(lambda db:submit(db,ids,values))
    revoke=lambda db:RevocationService(db).revoke('RELEASE',ids['standard'],'Concurrent revocation',request_id=uuid.uuid4())
    one,two=overlapping_commands(engine,monkeypatch,revoke if revoke_first else declare,declare if revoke_first else revoke)
    assert one[0]==two[0]=='ok'
    if revoke_first: assert two[1]=='denied:409:standard_release_revoked'
    with Session(engine) as db:
        assert count(db,ReleaseComponent,release_id=ids['release'])==(0 if revoke_first else 1)

@pytest.mark.parametrize('kind',['principal','project','software','session'])
def test_admin_revocation_rechecked_by_blocked_replay(component_pg,kind):
    import hashlib,time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import select,text
    from fastapi import HTTPException
    from app.models.security import SecurityPrincipal,ProjectMembership,SoftwareMembership,BrowserSession
    from app.services.admin_lock import admin_write_gate
    from test_application_release_creation import TOKEN
    engine,ids=component_pg;sid=None
    with Session(engine) as db:
        values=body(db,ids);submit(db,ids,values)
        if kind=='session':
            sid=uuid.uuid4();now=datetime.now(timezone.utc)
            db.add(BrowserSession(id=sid,principal_id=ids['actor'],token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
                created_at=now,expires_at=now+timedelta(minutes=5)));db.commit()
    ready,release=Event(),Event();pids={}
    def revoke():
        with Session(engine) as db:
            admin_write_gate(db)
            model,key={'principal':(SecurityPrincipal,ids['actor']),'project':(ProjectMembership,ids['pm']),
                'software':(SoftwareMembership,ids['sm']),'session':(BrowserSession,sid)}[kind]
            row=db.scalar(select(model).where(model.id==key).with_for_update())
            if kind=='session': row.revoked_at=datetime.now(timezone.utc)
            else: row.status='DISABLED' if kind=='principal' else 'SUSPENDED'
            db.flush();ready.set();assert release.wait(8);db.commit()
    def replay():
        with Session(engine) as db:
            pids['waiter']=db.scalar(text('SELECT pg_backend_pid()'))
            try: service(db).create(request=request(db,ids,sid),**values);return 200
            except HTTPException as exc:
                assert not db.in_transaction();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        holder=pool.submit(revoke)
        try:
            assert ready.wait(5);waiter=pool.submit(replay);deadline=time.monotonic()+5
            while True:
                with engine.connect() as con: blocked=con.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'),{'pid':pids.get('waiter',0)})
                if blocked: break
                assert time.monotonic()<deadline;time.sleep(.01)
        finally: release.set()
        holder.result(timeout=10);assert waiter.result(timeout=10) in (401,403)

@pytest.mark.parametrize('snapshot_first',[False,True])
def test_baseline_snapshot_lock_is_compatible(component_pg,monkeypatch,snapshot_first):
    from app.services.snapshot import SnapshotService
    from app.models.core import Release
    from test_command_audit import prepare_snapshot_source
    engine,ids=component_pg
    with Session(engine) as db:
        prepare_snapshot_source(db,db.get(Release,ids['standard']));db.commit();values=body(db,ids,True)
    declare=command(lambda db:submit(db,ids,values))
    snapshot=lambda db:SnapshotService().create(db,ids['standard'],request_id=uuid.uuid4())
    one,two=overlapping_commands(engine,monkeypatch,snapshot if snapshot_first else declare,declare if snapshot_first else snapshot)
    assert one[0]==two[0]=='ok'
    with Session(engine) as db: assert count(db,ReleaseComponent,release_id=ids['release'])==1


def test_deferred_parent_guard_rolls_back_component_and_audit(component_pg,monkeypatch):
    from fastapi import HTTPException
    from app.models.core import ApplicationReleaseDetail
    engine,ids=component_pg
    with Session(engine) as db:
        values=body(db,ids);original_commit=db.commit
        def invalid_parent_at_commit():
            # Existing deferred ASR relationship trigger, not a test-only schema change.
            db.get(ApplicationReleaseDetail,ids['release']).standard_base_release_id=ids['release']
            original_commit()
        monkeypatch.setattr(db,'commit',invalid_parent_at_commit)
        with pytest.raises(HTTPException) as exc: submit(db,ids,values)
        assert exc.value.status_code==409 and not db.in_transaction()
        assert db.get(ReleaseComponent,values['request_id']) is None
        assert count(db,AuditEvent,event_type='APPLICATION_COMPONENT_DECLARED')==0
        assert db.get(ApplicationReleaseDetail,ids['release']).standard_base_release_id==ids['standard']
