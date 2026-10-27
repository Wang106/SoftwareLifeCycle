"""Synthetic exact-project selectors: no real identity/provider/storage access."""
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import select, event
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.core import Artifact, ComponentDefinition, ReleaseComponent, Release, ApplicationReleaseDetail
from app.models.snapshot import SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule as Rule
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution
from app.models.production import ManufacturingSite, ProductionLine
from app.models.security import ProjectMembership, SecurityPrincipal, BrowserSession
from app.models.approval import ReleaseDecision, ApprovalRequest
from app.services.private_distribution_selection import PrivateDistributionSelection
from test_authorization_approval import approval_db, approval_client, actor_request, counts, TOKEN  # noqa:F401
from test_authorization_approval_postgres import approval_pg  # noqa:F401
from test_command_concurrency_postgres import pg  # noqa:F401


def seed(db, ids):
    db.add(ProjectMembership(principal_id=ids['people']['approver'],project_id=ids['project'],role='DISTRIBUTION_AUTHORITY'))
    definition=ComponentDefinition(code='SEL-C',name='Synthetic component');db.add(definition);db.flush()
    component=ReleaseComponent(release_id=ids['release'],component_definition_id=definition.id,version='1');db.add(component);db.flush()
    artifacts={}
    for index,name in enumerate(['allow','specificdeny','specificallow','internal','approval','missing','ambiguous']):
        source=Artifact(release_component_id=component.id,artifact_type='BINARY',filename=name+'.bin',storage_reference='SECRET-STORAGE',
            sha256=str(index)*64,classification='CONFIDENTIAL',distribution_level='EXTERNAL',ai_access_policy='DENY')
        db.add(source);db.flush()
        artifact=SnapshotArtifact(snapshot_id=ids['snapshot'],source_artifact_id=source.id,component_code='SEL-C',component_version='1',
            filename=name+'.bin',artifact_type='BINARY',sha256=str(index)*64,classification='CONFIDENTIAL',
            distribution_level='INTERNAL_ONLY' if name=='internal' else 'EXTERNAL',ai_access_policy='DENY',storage_reference='SECRET-STORAGE')
        db.add(artifact);db.flush();artifacts[name]=artifact.id
        if name!='missing':
            generic='DENY' if name=='specificallow' else 'APPROVAL_REQUIRED' if name=='approval' else 'ALLOW'
            db.add(Rule(snapshot_artifact_id=artifact.id,recipient_type='CUSTOMER',recipient_code=None,purpose='PRODUCTION',decision=generic))
        if name in ('specificdeny','specificallow'):
            db.add(Rule(snapshot_artifact_id=artifact.id,recipient_type='CUSTOMER',recipient_code='PAA-C',purpose='PRODUCTION',decision='DENY' if name=='specificdeny' else 'ALLOW'))
        if name=='ambiguous':db.add(Rule(snapshot_artifact_id=artifact.id,recipient_type='CUSTOMER',recipient_code=None,purpose='PRODUCTION',decision='DENY'))
    db.add(DeliveryPackageItem(delivery_package_id=ids['package'],snapshot_artifact_id=artifacts['allow'],policy_decision='ALLOW'))
    detail=db.get(ApplicationReleaseDetail,ids['release'])
    for n,project,status in [('own',ids['project'],'ACTIVE'),('foreign',ids['foreign_project'],'ACTIVE'),('inactive',ids['project'],'INACTIVE')]:
        site=ManufacturingSite(site_code='SEL-'+n,customer_id=detail.customer_id,project_id=project,name='Site '+n,status=status)
        db.add(site);db.flush()
        db.add_all([ProductionLine(site_id=site.id,line_code='ACTIVE',name='Active line'),ProductionLine(site_id=site.id,line_code='INACTIVE',name='Inactive line',status='INACTIVE')])
    db.commit();return artifacts


@pytest.fixture(params=['sqlite','postgres'])
def selection_db(request):
    if request.param=='sqlite':
        db,ids=request.getfixturevalue('approval_db');yield db,ids,seed(db,ids)
    else:
        engine,ids=request.getfixturevalue('approval_pg')
        with Session(engine,expire_on_commit=False) as db:yield db,ids,seed(db,ids)


