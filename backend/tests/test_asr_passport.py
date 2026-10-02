import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_distribution_catalog import chain
from test_command_concurrency_postgres import pg
from app.api.asr_passport import Selection, Page, summary, history
from app.core.db import get_db
from app.main import app
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.distribution import DeliveryPackage
from app.models.audit import AuditEvent


def seed(db, release, snapshot):
    release.release_type='APPLICATION'
    a=ApprovalRequest(approval_no='PASSPORT-APR',target_type='RELEASE',target_id=release.id,snapshot_id=snapshot.id,status='APPROVED')
    db.add(a);db.flush()
    d=ReleaseDecision(decision_no='PASSPORT-DEC',release_id=release.id,snapshot_id=snapshot.id,approval_request_id=a.id,readiness_status='READY',decision='RELEASE',decided_by='Trusted actor',decision_notes='Recorded note')
    db.add(d);db.commit();return a,d

@pytest.fixture
def passport(chain):
    db,r,s,*_=chain;a,d=seed(db,r,s);return chain,a,d

def filters(result, **kw):return Page(**(result['selection']|kw))

def test_exact_summary_counts_fields_and_legacy_compatibility(passport):
    chain,a,d=passport;db,r,s,old,packages,*_=chain;result=summary(r.id,Selection(),db)
    assert result['selection']=={'snapshot_id':str(s.id),'decision_id':str(d.id)}
    assert result['counts']=={'decisions':1,'deliveries':1,'distributions':2,'authorizations':2}
    assert result['decision']['context_consistent'] and result['decision']['is_current_snapshot']
    assert result['decision']['approval_no']==a.approval_no and result['decision']['decision_notes']=='Recorded note'
    assert result['profile']['snapshot']['content_hash']==s.content_hash
    assert history(r.id,filters(result),db,'deliveries')['items'][0]['revision']==2
    from app.api.dashboard import application_release_decisions,application_release_downstream
    assert len(application_release_decisions(r.id,db)['decisions'])==1
    assert len(application_release_downstream(r.id,db)['deliveries'])==2

@pytest.mark.parametrize('kind',['decisions','deliveries','distributions','authorizations'])
def test_independent_pages_empty_offsets_and_envelopes(passport,kind):
    chain,a,d=passport;db,r,*_=chain;result=summary(r.id,Selection(),db)
    page=history(r.id,filters(result,limit=1),db,kind)
    assert page['total']==result['counts'][kind] and len(page['items'])==1
    assert page['snapshot_id']==result['selection']['snapshot_id'] and page['decision_id']==str(d.id)
    end=history(r.id,filters(result,offset=100),db,kind)
    assert end['items']==[] and end['next_offset'] is None and end['total']==page['total']
    if page['total']>1:
        second=history(r.id,filters(result,offset=1,limit=1),db,kind)
        assert page['next_offset']==1 and page['items'][0]['id']!=second['items'][0]['id']

@pytest.mark.parametrize('case',['snapshot','decision','release','standard'])
def test_wrong_parent_and_type_404(passport,case):
    chain,a,d=passport;db,r,*_=chain;result=summary(r.id,Selection(),db);rid=r.id;kw=result['selection'].copy()
    if case in ['snapshot','decision']:kw[case+'_id']=str(uuid.uuid4())
    elif case=='release':rid=uuid.uuid4()
    else:r.release_type='STANDARD';db.commit()
    with pytest.raises(HTTPException) as error:summary(rid,Selection(**kw),db)
    assert error.value.status_code==404


def test_historical_pins_remain_exact_after_new_snapshot_and_hold(passport):
    chain,a,d=passport;db,r,s,*_=chain;original=summary(r.id,Selection(),db)
    newer=ReleaseSnapshot(release_id=r.id,snapshot_no='PASSPORT-NEW',snapshot_number=9,content_hash='9'*64,status='FROZEN');db.add(newer);db.flush()
    hold=ReleaseDecision(decision_no='PASSPORT-HOLD',release_id=r.id,snapshot_id=newer.id,approval_request_id=a.id,readiness_status='BLOCKED',decision='HOLD',decided_by='Trusted actor');db.add(hold);db.commit()
    pinned=summary(r.id,Selection(**original['selection']),db)
    assert pinned['selection']==original['selection'] and not pinned['profile']['snapshot']['is_current_snapshot']
    assert not pinned['decision']['is_current_snapshot'] and not pinned['decision']['is_latest_decision']
    assert history(r.id,filters(original),db,'deliveries')['items'][0]['snapshot_id']==str(s.id)
    assert summary(r.id,Selection(),db)['decision']['decision']=='HOLD'


def test_explicit_empty_selection_never_reselects(passport):
    chain,a,d=passport;db,r,*_=chain;result=summary(r.id,Selection(snapshot_id='none',decision_id='none'),db)
    assert result['profile']['snapshot'] is None and result['decision'] is None
    assert result['counts']['deliveries']==2 and result['counts']['decisions']==1
    assert history(r.id,filters(result),db,'deliveries')['total']==2

