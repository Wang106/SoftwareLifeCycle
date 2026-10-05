import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import event,func,select
from sqlalchemy.orm import Session
from test_impact_assessments import context
from test_change_issue_catalog import http
from test_command_concurrency_postgres import pg
from app.api.issue_views import Empty,Pages,SnapshotSelection,EvidencePages,summary,changes_page,candidates_page,assessments_page,evidence_summary,components_page,verification_page
from app.api.dashboard import get_issue
from app.api.impact import issue_impact,impact_evidence,assessment_history
from app.models.change import IssueChangeRequestRelation,SoftwareChangeRequest
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot,SnapshotArtifact
from app.models.testing import DvpPlan,DvpItem,IssueDvpItem,DvpExecution
from app.models.impact import IssueImpactAssessment
from app.models.audit import AuditEvent


def evidence(db,issue,release,snapshot,scr,count=3):
    plan=DvpPlan(change_request_id=scr.id,plan_no=str(uuid.uuid4()),title='Plan');db.add(plan);db.flush();items=[]
    for n in range(count):
        item=DvpItem(plan_id=plan.id,item_no=str(n),title='Original test title',scope='SOFTWARE_TEST');db.add(item);db.flush();items.append(item.id)
        db.add_all([IssueDvpItem(issue_id=issue.id,dvp_item_id=item.id),DvpExecution(dvp_item_id=item.id,execution_no=1,release_id=release.id,snapshot_id=snapshot.id,result='PASS',actual_result='Original observation')])
        db.add(SnapshotArtifact(snapshot_id=snapshot.id,source_artifact_id=uuid.uuid4(),component_code='SAME',component_version=None if n%2 else '',filename=str(n),artifact_type='BIN',sha256='a'*64,classification='PUBLIC',distribution_level='PUBLIC',ai_access_policy='DENY',storage_reference='private-path'))
    db.add(IssueImpactAssessment(id=uuid.uuid4(),issue_id=issue.id,release_id=release.id,snapshot_id=snapshot.id,decision='NEEDS_REVIEW',reason='Original reason',actor_name='Reviewer'));db.commit();return items

def pages(data,**kw):return Pages(issue_id=data['id'],**kw)
def epages(data,**kw):return EvidencePages(issue_id=data['issue_id'],snapshot_id=data['snapshot_id'],**kw)

def test_parent_relations_candidates_history_parity(context):
    db,issue,release,snapshot,scr=context;evidence(db,issue,release,snapshot,scr)
    db.add(IssueChangeRequestRelation(issue_id=issue.id,change_request_id=scr.id,relation_type='RELATED'));db.commit()
    new=summary(issue.issue_no,Empty(),db);old=get_issue(issue.issue_no,db)
    keys=['id','issue_no','title','scope','severity','status','description'];assert {k:new[k] for k in keys}=={k:old[k] for k in keys}
    assert (new['linked_count'],new['candidate_count'],new['assessment_count'])==(2,1,1)
    assert {r['relation_type'] for r in changes_page(issue.issue_no,pages(new),db)['items']}=={'FIXES','RELATED'}
    candidate=candidates_page(issue.issue_no,pages(new),db)['items'][0];legacy=issue_impact(issue.issue_no,db)['candidate_releases'][0]
    keys=['id','release_type','version','status','deployment_count','batch_count'];assert {k:candidate[k] for k in keys}=={k:legacy[k] for k in keys}
    assert candidate['snapshot_id']==legacy['snapshot']['id'] and candidate['decision']==legacy['assessment']['decision']
    assert assessments_page(issue.issue_no,pages(new),db)['items'][0]['reason']==assessment_history(issue.issue_no,50,db)['items'][0]['reason']

def test_exact_frozen_evidence_parity_and_latest_failure(context):
    db,issue,release,snapshot,scr=context;items=evidence(db,issue,release,snapshot,scr)
    db.add(DvpExecution(dvp_item_id=items[0],execution_no=2,release_id=release.id,snapshot_id=snapshot.id,result='FAIL',actual_result='Latest failure'));db.commit()
    new=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db);old=impact_evidence(issue.issue_no,release.id,db)
    assert new['snapshot']['id']==old['snapshot']['id'] and new['component_count']==1 and new['verification_count']==3
    rows=components_page(issue.issue_no,release.id,epages(new),db)['items'];assert rows==old['frozen_components'] and all('storage_reference' not in row for row in rows)
    rows=verification_page(issue.issue_no,release.id,epages(new),db)['items'];expected={r['id']:r for r in old['verification']}
    for row in rows:
        exe=expected[row['id']]['execution'];assert (row['execution_no'],row['result'],row['actual_result'])==(exe['execution_no'],exe['result'],exe['actual_result'])
    assert new['assessment']['reason']=='Original reason'