def artifacts(db,ids,**kwargs):
    return PrivateDistributionSelection(db).artifacts(actor_request(db,ids),ids['release'],'CUSTOMER','PAA-C','PRODUCTION',**kwargs)


def test_policy_filtered_before_pagination_and_no_private_fields(selection_db,monkeypatch):
    db,ids,records=selection_db;monkeypatch.setattr(settings,'read_only_mode',True);before=counts(db)
    page=artifacts(db,ids,limit=2);assert len(page['items'])==2 and page['next_offset']==2
    pins={'expected_snapshot_id':uuid.UUID(page['context']['snapshot_id']),'expected_decision_id':uuid.UUID(page['context']['release_decision_id'])}
    last=artifacts(db,ids,limit=2,offset=2,**pins);rows=page['items']+last['items']
    assert {r['snapshot_artifact_id'] for r in rows}=={records[x] for x in ('allow','specificallow','approval')}
    assert last['next_offset'] is None
    assert all(set(r)=={'snapshot_artifact_id','filename','artifact_type','component_code','component_version','sha256','policy_decision'} for r in rows)
    assert 'SECRET-STORAGE' not in str(page)+str(last) and 'ai_access_policy' not in str(page)
    assert not db.in_transaction() and counts(db)==before


@pytest.mark.parametrize('kind',['release','package','distribution'])
@pytest.mark.parametrize('name',['admin','foreign','creator'])
def test_missing_role_or_foreign_scope_hidden(selection_db,kind,name):
    db,ids,_=selection_db;before=counts(db);svc=PrivateDistributionSelection(db);request=actor_request(db,ids,name)
    # Creator has production authority, so for authorization scope use a foreign role principal instead.
    if kind=='distribution' and name=='creator':
        db.get(ProjectMembership,ids['grants']['creator']).status='SUSPENDED';db.commit()
    with pytest.raises(HTTPException) as error:
        if kind=='release':svc.artifacts(request,ids['release'],'CUSTOMER','PAA-C','PRODUCTION')
        elif kind=='package':svc.package(request,ids['package'])
        else:svc.scope(request,ids['distribution'])
    assert error.value.status_code==404 and error.value.detail=='selection_target_not_found'
    assert not db.in_transaction() and counts(db)==before


@pytest.mark.parametrize('mode',['disabled','principal','service','session'])
def test_authentication_and_current_session_failclosed(selection_db,monkeypatch,mode):
    db,ids,_=selection_db;request=actor_request(db,ids,'service' if mode=='service' else 'approver')
    if mode=='disabled':monkeypatch.setattr(settings,'auth_mode','disabled')
    elif mode=='principal':db.get(SecurityPrincipal,ids['people']['approver']).status='DISABLED';db.commit()
    elif mode=='session':
        sid=uuid.uuid4();now=datetime.now(timezone.utc)
        db.add(BrowserSession(id=sid,principal_id=ids['people']['approver'],token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),created_at=now,expires_at=now+timedelta(minutes=5),revoked_at=now));db.commit();request=actor_request(db,ids,session_id=sid)
    with pytest.raises(HTTPException) as error:PrivateDistributionSelection(db).package(request,ids['package'])
    assert error.value.status_code==(403 if mode=='service' else 401) and not db.in_transaction()


def test_package_preserves_existing_revision_without_current_release_decision(selection_db):
    db,ids,_=selection_db
    # Existing distribution creation does not depend on current decision/approval.
    previous=db.get(ReleaseDecision,ids['decision'])
    db.add(ReleaseDecision(decision_no='SEL-HOLD',release_id=previous.release_id,snapshot_id=previous.snapshot_id,
        approval_request_id=previous.approval_request_id,readiness_status='READY',decision='HOLD',decided_by='Synthetic reviewer',
        supersedes_id=previous.id,correction_reason='Synthetic newer decision'));db.commit()
    context=PrivateDistributionSelection(db).package(actor_request(db,ids),ids['package'])['context']
    assert context['delivery_package_id']==str(ids['package']) and context['revision']==1
    assert context['snapshot_id']==str(ids['snapshot']) and context['release_decision_id'] is None
    assert context['recipient_code']=='PAA-C' and context['purpose']=='PRODUCTION'


