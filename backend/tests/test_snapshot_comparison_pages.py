"""Bounded SQL comparison parity, policy multisets, exact pins and growth."""
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
from app.api.snapshot_comparison_views import ComparisonPage, comparison_summary, comparison_files
from app.api.snapshot_views import SummarySelection
from app.api.snapshots import compare_snapshots
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import Artifact, Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.snapshot_comparison_reads import VALUE_FIELDS


def file(db,s,name='same.hex',source=None,**changes):
    values=dict(component_code='APP',filename=name,artifact_type='HEX',component_version='1',sha256='a'*64,classification='CONFIDENTIAL',distribution_level='EXTERNAL',ai_access_policy='DENY',storage_reference='private-path');values.update(changes)
    a=SnapshotArtifact(snapshot_id=s.id,source_artifact_id=source or uuid.uuid4(),**values);db.add(a);db.flush();return a


def rule(db,a,code='CUS',decision='ALLOW'):
    db.add(SnapshotArtifactDistributionRule(snapshot_artifact_id=a.id,recipient_type='CUSTOMER',purpose='PRODUCTION',recipient_code=code,decision=decision));db.flush()


def seed(db,r,source=None):
    old=ReleaseSnapshot(release_id=r.id,snapshot_no='BEFORE',snapshot_number=10,status='FROZEN',content_hash='x'*64,release_metadata_json={'version':'1','release_type':r.release_type})
    new=ReleaseSnapshot(release_id=r.id,snapshot_no='AFTER',snapshot_number=11,status='DRAFT',content_hash='x'*64,release_metadata_json={'version':'2','release_type':r.release_type})
    db.add_all([old,new]);db.flush()
    file(db,old,'removed.hex',source);file(db,new,'added.hex',source)
    file(db,old,'changed.hex',source);file(db,new,'changed.hex',source,sha256='b'*64)
    a=file(db,old,'same.hex',source);b=file(db,new,'same.hex',source);rule(db,a);rule(db,b)
    # same filename in another component is a distinct file identity.
    file(db,old,'same.hex',source,component_code='BOOT');file(db,new,'same.hex',source,component_code='BOOT')
    db.commit();return old,new


@pytest.fixture
def comparison(context):
    db,_,r,*_=context;old,new=seed(db,r);return db,r,old,new


def summary(db,a,b):return comparison_summary(a.snapshot_no,b.snapshot_no,SummarySelection(),db)
def page(db,a,b,**kw):return comparison_files(a.snapshot_no,b.snapshot_no,ComparisonPage(source_id=a.id,target_id=b.id,**kw),db)


def test_legacy_parity_counts_full_hash_metadata_and_reverse(comparison):
    db,r,a,b=comparison;legacy=compare_snapshots(a.snapshot_no,b.snapshot_no,db);result=summary(db,a,b)
    assert result['summary']==legacy['summary']=={'added':1,'removed':1,'modified':1,'unchanged':2}
    assert result['metadata_changes']==legacy['metadata_changes'] and result['content_hash_matches']
    assert result['source']['id']==str(a.id) and result['target']['id']==str(b.id)
    actual=page(db,a,b,show='all')['items']
    for row in actual:
        old=next(x for x in legacy['files'] if x['component_code']==row['component_code'] and x['filename']==row['filename'])
        assert {k:v for k,v in row.items() if k not in ['before','after']}=={k:v for k,v in old.items() if k not in ['before','after']}
        for side in ['before','after']:
            assert (row[side] is None)==(old[side] is None)
            if row[side]:
                assert {k:row[side][k] for k in VALUE_FIELDS}=={k:old[side][k] for k in VALUE_FIELDS}
                assert row[side]['rule_count']==len(old[side]['policy_rules']) and 'policy_rules' not in row[side]
    assert 'private-path' not in str(actual)
    reverse=summary(db,b,a);assert reverse['summary']==result['summary']
    assert next(x for x in page(db,b,a)['items'] if x['filename']=='added.hex')['change_type']=='removed'


@pytest.mark.parametrize('field,value',[('artifact_type','ELF'),('component_version',None),('sha256','c'*64),('classification','STRICTLY_CONFIDENTIAL'),('distribution_level','INTERNAL_ONLY'),('ai_access_policy','LOCAL_ONLY')])
def test_each_field_detected_independently_same_content_hash(comparison,field,value):
    db,r,a,b=comparison;row=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==b.id,SnapshotArtifact.filename=='same.hex',SnapshotArtifact.component_code=='APP'));setattr(row,field,value);db.commit()
    changed=next(x for x in page(db,a,b)['items'] if x['filename']=='same.hex')
    assert changed['changed_fields']==[field] and summary(db,a,b)['content_hash_matches']