def test_historical_pin_new_snapshot_and_stale_none(context):
    db,issue,release,snapshot,scr=context;evidence(db,issue,release,snapshot,scr)
    pinned=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)
    empty=Release(software_id=release.software_id,release_type='APPLICATION',version='EMPTY');db.add(empty);db.commit()
    missing=evidence_summary(issue.issue_no,empty.id,SnapshotSelection(),db)
    assert missing['snapshot_id']=='none' and missing['verification_count']==3 and missing['component_count']==0
    for rel,num,no in [(release,2,'NEW'),(empty,1,'FIRST')]:db.add(ReleaseSnapshot(release_id=rel.id,snapshot_number=num,snapshot_no=no,content_hash='b'*64,status='FROZEN'))
    db.commit()
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(snapshot_id=snapshot.id),db)['snapshot_id']==str(snapshot.id)
    assert verification_page(issue.issue_no,release.id,epages(pinned),db)['items'][0]['result']=='PASS'
    with pytest.raises(HTTPException) as error:components_page(issue.issue_no,empty.id,epages(missing),db)
    assert error.value.status_code==409
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)['assessment'] is None

def test_full_candidates_beyond_200_and_direct_selection(context):
    db,issue,release,_,scr=context
    for n in range(205):db.add(Release(software_id=release.software_id,release_type='APPLICATION',version=str(n)))
    db.commit();data=summary(issue.issue_no,Empty(),db);assert data['candidate_count']==206
    page=candidates_page(issue.issue_no,pages(data,limit=1,offset=205),db);assert page['total']==206 and len(page['items'])==1
    assert evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)['release_id']==str(release.id)

def test_history_missing_metadata_retains_record(context):
    db,issue,_,_,_=context
    missing=IssueImpactAssessment(id=uuid.uuid4(),issue_id=issue.id,release_id=uuid.uuid4(),snapshot_id=uuid.uuid4(),decision='AFFECTED',reason='Historical record',actor_name='Reviewer');db.add(missing);db.commit()
    data=summary(issue.issue_no,Empty(),db);row=assessments_page(issue.issue_no,pages(data),db)['items'][0]
    assert row['release_version'] is row['snapshot_no'] is None and row['release_id']==str(missing.release_id)

@pytest.mark.parametrize('endpoint',['changes','candidates','assessments'])
def test_beyond_end_exact_issue_pin(context,endpoint):
    db,issue,*_=context;data=summary(issue.issue_no,Empty(),db);fn={'changes':changes_page,'candidates':candidates_page,'assessments':assessments_page}[endpoint]
    page=fn(issue.issue_no,pages(data,limit=1,offset=999),db);assert page['items']==[] and page['next_offset'] is None
    with pytest.raises(HTTPException) as error:fn(issue.issue_no,Pages(issue_id=uuid.uuid4()),db)
    assert error.value.status_code==404

@pytest.mark.parametrize('endpoint',['changes','candidates','assessments'])
def test_http_strict_queries(http,context,endpoint):
    issue=context[1];base='/api/v1/issue-views/'+issue.issue_no+'/'+endpoint;pin='issue_id='+str(issue.id)
    assert http.get(base+'?'+pin+'&limit=1').status_code==200
    for q in ['limit=101','limit=0','offset=-1','offset=100001','unknown=1','limit=bad']:assert http.get(base+'?'+pin+'&'+q).status_code==422
    assert http.get(base).status_code==422

def test_http_evidence_and_read_only(http,context,monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'read_only_mode',True)
    issue,release,snapshot=context[1:4];base='/api/v1/issue-views/'+issue.issue_no+'/impact/'+str(release.id)
    assert http.get(base+'/summary?unknown=1').status_code==422
    pin='issue_id='+str(issue.id)+'&snapshot_id='+str(snapshot.id)
    for endpoint in ['components','verification']:
        assert http.get(base+'/'+endpoint+'?'+pin+'&limit=1').status_code==200
        assert http.get(base+'/'+endpoint+'?issue_id='+str(issue.id)).status_code==422
        assert http.get(base+'/'+endpoint+'?'+pin+'&offset=-1').status_code==422
    assert http.post('/api/v1/deployments',json={}).status_code==403

def test_fixed_scalar_growth_no_orm(context):
    db,issue,release,snapshot,scr=context;evidence(db,issue,release,snapshot,scr,1)
    number=issue.issue_no;issue_id=issue.id;release_id=release.id;snapshot_id=snapshot.id;software_id=scr.software_id;plan_id=db.scalar(select(DvpItem.plan_id));queries=[]
    def capture(conn,cursor,statement,parameters,ctx,executemany):queries.append(statement)
    event.listen(db.bind,'before_cursor_execute',capture)
    def probe():
        db.expunge_all();queries.clear();data=summary(number,Empty(),db);ev=evidence_summary(number,release_id,SnapshotSelection(snapshot_id=snapshot_id),db)
        for fn in [changes_page,candidates_page,assessments_page]:assert len(fn(number,pages(data,limit=1),db)['items'])<=1
        for fn in [components_page,verification_page]:assert len(fn(number,release_id,epages(ev,limit=1),db)['items'])<=1
        assert not db.identity_map;return data,list(queries)
    try:
        _,before=probe()
        for n in range(120):
            db.add(Release(software_id=software_id,release_type='STANDARD',version=f'GROW-{n}'))
            db.add(IssueImpactAssessment(id=uuid.uuid4(),issue_id=issue_id,release_id=release_id,snapshot_id=snapshot_id,decision='NEEDS_REVIEW',reason='Reason',actor_name='Reviewer'))
            item=DvpItem(plan_id=plan_id,item_no=f'GROW-{n}',title='Test',scope='CUSTOMER_TEST');db.add(item);db.flush();db.add(IssueDvpItem(issue_id=issue_id,dvp_item_id=item.id))
            db.add(SnapshotArtifact(snapshot_id=snapshot_id,source_artifact_id=uuid.uuid4(),component_code=f'GROW-{n}',component_version='1',filename=str(n),artifact_type='BIN',sha256='a'*64,classification='PUBLIC',distribution_level='PUBLIC',ai_access_policy='DENY',storage_reference='private'))
        db.commit();data,after=probe();assert before==after and data['candidate_count']==data['assessment_count']==121
    finally:event.remove(db.bind,'before_cursor_execute',capture)

