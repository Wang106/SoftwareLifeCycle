"""Preserve readiness gates and live policy recording semantics with bounded reads."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_coverage_aggregates import seed as coverage_seed
from test_command_concurrency_postgres import pg
from app.api.asr_readiness import Selection, ExceptionPage, summary, exceptions
from app.api.dashboard import application_release_readiness, release_artifacts
from app.core.db import get_db
from app.main import app
from app.models.core import Artifact, ComponentDefinition, ReleaseComponent, Release
from app.models.policy import ArtifactDistributionRule
from app.models.governance import PolicyException
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpExecution
from app.models.audit import AuditEvent
from app.services.artifact_policy import ArtifactPolicyService, ArtifactPolicySummary


def seed_policy(db, release):
    definition=ComponentDefinition(code='READINESS-'+uuid.uuid4().hex,name='Readiness');db.add(definition);db.flush()
    component=ReleaseComponent(release_id=release.id,component_definition_id=definition.id,version='raw-version');db.add(component);db.flush()
    rows=[]
    for n,(sha,level) in enumerate([('a'*64,'INTERNAL_ONLY'),('','EXTERNAL'),(None,'CONTROLLED_EXTERNAL'),(' ',None),('b'*64,'EXTERNAL'),('','INTERNAL_ONLY')]):
        row=Artifact(release_component_id=component.id,filename=f'file-{n}',artifact_type='HEX',sha256=sha,distribution_level=level,controlled=False,storage_reference='private-location');db.add(row);rows.append(row)
    db.flush()
    for index,code,decision in [(0,None,'ALLOW'),(0,'internal','APPROVAL_REQUIRED'),(1,None,'DENY'),(1,None,'ALLOW'),(3,None,'APPROVAL_REQUIRED'),(4,None,'ALLOW'),(4,'exact','APPROVAL_REQUIRED')]:
        db.add(ArtifactDistributionRule(artifact_id=rows[index].id,recipient_type='CUSTOMER',purpose='PRODUCTION',recipient_code=code,decision=decision))
    db.commit();return rows


def legacy_policy(db,release_id):
    artifacts=ArtifactPolicyService(db).release_artifacts(release_id)
    ids=[a.id for a in artifacts]
    rules=db.scalars(select(ArtifactDistributionRule).where(ArtifactDistributionRule.artifact_id.in_(ids))).all() if ids else []
    sha=complete=eligible=approval=internal=0
    for a in artifacts:
        sha+=bool(a.sha256)
        if a.distribution_level=='INTERNAL_ONLY':internal+=1;complete+=1;continue
        selected=[r for r in rules if r.artifact_id==a.id]
        complete+=bool(selected);eligible+=any(r.decision=='ALLOW' for r in selected);approval+=any(r.decision=='APPROVAL_REQUIRED' for r in selected)
    return ArtifactPolicySummary(len(artifacts),sha,complete,eligible,approval,internal).as_dict()


def exception(db,snapshot,no='PEX',rule='VERIFICATION_CURRENT_SNAPSHOT_COMPLETE',status='APPROVED'):
    row=PolicyException(exception_no=no,snapshot_id=snapshot.id,rule_code=rule,status=status,scope='Verification',reason='Raw reason',compensating_control='Raw control');db.add(row);db.flush();return row

@pytest.fixture
def readiness(context):
    db,issue,r,s,scr=context;r.release_type='APPLICATION';db.commit();return db,issue,r,s,scr

@pytest.mark.parametrize('case',['mixed','empty','foreign'])
def test_sql_policy_matches_legacy_nullable_duplicate_and_empty(readiness,case):
    db,_,r,*_=readiness
    if case!='empty':seed_policy(db,r)
    target=r.id if case!='foreign' else uuid.uuid4()
    result=ArtifactPolicyService(db).summarize_release(target).as_dict()
    assert result==legacy_policy(db,target)
    if case=='mixed':assert result=={'artifact_total':6,'sha_complete':3,'sha_completeness':50,'policy_complete':5,'policy_completeness':83,'externally_eligible':2,'approval_required':2,'internal_only':2}
    else:assert result['artifact_total']==0 and result['sha_completeness']==result['policy_completeness']==100

@pytest.mark.parametrize('case',['plain','exception','draft','foreign_exception','hard_fail','live_declaration'])
def test_bounded_gates_equal_legacy_without_exception_arrays(readiness,case):
    db,issue,r,s,scr=readiness;items,_=coverage_seed(db,r,s,scr,issue)
    db.execute(delete(DvpExecution).where(DvpExecution.dvp_item_id==items[-1].id))
    rows=seed_policy(db,r)
    for row in rows:row.sha256='c'*64;row.distribution_level='INTERNAL_ONLY'
    if case in ['exception','hard_fail','live_declaration']:exception(db,s)
    if case=='draft':s.status='DRAFT';exception(db,s)
    if case=='foreign_exception':
        old=ReleaseSnapshot(release_id=r.id,snapshot_no='OLD',snapshot_number=0,content_hash='0'*64,status='FROZEN');db.add(old);db.flush();exception(db,old)
    if case=='hard_fail':rows[0].sha256=''
    if case=='live_declaration':rows[-1].distribution_level='EXTERNAL'  # Existing live declarations, not frozen Snapshot policy.
    db.commit();old=application_release_readiness(r.id,db);result=summary(r.id,Selection(),db)
    for key in ['overall','approval_eligible','coverage','artifact_policy','rules']:assert result[key]==old[key],key
    assert 'exceptions' not in result and result['exception_total']==len(old['exceptions']) and len(result['rules'])==8
    verification=next(row for row in result['rules'] if row['group']=='Verification')
    assert verification['raw']=='FAIL' and verification['effective']==('EXCEPTION_GRANTED' if case in ['exception','hard_fail','live_declaration','draft'] else 'FAIL')
    assert result['overall']==('READY' if case=='exception' else 'NOT_READY')


def test_exception_pages_exact_snapshot_status_order_and_all_public_fields(readiness):
    db,_,r,s,*_=readiness
    for n in range(3):exception(db,s,no=f'PEX-{n}',rule='OTHER')
    exception(db,s,no='DRAFT',status='DRAFT');old=ReleaseSnapshot(release_id=r.id,snapshot_no='OLD',snapshot_number=0,content_hash='0'*64);db.add(old);db.flush();exception(db,old,no='OLD');db.commit()
    result=summary(r.id,Selection(),db);assert result['exception_total']==3
    pages=[exceptions(r.id,ExceptionPage(snapshot_id=s.id,limit=1,offset=n),db) for n in range(3)]
    assert [p['items'][0]['exception_no'] for p in pages]==['PEX-0','PEX-1','PEX-2']
    assert all(p['total']==3 and p['snapshot_id']==str(s.id) for p in pages)
    assert pages[0]['next_offset']==1 and pages[-1]['next_offset'] is None
    row=pages[0]['items'][0];assert row['reason']=='Raw reason' and row['compensating_control']=='Raw control' and row['snapshot_no']==s.snapshot_no
    assert exceptions(r.id,ExceptionPage(snapshot_id=s.id,offset=100),db)['items']==[]
    assert exceptions(r.id,ExceptionPage(snapshot_id=old.id),db)['total']==1

@pytest.mark.parametrize('case',['none','missing','foreign','standard','stale'])
def test_empty_invalid_scope_and_changed_selection(readiness,case):
    db,_,r,s,*_=readiness
    if case=='none':
        page=exceptions(r.id,ExceptionPage(snapshot_id='none'),db);assert page['items']==[] and page['total']==0
        with pytest.raises(HTTPException) as e:summary(r.id,Selection(snapshot_id='none'),db)
        assert e.value.status_code==409;return
    rid,filters=r.id,Selection(snapshot_id=s.id)
    if case=='missing':rid=uuid.uuid4()
    elif case=='foreign':s.release_id=uuid.uuid4();db.commit()
    elif case=='standard':r.release_type='STANDARD';db.commit()
    else:db.add(ReleaseSnapshot(release_id=r.id,snapshot_no='NEW',snapshot_number=9,content_hash='9'*64));db.commit()
    with pytest.raises(HTTPException) as e:summary(rid,filters,db)
    assert e.value.status_code==(409 if case=='stale' else 404)

@pytest.mark.parametrize('kw',[{'snapshot_id':'bad'},{'extra':1}])
def test_strict_selection(kw):
    with pytest.raises(ValidationError):Selection(**kw)

@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'extra':1}])
def test_strict_pages(kw):
    with pytest.raises(ValidationError):ExceptionPage(**({'snapshot_id':'none'}|kw))


def test_growing_policy_and_exceptions_fixed_sql_no_child_orm(readiness):
    db,_,r,s,*_=readiness;rows=seed_policy(db,r);rid,sid,cid=r.id,s.id,rows[0].release_component_id;calls=[]
    def capture(_c,_cur,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();calls.clear();result=summary(rid,Selection(),db);page=exceptions(rid,ExceptionPage(snapshot_id=sid,limit=2),db)
        assert not any(isinstance(row,(Artifact,ArtifactDistributionRule,PolicyException)) for row in db.identity_map.values())
        return result,page,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        for n in range(130):
            db.add(Artifact(release_component_id=cid,filename=f'GROW-{n}',artifact_type='HEX',storage_reference='private',sha256='a'*64,distribution_level='INTERNAL_ONLY'))
            exception(db,db.get(ReleaseSnapshot,sid),no=f'GROW-{n}',rule='OTHER')
        db.commit();grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['artifact_policy']['artifact_total']==136 and grown[0]['exception_total']==130
    assert len(grown[1]['items'])==2 and small[2]==grown[2]


def test_http_strict_current_summary_pages_and_readonly(readiness,monkeypatch):
    from app import main
    db,_,r,s,*_=readiness;exception(db,s);db.commit();rid,sid=r.id,s.id
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root=f'/api/v1/releases/application/id/{rid}/readiness'
            assert client.get(root+'/summary').json()['exception_total']==1
            assert len(client.get(root+f'/exceptions?snapshot_id={sid}&limit=1').json()['items'])==1
            for query in ['?unknown=1','?snapshot_id=bad']:assert client.get(root+'/summary'+query).status_code==422
            assert client.get(root+'/summary?snapshot_id=none').status_code==409
            assert client.get(root+'/exceptions').status_code==422
            for query in ['&limit=101','&offset=-1','&unknown=1']:assert client.get(root+f'/exceptions?snapshot_id={sid}'+query).status_code==422
            response=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()

@pytest.mark.parametrize('case',['policy','exceptions','second_commit','empty'])
def test_real_postgresql_parity_and_pinned_readiness(pg,case):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);r.release_type='APPLICATION';s=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==r.id));db.commit()
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        if case=='policy':
            seed_policy(db,r);assert ArtifactPolicyService(db).summarize_release(r.id).as_dict()==legacy_policy(db,r.id)
            # Compatibility artifacts still return full arrays/recorded policy shape.
            result=release_artifacts(r.version,db);assert result['summary']==legacy_policy(db,r.id)
        elif case=='empty':
            empty=Release(software_id=r.software_id,release_type='APPLICATION',version='empty');db.add(empty);db.commit()
            result=summary(empty.id,Selection(snapshot_id='none'),db);assert result['snapshot'] is None and result['exception_total']==0 and result['overall']=='NOT_READY'
        else:
            for n in range(3):exception(db,s,no=f'PG-{n}')
            db.commit();result=summary(r.id,Selection(),db);assert result['exception_total']==3
            for key in ['overall','approval_eligible','coverage','artifact_policy','rules']:assert result[key]==application_release_readiness(r.id,db)[key]
            pages=[exceptions(r.id,ExceptionPage(snapshot_id=s.id,limit=1,offset=n),db) for n in range(3)]
            assert len({p['items'][0]['id'] for p in pages})==3 and all(p['total']==3 for p in pages)
            if case=='second_commit':
                with Session(engine) as writer:writer.add(ReleaseSnapshot(release_id=r.id,snapshot_no='PG-NEW',snapshot_number=99,content_hash='9'*64));writer.commit()
                with pytest.raises(HTTPException) as e:summary(r.id,Selection(snapshot_id=s.id),db)
                assert e.value.status_code==409 and exceptions(r.id,ExceptionPage(snapshot_id=s.id),db)['total']==3
                assert summary(r.id,Selection(),db)['snapshot']['snapshot_no']=='PG-NEW'
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