@pytest.mark.parametrize('case',['orphan_snapshot','foreign_snapshot','approval_target','approval_snapshot'])
def test_missing_metadata_never_widens_scope(passport,case):
    chain,a,d=passport;db,r,s,old,packages,*_=chain
    if case=='orphan_snapshot':d.snapshot_id=uuid.uuid4()
    elif case=='foreign_snapshot':s.release_id=uuid.uuid4()
    elif case=='approval_target':a.target_id=uuid.uuid4()
    else:a.snapshot_id=old.id
    db.commit();result=summary(r.id,Selection(snapshot_id='none',decision_id=d.id),db)
    assert not result['decision']['context_consistent']
    rows=history(r.id,filters(result),db,'deliveries')
    assert rows['total']==(0 if case=='orphan_snapshot' else 1)
    if case=='foreign_snapshot':assert result['decision']['snapshot_no'] is None and rows['items'][0]['snapshot_no'] is None
    if case.startswith('approval'):assert result['decision']['approval_no'] is None

@pytest.mark.parametrize('kw',[{'snapshot_id':'bad','decision_id':'none'},{'snapshot_id':'none'}, {'unknown':1}])
def test_strict_selection(kw):
    with pytest.raises(ValidationError):Selection(**kw)

@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'extra':1}])
def test_strict_page(kw):
    with pytest.raises(ValidationError):Page(**({'snapshot_id':'none','decision_id':'none'}|kw))


def test_growth_keeps_fixed_queries_and_bounded_records(passport):
    chain,a,d=passport;db,r,s,*_=chain;rid,sid,did=r.id,s.id,d.id;calls=[]
    def capture(_c,_cursor,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();calls.clear();result=summary(rid,Selection(snapshot_id=sid,decision_id=did),db)
        page=history(rid,filters(result,limit=2),db,'deliveries');return result,page,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        db.add_all([DeliveryPackage(package_no=f'GROW-{n}',revision=1,release_id=rid,snapshot_id=sid,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION') for n in range(120)]);db.commit();grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['counts']['deliveries']==121 and len(grown[1]['items'])==2 and small[2]==grown[2]


def test_http_strict_pins_and_readonly(passport,monkeypatch):
    from app import main
    chain,a,d=passport;db,r,s,*_=chain;rid,sid,did=r.id,s.id,d.id;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root=f'/api/v1/releases/application/id/{rid}/passport'
            assert client.get(root+'/summary').json()['counts']['deliveries']==1
            for q in ['?unknown=1',f'?snapshot_id={sid}','?snapshot_id=bad&decision_id=none']:assert client.get(root+'/summary'+q).status_code==422
            for kind in ['decisions','deliveries','distributions','authorizations']:
                assert client.get(root+'/'+kind).status_code==422
                query=f'?snapshot_id={sid}&decision_id={did}&limit=1'
                assert len(client.get(root+'/'+kind+query).json()['items'])==1
                for q in ['&limit=101','&offset=-1','&unknown=1']:assert client.get(root+'/'+kind+query+q).status_code==422
            assert client.post(f'/api/v1/releases/{rid}/create-snapshot',json={}).json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()

@pytest.mark.parametrize('case',['pagination','new_commit','foreign_pin','empty_pin'])
def test_real_postgresql_exact_history_no_audit_write(pg,case):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);s=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==r.id));a,d=seed(db,r,s)
        db.add_all([DeliveryPackage(package_no=f'PG-{n}',revision=1,release_id=r.id,snapshot_id=s.id,recipient_type='CUSTOMER',recipient_code='C',purpose='PRODUCTION') for n in range(3)]);db.commit()
        before=db.scalar(select(func.count()).select_from(AuditEvent));original=summary(r.id,Selection(),db)
        if case=='pagination':
            pages=[history(r.id,filters(original,limit=1,offset=n),db,'deliveries') for n in range(3)]
            assert all(p['total']==3 for p in pages) and len({p['items'][0]['id'] for p in pages})==3
        elif case=='new_commit':
            with Session(engine) as writer:
                writer.add(ReleaseSnapshot(release_id=r.id,snapshot_no='PG-NEW',snapshot_number=99,content_hash='a'*64,status='FROZEN'));writer.commit()
            assert not summary(r.id,Selection(**original['selection']),db)['profile']['snapshot']['is_current_snapshot']
            assert history(r.id,filters(original),db,'deliveries')['total']==3
        elif case=='foreign_pin':
            other=Release(software_id=r.software_id,release_type='APPLICATION',version=r.version+'-other');db.add(other);db.commit()
            with pytest.raises(HTTPException):summary(other.id,Selection(**original['selection']),db)
        else:
            empty=summary(r.id,Selection(snapshot_id='none',decision_id='none'),db)
            assert empty['decision'] is None and empty['profile']['snapshot'] is None
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