def test_authorization_scope_fixed_customer_project_active_lines(selection_db):
    db,ids,_=selection_db
    # Authorization creation does not impose package READY or approval status anew.
    db.get(DeliveryPackage,ids['package']).status='HISTORICAL'
    decision=db.get(ReleaseDecision,ids['decision']);db.get(ApprovalRequest,decision.approval_request_id).status='REJECTED';db.commit()
    data=PrivateDistributionSelection(db).scope(actor_request(db,ids),ids['distribution'])
    assert len(data['items'])==1 and data['items'][0]['site_code']=='SEL-own' and data['items'][0]['line_code']=='ACTIVE'
    assert data['context']['project_id']==str(ids['project']) and data['context']['distribution_id']==str(ids['distribution'])
    assert 'total' not in data


def test_stale_page_pins_rejected_and_query_bounded(selection_db):
    db,ids,_=selection_db;statements=[]
    def record(_c,_cur,sql,_p,_ctx,_many):statements.append(sql)
    event.listen(db.get_bind(),'before_cursor_execute',record)
    try:artifacts(db,ids,limit=1)
    finally:event.remove(db.get_bind(),'before_cursor_execute',record)
    selected=[s for s in statements if 'snapshot_artifacts.filename' in s]
    assert len(selected)==1 and 'LIMIT' in selected[0] and 'storage_reference' not in selected[0]
    with pytest.raises(HTTPException) as error:artifacts(db,ids,expected_snapshot_id=ids['snapshot'],expected_decision_id=uuid.uuid4())
    assert error.value.status_code==409 and error.value.detail=='selection_context_changed'


def test_missing_target_and_ssr_never_expose_metadata(selection_db):
    db,ids,_=selection_db
    with pytest.raises(HTTPException) as error:PrivateDistributionSelection(db).package(actor_request(db,ids),uuid.uuid4())
    assert error.value.status_code==404
    db.get(Release,ids['release']).release_type='STANDARD';db.commit()
    with pytest.raises(HTTPException) as error:artifacts(db,ids)
    assert error.value.status_code==404


@pytest.mark.parametrize('query',['limit=51','offset=1','limit=0','offset=100001','unexpected=x'])
def test_route_bounds_and_pins(approval_client,query):
    client,headers,ids=approval_client
    response=client.get('/api/v1/selection-context/releases/'+str(ids['release'])+'/delivery-artifacts?recipient_type=CUSTOMER&recipient_code=PAA-C&purpose=PRODUCTION&'+query,headers=headers)
    assert response.status_code==422 and response.headers['cache-control']=='private, no-store'


@pytest.mark.parametrize('method,suffix',[('GET',''),('HEAD',''),('GET','/')])
def test_authdisabled_private_even_method_redirect(approval_client,monkeypatch,method,suffix):
    client,headers,ids=approval_client;monkeypatch.setattr(settings,'auth_mode','disabled')
    response=client.request(method,'/api/v1/selection-context/deliveries/'+str(ids['package'])+suffix,headers=headers,follow_redirects=False)
    assert response.status_code==401 and response.headers['cache-control']=='private, no-store'


def test_role_revocation_applies_to_next_read(selection_db):
    db,ids,_=selection_db
    assert artifacts(db,ids)['items']
    membership=db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id==ids['people']['approver'],
        ProjectMembership.role=='DISTRIBUTION_AUTHORITY'))
    membership.status='SUSPENDED';db.commit()
    with pytest.raises(HTTPException) as error:artifacts(db,ids)
    assert error.value.status_code==404 and not db.in_transaction()


