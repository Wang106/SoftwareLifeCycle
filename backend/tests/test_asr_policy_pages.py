"""Pinned frozen policy counts, bounded rule growth and exact artifact selection."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.asr_evidence import EvidencePage, EvidenceSelection
from app.api.asr_policy import RulePage, policy_summary, policy_artifacts, policy_rules
from app.api.dashboard import application_snapshot_policy
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import Artifact, Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule


def artifact(snapshot,source=None,**kw):
    return SnapshotArtifact(snapshot_id=snapshot.id,source_artifact_id=source or uuid.uuid4(),component_code='APP',filename='same.hex',artifact_type='HEX',sha256=kw.pop('sha256','a'*64),classification='CONFIDENTIAL',distribution_level=kw.pop('distribution_level','EXTERNAL'),ai_access_policy='DENY',storage_reference='private-location',**kw)


def seed(db,release,source=None):
    release.release_type='APPLICATION'
    s=ReleaseSnapshot(release_id=release.id,snapshot_no='POLICY-'+uuid.uuid4().hex[:10],snapshot_number=10,content_hash='b'*64,status='DRAFT')
    db.add(s);db.flush()
    rows=[artifact(s,source,sha256=sha,distribution_level=level) for sha,level in [('a'*64,'EXTERNAL'),('','INTERNAL_ONLY'),(' ','EXTERNAL'),('','INTERNAL_ONLY')]]
    db.add_all(rows);db.flush()
    for row,recipient,code,decision in [(rows[2],'CUSTOMER',None,'DENY'),(rows[2],'CUSTOMER',None,'DENY'),(rows[2],'CUSTOMER','','ALLOW'),(rows[3],'SUPPLIER','RAW','ALLOW')]:
        db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=row.id,recipient_type=recipient,purpose='PRODUCTION',recipient_code=code,decision=decision))
    db.commit();return s,rows


@pytest.fixture
def policy(context):
    db,_,release,old,*_=context;s,rows=seed(db,release);return db,release,s,rows,old


def page(s,**kw):return EvidencePage(snapshot_id=s.id,**kw)
def rulepage(s,**kw):return RulePage(snapshot_id=s.id,**kw)


def test_legacy_recording_counts_not_permission_or_hash_validation(policy):
    db,r,s,rows,_=policy;legacy=application_snapshot_policy(r.id,db);summary=policy_summary(r.id,EvidenceSelection(),db)
    assert summary['snapshot']=={'id':str(s.id),'snapshot_no':s.snapshot_no,'status':'DRAFT','content_hash':s.content_hash,'is_current_snapshot':True}
    assert summary['artifact_count']==len(legacy['artifacts'])==4
    assert summary['sha_recorded_count']==sum(bool(row['sha256']) for row in legacy['artifacts'])==2
    assert summary['policy_recorded_count']==sum(row['distribution_level']=='INTERNAL_ONLY' or bool(row['policy_rules']) for row in legacy['artifacts'])==3
    assert summary['rule_count']==4
    projected=policy_artifacts(r.id,page(s),db)['items']
    byid={row['id']:row for row in projected}
    for row in legacy['artifacts']:
        expected={k:v for k,v in row.items() if k!='policy_rules'}|{'rule_count':len(row['policy_rules'])}
        assert byid[row['id']]==expected
    assert all('policy_rules' not in row and 'private' not in str(row) for row in projected)
    rules=policy_rules(r.id,rulepage(s),db)['items'];assert len(rules)==4
    assert any(row['distribution_level']=='INTERNAL_ONLY' and row['decision']=='ALLOW' for row in rules)


@pytest.mark.parametrize('fn',[policy_artifacts,policy_rules])
def test_stable_duplicate_null_rule_order_and_beyond_end(policy,fn):
    db,r,s,*_=policy;filters=page if fn==policy_artifacts else rulepage
    whole=fn(r.id,filters(s),db);ids=[]
    for offset in range(whole['total']):
        p=fn(r.id,filters(s,limit=1,offset=offset),db)
        assert p['release_id']==str(r.id) and p['snapshot_id']==str(s.id) and p['total']==4
        assert p['next_offset']==(offset+1 if offset<3 else None)
        ids.append(p['items'][0]['id'])
    assert ids==[row['id'] for row in whole['items']] and len(set(ids))==4
    p=fn(r.id,filters(s,offset=100),db);assert p['total']==4 and p['items']==[] and p['next_offset'] is None


def test_rule_filter_exact_artifact_uuid_includes_no_rule_artifact(policy):
    db,r,s,rows,_=policy
    assert policy_rules(r.id,rulepage(s,snapshot_artifact_id=rows[2].id),db)['total']==3
    empty=policy_rules(r.id,rulepage(s,snapshot_artifact_id=rows[0].id),db)
    assert empty['total']==0 and empty['items']==[] and empty['snapshot_artifact_id']==str(rows[0].id)
    with pytest.raises(HTTPException) as e:policy_rules(r.id,rulepage(s,snapshot_artifact_id=uuid.uuid4()),db)
    assert e.value.status_code==404


def test_new_snapshot_never_moves_selected_counts_pages_or_artifact_filter(policy):
    db,r,s,rows,_=policy;new=ReleaseSnapshot(release_id=r.id,snapshot_no='NEWER',snapshot_number=11,content_hash='c'*64)
    db.add(new);db.flush();db.add(artifact(new));db.commit()
    assert policy_summary(r.id,EvidenceSelection(),db)['artifact_count']==1
    assert policy_summary(r.id,EvidenceSelection(snapshot_id=s.id),db)['artifact_count']==4
    assert not policy_summary(r.id,EvidenceSelection(snapshot_id=s.id),db)['snapshot']['is_current_snapshot']
    assert policy_artifacts(r.id,page(s),db)['total']==policy_rules(r.id,rulepage(s),db)['total']==4
    with pytest.raises(HTTPException) as e:policy_rules(r.id,rulepage(new,snapshot_artifact_id=rows[2].id),db)
    assert e.value.status_code==404


@pytest.mark.parametrize('case',['missing_release','standard','missing_snapshot','foreign_snapshot'])
def test_exact_release_snapshot_rejection(policy,case):
    db,r,s,*_=policy;rid=r.id;sid=s.id
    if case=='missing_release':rid=uuid.uuid4()
    elif case=='standard':r.release_type='STANDARD';db.commit()
    elif case=='missing_snapshot':sid=uuid.uuid4()
    else:
        other=Release(software_id=uuid.uuid4(),release_type='APPLICATION',version=r.version);db.add(other);db.commit();rid=other.id
    for fn,q in [(policy_summary,EvidenceSelection(snapshot_id=sid)),(policy_artifacts,EvidencePage(snapshot_id=sid)),(policy_rules,RulePage(snapshot_id=sid))]:
        with pytest.raises(HTTPException) as e:fn(rid,q,db)
        assert e.value.status_code==404


def test_no_snapshot_empty_snapshot_and_orphan_rule_exclusion(policy):
    db,r,s,*_=policy;empty=Release(software_id=r.software_id,release_type='APPLICATION',version='empty');db.add(empty);db.commit()
    assert policy_summary(empty.id,EvidenceSelection(),db)=={'release_id':str(empty.id),'snapshot':None,'artifact_count':0,'sha_recorded_count':0,'policy_recorded_count':0,'rule_count':0}
    snap=ReleaseSnapshot(release_id=empty.id,snapshot_no='EMPTY',snapshot_number=1,content_hash='d'*64);db.add(snap)
    db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=uuid.uuid4(),recipient_type='CUSTOMER',purpose='PRODUCTION',decision='ALLOW'));db.commit()
    summary=policy_summary(empty.id,EvidenceSelection(),db);assert summary['artifact_count']==summary['sha_recorded_count']==summary['policy_recorded_count']==summary['rule_count']==0
    assert policy_artifacts(empty.id,page(snap),db)['items']==policy_rules(empty.id,rulepage(snap),db)['items']==[]
    assert policy_summary(r.id,EvidenceSelection(),db)['rule_count']==4


@pytest.mark.parametrize('kw',[{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'snapshot_id':'bad'},{'snapshot_artifact_id':'bad'},{'unknown':1}])
def test_strict_rule_filters(kw):
    with pytest.raises(ValidationError):RulePage(**({'snapshot_id':uuid.uuid4()}|kw))


def test_growth_rules_and_artifacts_fixed_sql_no_child_orm(policy):
    db,r,s,rows,_=policy;rid,sid=r.id,s.id;calls=[]
    def capture(_conn,_cursor,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();calls.clear();summary=policy_summary(rid,EvidenceSelection(snapshot_id=sid),db)
        pages=[policy_artifacts(rid,EvidencePage(snapshot_id=sid,limit=2),db),policy_rules(rid,RulePage(snapshot_id=sid,limit=2),db)]
        assert not any(isinstance(x,(SnapshotArtifact,SnapshotArtifactDistributionRule)) for x in db.identity_map.values())
        return summary,pages,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        for n in range(120):
            row=artifact(db.get(ReleaseSnapshot,sid));db.add(row);db.flush()
            for j in range(3):db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=row.id,recipient_type='CUSTOMER',purpose='PRODUCTION',recipient_code=f'{n}-{j}',decision='DENY'))
        db.commit();grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert grown[0]['artifact_count']==124 and grown[0]['policy_recorded_count']==123 and grown[0]['rule_count']==364
    assert all(len(p['items'])==2 for p in grown[1]) and small[2]==grown[2] and 'limit' in grown[2][-1]


def test_http_strict_pinned_selection_and_readonly(policy,monkeypatch):
    from app import main
    db,r,s,rows,_=policy;rid,sid,aid=r.id,s.id,rows[2].id;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root=f'/api/v1/releases/application/id/{rid}/snapshot-policy'
            assert client.get(root+'/summary').json()['rule_count']==4
            for q in ['?unknown=1','?snapshot_id=bad']:assert client.get(root+'/summary'+q).status_code==422
            for name in ['artifacts','rules']:
                assert client.get(root+'/'+name).status_code==422
                assert len(client.get(root+'/'+name+f'?snapshot_id={sid}&limit=1').json()['items'])==1
                for q in ['&limit=101','&offset=-1','&unknown=1']:assert client.get(root+'/'+name+f'?snapshot_id={sid}'+q).status_code==422
            assert client.get(root+f'/rules?snapshot_id={sid}&snapshot_artifact_id={aid}').json()['total']==3
            assert client.get(root+f'/rules?snapshot_id={sid}&snapshot_artifact_id={uuid.uuid4()}').status_code==404
            response=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={});assert response.status_code==403 and response.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()


def test_real_postgresql_null_rule_order_recording_counts_and_no_audit_write(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);source=db.scalar(select(Artifact.id));s,rows=seed(db,r,source)
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        summary=policy_summary(r.id,EvidenceSelection(),db);assert summary['artifact_count']==summary['rule_count']==4 and summary['policy_recorded_count']==3 and summary['sha_recorded_count']==2
        ids_seen=[policy_rules(r.id,rulepage(s,limit=1,offset=n),db)['items'][0]['id'] for n in range(4)]
        assert len(set(ids_seen))==4 and ids_seen==[row['id'] for row in policy_rules(r.id,rulepage(s),db)['items']]
        assert policy_rules(r.id,rulepage(s,snapshot_artifact_id=rows[2].id),db)['total']==3
        old=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==r.id,ReleaseSnapshot.id!=s.id))
        with pytest.raises(HTTPException):policy_rules(r.id,rulepage(old,snapshot_artifact_id=rows[2].id),db)
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
