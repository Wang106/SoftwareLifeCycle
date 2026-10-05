"""Exact Snapshot pages preserve public metadata and never substitute a parent."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_asr_policy_pages import policy, seed, artifact
from test_command_concurrency_postgres import pg
from app.api.asr_policy import RulePage
from app.api.snapshot_views import SummarySelection, snapshot_summary, snapshot_artifacts, snapshot_rules
from app.api.snapshots import snapshot_detail
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import Artifact, Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule


def summary(db,s):return snapshot_summary(s.snapshot_no,SummarySelection(),db)
def page(db,s,fn=snapshot_artifacts,**kw):return fn(s.snapshot_no,RulePage(snapshot_id=s.id,**kw),db)


@pytest.mark.parametrize('release_type',['STANDARD','APPLICATION'])
def test_summary_and_pages_preserve_legacy_public_fields(policy,release_type):
    db,r,s,rows,_=policy;r.release_type=release_type;db.commit()
    old=snapshot_detail(s.snapshot_no,db);new=summary(db,s)
    assert {k:v for k,v in new.items() if k not in ['artifact_count','rule_count','release_id']}=={k:v for k,v in old.items() if k!='artifacts'}
    assert new['artifact_count']==4 and new['rule_count']==4 and new['release_id']==str(r.id)
    byid={row['id']:row for row in page(db,s)['items']}
    for row in old['artifacts']:
        assert byid[row['id']]=={k:v for k,v in row.items() if k!='policy_rules'}|{'rule_count':len(row['policy_rules'])}
    assert 'private-location' not in str(new)+str(byid) and 'policy_rules' not in str(byid)
    assert any(row['distribution_level']=='INTERNAL_ONLY' and row['decision']=='ALLOW' for row in page(db,s,snapshot_rules)['items'])


@pytest.mark.parametrize('fn',[snapshot_artifacts,snapshot_rules])
def test_duplicate_order_pages_and_beyond_end_keep_totals(policy,fn):
    db,r,s,*_=policy;whole=page(db,s,fn);ids=[]
    for n in range(whole['total']):
        p=page(db,s,fn,limit=1,offset=n)
        assert p['snapshot_no']==s.snapshot_no and p['snapshot_id']==str(s.id) and p['release_id']==str(r.id)
        assert p['total']==4 and p['next_offset']==(n+1 if n<3 else None)
        ids.append(p['items'][0]['id'])
    assert ids==[row['id'] for row in whole['items']] and len(set(ids))==4
    assert page(db,s,fn,offset=100)['items']==[] and page(db,s,fn,offset=100)['total']==4


def test_selected_file_and_rules_exact_search_target(policy):
    db,r,s,rows,_=policy
    assert page(db,s,snapshot_artifact_id=rows[2].id)['items'][0]['id']==str(rows[2].id)
    assert page(db,s,snapshot_artifact_id=rows[2].id)['total']==1
    assert page(db,s,snapshot_rules,snapshot_artifact_id=rows[2].id)['total']==3
    assert page(db,s,snapshot_rules,snapshot_artifact_id=rows[0].id)['items']==[]
    for fn in [snapshot_artifacts,snapshot_rules]:
        with pytest.raises(HTTPException) as e:page(db,s,fn,snapshot_artifact_id=uuid.uuid4())
        assert e.value.status_code==404


@pytest.mark.parametrize('fn',[snapshot_artifacts,snapshot_rules])
def test_name_and_uuid_must_both_match_no_fallback(policy,fn):
    db,r,s,rows,old=policy
    for name,sid in [('missing',s.id),(s.snapshot_no,old.id),(old.snapshot_no,s.id),(s.snapshot_no,uuid.uuid4())]:
        with pytest.raises(HTTPException) as e:fn(name,RulePage(snapshot_id=sid),db)
        assert e.value.status_code==404
    with pytest.raises(HTTPException):snapshot_summary('missing',SummarySelection(),db)


def test_historical_pin_and_orphan_parent_identity(policy):
    db,r,s,rows,_=policy
    newer=ReleaseSnapshot(release_id=r.id,snapshot_no='NEXT',snapshot_number=11,content_hash='c'*64,status='DRAFT');db.add(newer);db.commit()
    assert not summary(db,s)['is_current_snapshot'] and page(db,s)['total']==4
    assert summary(db,newer)['artifact_count']==summary(db,newer)['rule_count']==0
    with pytest.raises(HTTPException):page(db,newer,snapshot_artifact_id=rows[2].id)
    db.delete(r);db.commit();result=summary(db,s)
    assert result['release'] is None and result['release_id']==str(s.release_id) and result['artifact_count']==4
    assert page(db,s)['total']==4


def test_fixed_sql_and_no_bulk_child_models_when_growing(policy):
    db,r,s,rows,_=policy;sid=s.id;calls=[]
    def capture(_conn,_cursor,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();calls.clear();snap=db.get(ReleaseSnapshot,sid);calls.clear()
        result=summary(db,snap);pages=[page(db,snap,fn,limit=2) for fn in [snapshot_artifacts,snapshot_rules]]
        assert not any(isinstance(x,(SnapshotArtifact,SnapshotArtifactDistributionRule)) for x in db.identity_map.values())
        return result,pages,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        for n in range(120):
            row=artifact(db.get(ReleaseSnapshot,sid));db.add(row);db.flush()
            for j in range(3):db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=row.id,recipient_type='CUSTOMER',purpose='PRODUCTION',recipient_code=f'{n}-{j}',decision='DENY'))
        db.commit();large=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert large[0]['artifact_count']==124 and large[0]['rule_count']==364
    assert all(len(p['items'])==2 for p in large[1]) and small[2]==large[2]
    assert 'limit' in large[2][-1]


def test_http_strict_queries_pin_readonly_and_retired_detail(policy,monkeypatch):
    from app import main
    db,r,s,rows,_=policy;rid,sid,name=r.id,s.id,s.snapshot_no
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root=f'/api/v1/snapshots/{name}'
            assert client.get(root).status_code == 410
            assert client.get(root+'/summary').json()['artifact_count']==4
            assert client.get(root+'/summary?unknown=1').status_code==422
            for name in ['artifacts','rules']:
                endpoint=root+'/'+name
                assert client.get(endpoint).status_code==422
                assert len(client.get(endpoint+f'?snapshot_id={sid}&limit=1').json()['items'])==1
                for q in ['&limit=0','&limit=101','&offset=-1','&offset=100001','&unknown=1','&snapshot_artifact_id=bad']:
                    assert client.get(endpoint+f'?snapshot_id={sid}'+q).status_code==422
                assert client.get(endpoint+f'?snapshot_id={uuid.uuid4()}').status_code==404
            result=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={})
            assert result.status_code==403 and result.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()


def test_real_postgresql_new_snapshot_commit_does_not_move_exact_page(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);source=db.scalar(select(Artifact.id));s,rows=seed(db,r,source)
        sid,rid=s.id,r.id;before=db.scalar(select(func.count()).select_from(AuditEvent))
        assert summary(db,s)['artifact_count']==4
        with Session(engine) as writer:
            writer.add(ReleaseSnapshot(release_id=rid,snapshot_no='NEW-COMMIT',snapshot_number=11,content_hash='c'*64));writer.commit()
        assert not summary(db,s)['is_current_snapshot']
        assert page(db,s)['total']==page(db,s,snapshot_rules)['total']==4
        seen=[page(db,s,snapshot_rules,limit=1,offset=n)['items'][0]['id'] for n in range(4)]
        assert len(set(seen))==4 and seen==[row['id'] for row in page(db,s,snapshot_rules)['items']]
        assert page(db,s,snapshot_artifact_id=rows[2].id)['total']==1
        assert page(db,s,snapshot_rules,snapshot_artifact_id=rows[2].id)['total']==3
        with pytest.raises(HTTPException):snapshot_artifacts('NEW-COMMIT',RulePage(snapshot_id=sid),db)
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