def test_postgres_pages_and_no_audit_write(pg):
    from app.models.change import Issue
    engine,ids=pg
    with Session(engine) as db:
        release=db.get(Release,ids['release']);issue=Issue(issue_no='PG-ISS',title='Issue',scope='STANDARD',severity='HIGH');scr=SoftwareChangeRequest(request_no='PG-ISS-SCR',title='SCR',software_id=release.software_id,source='INTERNAL',scope='STANDARD',change_type='FIX');db.add_all([issue,scr]);db.flush();db.add(IssueChangeRequestRelation(issue_id=issue.id,change_request_id=scr.id,relation_type='FIXES'))
        for n in range(205):db.add(Release(software_id=release.software_id,release_type='APPLICATION',version=str(n)))
        db.commit();before=db.scalar(select(func.count()).select_from(AuditEvent));data=summary(issue.issue_no,Empty(),db);assert data['candidate_count']==206
        assert len(candidates_page(issue.issue_no,pages(data,limit=1,offset=205),db)['items'])==1
        snapshot=db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id==release.id))
        plan=DvpPlan(change_request_id=scr.id,plan_no='PG-VERIFICATION',title='Plan');db.add(plan);db.flush()
        item=DvpItem(plan_id=plan.id,item_no='SAME',title='Test',scope='SOFTWARE_TEST');db.add(item);db.flush()
        db.add(IssueDvpItem(issue_id=issue.id,dvp_item_id=item.id))
        for number,result in [(1,'PASS'),(2,'FAIL')]:db.add(DvpExecution(dvp_item_id=item.id,execution_no=number,release_id=release.id,snapshot_id=snapshot.id,result=result))
        db.commit();ev=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)
        assert ev['snapshot_id']==str(snapshot.id)
        assert verification_page(issue.issue_no,release.id,epages(ev),db)['items'][0]['result']=='FAIL'
        assert components_page(issue.issue_no,release.id,epages(ev,limit=1),db)['total']==ev['component_count']
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before

@pytest.mark.parametrize('endpoint',['components','verification'])
def test_foreign_evidence_context_and_beyond_end(context,endpoint):
    db,issue,release,snapshot,scr=context;evidence(db,issue,release,snapshot,scr)
    data=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db);fn=components_page if endpoint=='components' else verification_page
    page=fn(issue.issue_no,release.id,epages(data,limit=1,offset=999),db);assert page['total']>0 and page['items']==[]
    for change in [{'issue_id':uuid.uuid4()},{'snapshot_id':uuid.uuid4()}]:
        pin=epages(data).model_copy(update=change)
        with pytest.raises(HTTPException) as error:fn(issue.issue_no,release.id,pin,db)
        assert error.value.status_code==(404 if 'issue_id' in change else 409)


def test_latest_exact_context_excludes_other_release_and_snapshot(context):
    db,issue,release,snapshot,scr=context;items=evidence(db,issue,release,snapshot,scr,1)
    other=Release(software_id=release.software_id,release_type='STANDARD',version='OTHER');old=ReleaseSnapshot(release_id=release.id,snapshot_no='OLD-ISS',snapshot_number=0,content_hash='b'*64,status='FROZEN');db.add_all([other,old]);db.flush()
    for number,r,s in [(2,other,snapshot),(3,release,old)]:db.add(DvpExecution(dvp_item_id=items[0],execution_no=number,release_id=r.id,snapshot_id=s.id,result='FAIL'))
    db.commit();data=evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)
    assert verification_page(issue.issue_no,release.id,epages(data),db)['items'][0]['result']=='PASS'


def test_no_linked_scr_and_foreign_software_release(context):
    db,issue,release,_,_=context
    db.delete(db.scalar(select(IssueChangeRequestRelation)));db.commit()
    data=summary(issue.issue_no,Empty(),db);assert data['candidate_count']==data['linked_count']==0
    with pytest.raises(HTTPException) as error:evidence_summary(issue.issue_no,release.id,SnapshotSelection(),db)
    assert error.value.status_code==409