def test_counted_rules_preserve_duplicates_null_empty_without_order_or_uuid_changes(comparison):
    db,r,a,b=comparison
    old=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==a.id,SnapshotArtifact.filename=='same.hex',SnapshotArtifact.component_code=='APP'))
    new=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==b.id,SnapshotArtifact.filename=='same.hex',SnapshotArtifact.component_code=='APP'))
    # Nullable recipient codes permit duplicate rows in PostgreSQL. Opposite order
    # and unrelated UUIDs must not make the same rule multiset a policy change.
    for code in [None,None,'']:rule(db,old,code)
    for code in ['',None,None]:rule(db,new,code)
    db.commit();assert summary(db,a,b)['summary']['unchanged']==2
    rule(db,new,None);db.commit();row=next(x for x in page(db,a,b)['items'] if x['filename']=='same.hex')
    assert row['changed_fields']==['policy_rules'] and row['before']['rule_count']==4 and row['after']['rule_count']==5
    # Equal counts but different NULL/empty contents must still differ.
    target=db.scalar(select(SnapshotArtifactDistributionRule).where(SnapshotArtifactDistributionRule.snapshot_artifact_id==new.id,SnapshotArtifactDistributionRule.recipient_code.is_(None)))
    db.delete(target);target=db.scalar(select(SnapshotArtifactDistributionRule).where(SnapshotArtifactDistributionRule.snapshot_artifact_id==new.id,SnapshotArtifactDistributionRule.recipient_code.is_(None)));target.recipient_code='OTHER';db.commit()
    row=next(x for x in page(db,a,b)['items'] if x['filename']=='same.hex');assert row['before']['rule_count']==row['after']['rule_count']==4 and row['changed_fields']==['policy_rules']


@pytest.mark.parametrize('show,total',[('changes',3),('all',5)])
def test_sql_filter_pagination_order_beyond_end(comparison,show,total):
    db,r,a,b=comparison;whole=page(db,a,b,show=show);assert whole['total']==total
    collected=[]
    for n in range(total):
        p=page(db,a,b,show=show,limit=1,offset=n);assert p['show']==show and p['total']==total and len(p['items'])==1
        assert p['next_offset']==(n+1 if n<total-1 else None);collected.extend(p['items'])
    assert collected==whole['items']
    end=page(db,a,b,show=show,offset=999);assert end['total']==total and end['items']==[] and end['next_offset'] is None


@pytest.mark.parametrize('side',['source','target'])
def test_duplicate_anywhere_rejected_before_pagination_or_changes_filter(comparison,side):
    db,r,a,b=comparison;file(db,a if side=='source' else b,'same.hex');db.commit()
    for fn in [lambda:summary(db,a,b),lambda:page(db,a,b,offset=999)]:
        with pytest.raises(HTTPException) as e:fn()
        assert e.value.status_code==409 and 'Ambiguous' in e.value.detail


def test_missing_cross_release_and_name_uuid_mismatch(comparison):
    db,r,a,b=comparison
    for sid,tid in [(uuid.uuid4(),b.id),(a.id,uuid.uuid4()),(b.id,a.id)]:
        with pytest.raises(HTTPException) as e:comparison_files(a.snapshot_no,b.snapshot_no,ComparisonPage(source_id=sid,target_id=tid),db)
        assert e.value.status_code==404
    with pytest.raises(HTTPException):comparison_summary('missing',b.snapshot_no,SummarySelection(),db)
    foreign=Release(software_id=r.software_id,release_type='STANDARD',version='foreign');db.add(foreign);db.flush();b.release_id=foreign.id;db.commit()
    for fn in [lambda:summary(db,a,b),lambda:page(db,a,b)]:
        with pytest.raises(HTTPException) as e:fn()
        assert e.value.status_code==409


