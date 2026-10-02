"""Pinned pagination, latest execution selection, bounded growth and migrated index."""
import uuid
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine,event,func,inspect,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.asr_evidence import EvidencePage,EvidenceSelection,evidence_artifacts,evidence_executions,evidence_summary
from app.api.dashboard import application_release_evidence
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot,SnapshotArtifact
from app.models.testing import DvpExecution,DvpItem,DvpPlan
from app.models.change import SoftwareChangeRequest

@pytest.fixture
def evidence(context):
    db,_,r,old,scr=context;r.release_type='APPLICATION'
    s=ReleaseSnapshot(release_id=r.id,snapshot_no='NEW',snapshot_number=2,content_hash='b'*64)
    plan=DvpPlan(change_request_id=scr.id,plan_no='P',title='Plan');db.add_all([s,plan]);db.flush()
    items=[DvpItem(plan_id=plan.id,item_no=f'DVP-{n}',title=f'Item {n}',scope='SOFTWARE_TEST') for n in range(3)];db.add_all(items);db.flush()
    for n in range(3):db.add(artifact(s))
    for i in items:
        for no,snapshot,result in [(1,s,'FAIL'),(2,s,'PASS'),(3,old,'FAIL')]:db.add(DvpExecution(dvp_item_id=i.id,execution_no=no,release_id=r.id,snapshot_id=snapshot.id,result=result,actual_result='private result'))
    db.commit();return db,r,s,old,plan,items

def artifact(s):return SnapshotArtifact(snapshot_id=s.id,source_artifact_id=uuid.uuid4(),component_code='APP',filename='same.hex',artifact_type='HEX',sha256='a'*64,classification='PUBLIC',distribution_level='EXTERNAL',ai_access_policy='DENY',storage_reference='private location')
def page(s,**kw):return EvidencePage(snapshot_id=s.id,**kw)

def test_counts_legacy_and_historical_selection(evidence):
    db,r,s,old,*_=evidence;result=evidence_summary(r.id,EvidenceSelection(),db)
    assert result=={'release_id':str(r.id),'snapshot':{'id':str(s.id),'snapshot_no':'NEW','is_current_snapshot':True},'artifact_count':3,'latest_execution_count':3,'other_snapshot_executions':3}
    legacy=application_release_evidence(r.id,db);assert len(legacy['artifacts'])==len(legacy['executions'])==3 and [i['execution_no'] for i in legacy['executions']]==[2]*3
    pinned=evidence_summary(r.id,EvidenceSelection(snapshot_id=old.id),db)
    assert not pinned['snapshot']['is_current_snapshot'] and pinned['other_snapshot_executions']==6 and pinned['artifact_count']==0 and pinned['latest_execution_count']==3

@pytest.mark.parametrize('fn',[evidence_artifacts,evidence_executions])
def test_stable_duplicate_pages_total_and_beyond_end(evidence,fn):
    db,r,s,*_=evidence;seen=[]
    for n in range(3):
        result=fn(r.id,page(s,limit=1,offset=n),db);assert result['total']==3 and len(result['items'])==1 and result['snapshot_id']==str(s.id) and result['release_id']==str(r.id)
        assert result['next_offset']==(n+1 if n<2 else None)
        seen.append(result['items'][0]['id']);assert 'private' not in str(result)
        if fn is evidence_executions:assert result['items'][0]['execution_no']==2 and result['items'][0]['result']=='PASS'
    assert len(set(seen))==3 and seen==[fn(r.id,page(s,limit=1,offset=n),db)['items'][0]['id'] for n in range(3)]
    beyond=fn(r.id,page(s,offset=50),db);assert beyond['total']==3 and beyond['items']==[] and beyond['next_offset'] is None

def test_new_snapshot_never_moves_pinned_pages(evidence):
    db,r,s,*_=evidence;db.add(ReleaseSnapshot(release_id=r.id,snapshot_no='NEWER',snapshot_number=3,content_hash='c'*64));db.commit()
    assert evidence_summary(r.id,EvidenceSelection(),db)['snapshot']['snapshot_no']=='NEWER'
    assert evidence_artifacts(r.id,page(s),db)['total']==evidence_executions(r.id,page(s),db)['total']==3
    assert not evidence_summary(r.id,EvidenceSelection(snapshot_id=s.id),db)['snapshot']['is_current_snapshot']

def test_same_version_other_release_executions_excluded(evidence):
    db,r,s,_,_,items=evidence;other=Release(software_id=uuid.uuid4(),release_type='APPLICATION',version=r.version);db.add(other);db.flush()
    db.add(DvpExecution(dvp_item_id=items[0].id,execution_no=4,release_id=other.id,snapshot_id=s.id,result='FAIL'));db.commit()
    assert evidence_executions(r.id,page(s),db)['items'][0]['execution_no']==2
    with pytest.raises(HTTPException) as err:evidence_artifacts(other.id,page(s),db)
    assert err.value.status_code==404

def test_duplicate_dvp_numbers_missing_metadata_retains_uuid(evidence):
    db,r,s,_,plan,items=evidence;p=DvpPlan(change_request_id=plan.change_request_id,plan_no='P2',title='Other');db.add(p);db.flush()
    i=DvpItem(plan_id=p.id,item_no=items[0].item_no,title='Same number other plan',scope='CUSTOMER_TEST');db.add(i);db.flush();missing=uuid.uuid4()
    for iid in [i.id,missing]:db.add(DvpExecution(dvp_item_id=iid,execution_no=1,release_id=r.id,snapshot_id=s.id,result='NOT_RUN'))
    db.commit();result=evidence_executions(r.id,page(s),db)
    assert result['total']==5 and len({i['dvp_item_id'] for i in result['items']})==5
    assert result['items'][-1]['dvp_item_id']==str(missing) and not result['items'][-1]['item_metadata_available']
    assert evidence_summary(r.id,EvidenceSelection(),db)['latest_execution_count']==5