def test_real_middleware_serializes_minimal_readonly_contexts(approval_client,approval_db,monkeypatch):
    client,headers,ids=approval_client;db,_=approval_db;seed(db,ids);monkeypatch.setattr(settings,'read_only_mode',True)
    prefix='/api/v1/selection-context/'
    for path in ['releases/'+str(ids['release'])+'/delivery-artifacts?recipient_type=CUSTOMER&recipient_code=PAA-C&purpose=PRODUCTION',
                 'deliveries/'+str(ids['package']),'distributions/'+str(ids['distribution'])+'/authorization-scope']:
        response=client.get(prefix+path,headers=headers)
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='private, no-store' and 'x-browser-session' in response.headers['vary'].lower()
        assert 'SECRET-STORAGE' not in response.text and response.json()['context']['release_id']==str(ids['release'])
    response=client.get(prefix+'deliveries/'+str(ids['package']))
    assert response.status_code==401 and response.headers['cache-control']=='private, no-store'


def _assert_selector_waits_for_committed_writer(engine, write, read, expected):
    """Observe actual PostgreSQL lock ownership, not elapsed-time coincidence."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import text
    ready, release = Event(), Event()
    pids = {}
    def holder():
        with Session(engine) as db:
            pids['holder'] = db.scalar(text('SELECT pg_backend_pid()'))
            write(db)
            db.flush()
            ready.set()
            assert release.wait(15), 'writer release timeout'
            db.commit()
    def selector():
        with Session(engine) as db:
            pids['selector'] = db.scalar(text('SELECT pg_backend_pid()'))
            try:
                read(db)
                return 'unexpected_data'
            except HTTPException as exc:
                assert not db.in_transaction()
                return exc.status_code, exc.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(holder)
        second = None
        try:
            assert ready.wait(10), 'writer did not acquire expected lock'
            second = pool.submit(selector)
            deadline = time.monotonic()+10
            while True:
                with engine.connect() as connection:
                    blockers = connection.scalar(text('SELECT pg_blocking_pids(:pid)'),
                                                 {'pid':pids.get('selector',0)})
                if pids['holder'] in (blockers or []):
                    break
                assert time.monotonic()<deadline, 'selector did not block behind writer'
                time.sleep(.01)
        finally:
            release.set()
        first.result(timeout=15)
        assert second is not None and second.result(timeout=15)==expected


def test_postgres_selector_waits_for_current_role_revocation(approval_pg):
    from app.services.admin_lock import admin_write_gate
    engine,ids=approval_pg
    with Session(engine,expire_on_commit=False) as db:
        seed(db,ids)
        grant_id=db.scalar(select(ProjectMembership.id).where(ProjectMembership.principal_id==ids['people']['approver'],
            ProjectMembership.role=='DISTRIBUTION_AUTHORITY'))
    def revoke(db):
        admin_write_gate(db)
        db.scalar(select(SecurityPrincipal).where(SecurityPrincipal.id==ids['people']['approver']).with_for_update())
        grant=db.scalar(select(ProjectMembership).where(ProjectMembership.id==grant_id).with_for_update())
        grant.status='SUSPENDED'
    _assert_selector_waits_for_committed_writer(engine,revoke,lambda db:artifacts(db,ids),
                                               (404,'selection_target_not_found'))


def test_postgres_pinned_selector_waits_for_release_decision_replacement(approval_pg):
    engine,ids=approval_pg
    with Session(engine,expire_on_commit=False) as db:
        seed(db,ids)
        first=artifacts(db,ids,limit=1)
    pins={'expected_snapshot_id':uuid.UUID(first['context']['snapshot_id']),
          'expected_decision_id':uuid.UUID(first['context']['release_decision_id'])}
    def replace(db):
        db.scalar(select(Release).where(Release.id==ids['release']).with_for_update())
        previous=db.get(ReleaseDecision,ids['decision'])
        db.add(ReleaseDecision(decision_no='SEL-CONCURRENT-RELEASE',release_id=previous.release_id,
            snapshot_id=previous.snapshot_id,approval_request_id=previous.approval_request_id,readiness_status='READY',
            decision='RELEASE',decided_by='Synthetic reviewer',supersedes_id=previous.id,
            correction_reason='Synthetic concurrent evidence replacement'))
    _assert_selector_waits_for_committed_writer(engine,replace,
        lambda db:artifacts(db,ids,limit=1,offset=1,**pins),(409,'selection_context_changed'))