def test_empty_self_comparison_and_no_source_artifact_dependency(comparison):
    db,r,a,b=comparison;result=summary(db,a,a);assert result['summary']=={'added':0,'removed':0,'modified':0,'unchanged':4}
    assert page(db,a,a)['total']==0 and page(db,a,a,show='all')['total']==4
    empty=ReleaseSnapshot(release_id=r.id,snapshot_no='EMPTY',snapshot_number=12,content_hash='z'*64);db.add(empty);db.commit()
    assert summary(db,empty,empty)['summary']==dict.fromkeys(['added','removed','modified','unchanged'],0)
    assert page(db,empty,empty)['items']==[]


def test_fixed_statement_shape_and_no_child_orm_on_growth(comparison):
    db,r,a,b=comparison;aid,bid=a.id,b.id;calls=[]
    def capture(_conn,_cursor,sql,*_):calls.append(sql.lower())
    def read():
        db.expunge_all();old,new=db.get(ReleaseSnapshot,aid),db.get(ReleaseSnapshot,bid);calls.clear()
        result=summary(db,old,new);p=page(db,old,new,show='all',limit=2)
        assert not any(isinstance(x,(SnapshotArtifact,SnapshotArtifactDistributionRule)) for x in db.identity_map.values())
        return result,p,list(calls)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        small=read()
        for n in range(60):
            for sid in [aid,bid]:
                row=file(db,db.get(ReleaseSnapshot,sid),f'growth-{n:03}.hex')
                for j in range(3):rule(db,row,str(j))
        db.commit();large=read()
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    assert large[0]['summary']['unchanged']==62 and large[1]['total']==65 and len(large[1]['items'])==2
    assert small[2]==large[2] and 'limit' in large[2][-1] and 'except' in large[2][-1]


@pytest.mark.parametrize('kw',[{'source_id':'bad'},{'target_id':'bad'},{'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'show':'bad'},{'unknown':1}])
def test_strict_page_filter(kw):
    with pytest.raises(ValidationError):ComparisonPage(**({'source_id':uuid.uuid4(),'target_id':uuid.uuid4()}|kw))


def test_http_queries_context_and_readonly(comparison,monkeypatch):
    from app import main
    db,r,a,b=comparison;aid,bid,rid=a.id,b.id,r.id;engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db=Session(engine);app.dependency_overrides[get_db]=lambda:route_db;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        with TestClient(app) as client:
            root='/api/v1/snapshots/BEFORE/comparison/AFTER'
            assert client.get(root+'/summary').json()['summary']['modified']==1
            assert client.get(root+'/summary?unknown=1').status_code==422
            assert client.get(root+'/files').status_code==422
            q=f'?source_id={aid}&target_id={bid}'
            assert client.get(root+'/files'+q).json()['total']==3
            assert client.get(root+'/files'+q+'&show=all&limit=1').json()['total']==5
            for more in ['&unknown=1','&show=bad','&limit=101','&offset=-1']:assert client.get(root+'/files'+q+more).status_code==422
            assert client.get(root+'/files'+f'?source_id={bid}&target_id={aid}').status_code==404
            result=client.post(f'/api/v1/releases/{rid}/create-snapshot',json={});assert result.status_code==403 and result.json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.pop(get_db,None);route_db.close();engine.dispose()


def test_real_postgresql_rule_multiset_and_newer_commit_pins_no_audit(pg):
    engine,ids=pg
    with Session(engine) as db:
        r=db.get(Release,ids['release']);source=db.scalar(select(Artifact.id));a,b=seed(db,r,source)
        before=db.scalar(select(func.count()).select_from(AuditEvent))
        old=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==a.id,SnapshotArtifact.filename=='same.hex',SnapshotArtifact.component_code=='APP'))
        new=db.scalar(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id==b.id,SnapshotArtifact.filename=='same.hex',SnapshotArtifact.component_code=='APP'))
        for code in [None,None,'']:rule(db,old,code)
        for code in ['',None,None]:rule(db,new,code)
        db.commit();assert summary(db,a,b)['summary']['unchanged']==2
        with Session(engine) as writer:
            writer.add(ReleaseSnapshot(release_id=r.id,snapshot_no='NEW-COMMIT',snapshot_number=12,content_hash='z'*64));writer.commit()
        assert page(db,a,b)['total']==3 and page(db,a,b,show='all')['total']==5
        rule(db,new,None);db.commit();assert summary(db,a,b)['summary']['modified']==2
        assert next(x for x in page(db,a,b)['items'] if x['filename']=='same.hex')['changed_fields']==['policy_rules']
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before