@pytest.mark.parametrize('case',['missing_release','standard','missing_snapshot','foreign_snapshot'])
def test_invalid_exact_context_404(evidence,case):
    db,r,s,*_=evidence;rid=r.id;sid=s.id
    if case=='missing_release':rid=uuid.uuid4()
    elif case=='standard':r.release_type='STANDARD';db.commit()
    elif case=='missing_snapshot':sid=uuid.uuid4()
    else:s.release_id=uuid.uuid4();db.commit()
    for fn in [evidence_artifacts,evidence_executions]:
        with pytest.raises(HTTPException) as err:fn(rid,EvidencePage(snapshot_id=sid),db)
        assert err.value.status_code==404
    with pytest.raises(HTTPException) as err:evidence_summary(rid,EvidenceSelection(snapshot_id=sid),db)
    assert err.value.status_code==404

def test_no_snapshot_and_empty_evidence(evidence):
    db,r,*_=evidence;other=Release(software_id=r.software_id,release_type='APPLICATION',version='empty');db.add(other);db.commit()
    assert evidence_summary(other.id,EvidenceSelection(),db)=={'release_id':str(other.id),'snapshot':None,'artifact_count':0,'latest_execution_count':0,'other_snapshot_executions':0}
    s=ReleaseSnapshot(release_id=other.id,snapshot_no='EMPTY',snapshot_number=1,content_hash='c'*64);db.add(s);db.commit()
    for fn in [evidence_artifacts,evidence_executions]:assert fn(other.id,page(s),db)['items']==[]

@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'snapshot_id':'bad'},{'unknown':'value'}])
def test_strict_page_validation(evidence,kw):
    _,_,s,*_=evidence
    with pytest.raises(ValidationError):EvidencePage(**({'snapshot_id':s.id}|kw))

def test_growth_fixed_queries_no_child_orm_or_private_columns(evidence):
    db,r,s,_,plan,*_=evidence;calls=[]
    def capture(_conn,_cursor,statement,*_):calls.append(statement.lower())
    def read():
        rid,sid=r.id,s.id;db.expire_all();calls.clear()
        summary=evidence_summary(rid,EvidenceSelection(snapshot_id=sid),db)
        a=evidence_artifacts(rid,EvidencePage(snapshot_id=sid,limit=2),db);e=evidence_executions(rid,EvidencePage(snapshot_id=sid,limit=2),db)
        return summary,a,e,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        initial=read()
        for n in range(105):
            i=DvpItem(plan_id=plan.id,item_no=f'G-{n}',title='Growth',scope='SOFTWARE_TEST');db.add(i);db.flush()
            db.add_all([DvpExecution(dvp_item_id=i.id,execution_no=1,release_id=r.id,snapshot_id=s.id,result='PASS',actual_result='private'*1000),artifact(s)])
        db.commit();grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['artifact_count']==grown[0]['latest_execution_count']==108 and len(grown[1]['items'])==len(grown[2]['items'])==2
    assert len(initial[3])==len(grown[3]) and not any('storage_reference' in q or 'actual_result' in q for q in grown[3])
    assert not any(isinstance(obj,(SnapshotArtifact,DvpExecution)) for obj in db.identity_map.values())

def test_http_readonly_validation_and_unknown_filters(evidence,monkeypatch):
    from app import main
    db,r,s,*_=evidence;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            base='/api/v1/releases/application/id/'+str(r.id);assert client.get(base+'/evidence-summary').status_code==200
            for suffix in ['artifacts','executions']:
                path=base+'/evidence/'+suffix;assert client.get(path,params={'snapshot_id':str(s.id),'limit':1}).json()['total']==3
                for query in ['', '?snapshot_id=bad','?snapshot_id='+str(s.id)+'&limit=101','?snapshot_id='+str(s.id)+'&unexpected=1']:assert client.get(path+query).status_code==422
            response=client.post('/api/v1/releases/'+str(r.id)+'/create-snapshot',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()

def test_postgres_window_index_and_reversible_migration(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);r.release_type='APPLICATION';s=db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==r.id)).first();scr=db.scalars(select(SoftwareChangeRequest)).first()
        if scr is None:
            scr=SoftwareChangeRequest(request_no='PG-E',title='Evidence',source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=r.software_id);db.add(scr);db.flush()
        p=DvpPlan(change_request_id=scr.id,plan_no='PG-E',title='Evidence');db.add(p);db.flush();i=DvpItem(plan_id=p.id,item_no='DUP',title='Evidence',scope='SOFTWARE_TEST');db.add(i);db.flush()
        for n in [1,2]:db.add(DvpExecution(dvp_item_id=i.id,execution_no=n,release_id=r.id,snapshot_id=s.id,result='PASS'))
        db.commit();before=db.scalar(select(func.count()).select_from(AuditEvent))
        assert evidence_summary(r.id,EvidenceSelection(),db)['latest_execution_count']==1 and evidence_executions(r.id,page(s,limit=1),db)['items'][0]['execution_no']==2
        assert len(evidence_artifacts(r.id,page(s,limit=1),db)['items'])<=1 and db.scalar(select(func.count()).select_from(AuditEvent))==before
    name='ix_dvp_executions_release_snapshot_item'
    assert next(i for i in inspect(engine).get_indexes('dvp_executions') if i['name']==name)['column_names']==['release_id','snapshot_id','dvp_item_id','execution_no']
    command.downgrade(Config('alembic.ini'),'0017_deployment_actual_version');assert name not in {i['name'] for i in inspect(engine).get_indexes('dvp_executions')}
    command.upgrade(Config('alembic.ini'),'head')
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(DvpExecution))==2
