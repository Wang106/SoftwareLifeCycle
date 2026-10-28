"""Synthetic private evidence selectors; no real identities or business writes."""
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.core import Release, ApplicationReleaseDetail, Project
from app.models.change import SoftwareChangeRequest, AcceptanceCriterion, Issue, IssueChangeRequestRelation
from app.models.testing import DvpPlan, DvpItem, TestRelease as TestReleaseModel, DvpExecution
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ApprovalStep
from app.models.security import SecurityPrincipal, ProjectMembership, BrowserSession
from app.models.resource import ResourceLink
from app.services.private_evidence_selection import PrivateEvidenceSelection
from test_authorization_approval import approval_db, approval_client, actor_request, counts, TOKEN  # noqa:F401
from test_authorization_approval_postgres import approval_pg  # noqa:F401
from test_command_concurrency_postgres import pg  # noqa:F401


def seed(db,ids):
    release=db.get(Release,ids['release'])
    changes=[]
    for index,project in enumerate([ids['project'],ids['foreign_project']]):
        change=SoftwareChangeRequest(request_no='EVI-SCR-'+str(index),title='Synthetic change',source='INTERNAL',scope='APPLICATION',change_type='FEATURE',software_id=release.software_id,project_id=project,background='PRIVATE-BACKGROUND');db.add(change);db.flush();changes.append(change)
        plan=DvpPlan(change_request_id=change.id,plan_no='EVI-PLAN-'+str(index),title='Plan');db.add(plan);db.flush()
        for n in range(3):
            db.add(AcceptanceCriterion(change_request_id=change.id,criterion_no='AC-'+str(n),description='Exact criterion '+str(n)))
            db.add(DvpItem(plan_id=plan.id,item_no='DVP-'+str(n),title='Exact DVP '+str(n),scope='SOFTWARE_TEST'))
    issue=Issue(issue_no='EVI-ISSUE',title='Issue',scope='APPLICATION',severity='MAJOR',description='PRIVATE-ISSUE');db.add(issue);db.flush()
    db.add(IssueChangeRequestRelation(issue_id=issue.id,change_request_id=changes[0].id,relation_type='RELATED'))
    approval=ApprovalRequest(approval_no='EVI-APPROVAL',target_type='RELEASE',target_id=release.id,snapshot_id=ids['snapshot'],status='PENDING');db.add(approval);db.flush()
    steps=[]
    for order,status in [(1,'APPROVED'),(2,'PENDING'),(3,'WAITING')]:
        step=ApprovalStep(approval_request_id=approval.id,step_order=order,role_name='Review '+str(order),status=status,approver_name='PRIVATE-APPROVER');db.add(step);db.flush();steps.append(step.id)
    grants=[]
    for role in ['REVIEWER','CONTRIBUTOR']:
        grant=ProjectMembership(principal_id=ids['people']['approver'],project_id=ids['project'],role=role);db.add(grant);db.flush();grants.append(grant.id)
    db.add(ReleaseSnapshot(release_id=release.id,snapshot_no='EVI-DRAFT',snapshot_number=2,status='DRAFT',content_hash='b'*64))
    db.commit()
    return {'change':changes[0].id,'foreign_change':changes[1].id,'issue':issue.id,'approval':approval.id,'steps':steps,'grants':grants}

@pytest.fixture(params=['sqlite','postgres'])
def evidence_db(request):
    if request.param=='sqlite':
        db,ids=request.getfixturevalue('approval_db');yield db,ids,seed(db,ids)
    else:
        engine,ids=request.getfixturevalue('approval_pg')
        with Session(engine,expire_on_commit=False) as db:yield db,ids,seed(db,ids)


def run(db,ids,kind,request=None):
    svc=PrivateEvidenceSelection(db);request=request or actor_request(db,ids)
    if kind=='approval':return svc.approval(request,'EVI-APPROVAL')
    if kind in ('criteria','dvp'):return svc.changes(request,'EVI-SCR-0',kind,limit=2)
    if kind=='impact':return svc.snapshots(request,'EVI-ISSUE',ids['release'])
    return svc.resource(request,'PROJECT',ids['project'])

@pytest.mark.parametrize('kind',['approval','criteria','dvp','impact','resource'])
def test_minimal_readonly_context_and_no_side_effects(evidence_db,kind,monkeypatch):
    db,ids,extra=evidence_db;monkeypatch.setattr(settings,'read_only_mode',True)
    before=counts(db);links=db.scalar(select(func.count()).select_from(ResourceLink));value=run(db,ids,kind)
    assert not db.in_transaction() and counts(db)==before and db.scalar(select(func.count()).select_from(ResourceLink))==links
    assert not any(s in str(value) for s in ['PRIVATE-','storage_reference','actor_name','approver_name','background','location'])
    if kind=='approval':
        assert value['step']=={'step_id':str(extra['steps'][1]),'step_order':2,'role_name':'Review 2','status':'PENDING'}
        assert set(value['context'])=={'approval_id','approval_no','project_id','target_type','target_id','snapshot_id','status'}
    elif kind in ('criteria','dvp'):
        assert len(value['items'])==2 and value['next_offset']==2 and value['context']['change_request_id']==str(extra['change'])
        page=PrivateEvidenceSelection(db).changes(actor_request(db,ids),'EVI-SCR-0',kind,limit=2,offset=2)
        assert len(page['items'])==1 and page['next_offset'] is None
        assert 'total' not in value
    elif kind=='impact':assert value['items']==[{'snapshot_id':ids['snapshot'],'snapshot_no':'PAA-SNAP','snapshot_number':1,'status':'FROZEN'}]
    else:assert value['context']=={'entity_type':'PROJECT','entity_id':str(ids['project']),'entity_ref':'PAA-P','project_ids':[str(ids['project'])]}

@pytest.mark.parametrize('kind',['approval','criteria','dvp','impact','resource'])
@pytest.mark.parametrize('person',['admin','foreign','creator'])
def test_no_admin_bypass_or_foreign_project_role(evidence_db,kind,person):
    db,ids,_=evidence_db;before=counts(db)
    with pytest.raises(HTTPException) as error:run(db,ids,kind,actor_request(db,ids,person))
    assert error.value.status_code==404 and error.value.detail=='selection_target_not_found'
    assert not db.in_transaction() and counts(db)==before

@pytest.mark.parametrize('mode',['disabled','principal','service','session','role'])
def test_current_user_session_and_role_required(evidence_db,mode,monkeypatch):
    db,ids,extra=evidence_db;request=actor_request(db,ids,'service' if mode=='service' else 'approver')
    if mode=='disabled':monkeypatch.setattr(settings,'auth_mode','disabled')
    elif mode=='principal':db.get(SecurityPrincipal,ids['people']['approver']).status='DISABLED';db.commit()
    elif mode=='role':db.get(ProjectMembership,extra['grants'][0]).status='SUSPENDED';db.commit()
    elif mode=='session':
        now=datetime.now(timezone.utc);sid=uuid.uuid4();db.add(BrowserSession(id=sid,principal_id=ids['people']['approver'],token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),created_at=now,expires_at=now+timedelta(minutes=5),revoked_at=now));db.commit();request=actor_request(db,ids,session_id=sid)
    with pytest.raises(HTTPException) as error:run(db,ids,'approval',request)
    assert error.value.status_code==({'service':403,'role':404}.get(mode,401)) and not db.in_transaction()


def test_scr_approval_and_closed_or_missing_step(evidence_db):
    db,ids,extra=evidence_db;approval=db.get(ApprovalRequest,extra['approval']);approval.target_type='SCR';approval.target_id=extra['change'];approval.snapshot_id=None;db.commit()
    value=run(db,ids,'approval');assert value['context']['target_id']==str(extra['change']) and value['context']['snapshot_id'] is None
    db.get(ApprovalRequest,extra['approval']).status='APPROVED';db.commit()
    with pytest.raises(HTTPException) as error:run(db,ids,'approval')
    assert error.value.status_code==409
    db.get(ApprovalRequest,extra['approval']).status='PENDING'
    for sid in extra['steps']:db.get(ApprovalStep,sid).status='APPROVED'
    db.commit()
    with pytest.raises(HTTPException) as error:run(db,ids,'approval')
    assert error.value.status_code==404


def test_issue_requires_linked_project_and_software(evidence_db):
    db,ids,extra=evidence_db
    link=db.scalar(select(IssueChangeRequestRelation).where(IssueChangeRequestRelation.issue_id==extra['issue']));link.change_request_id=extra['foreign_change'];db.commit()
    with pytest.raises(HTTPException) as error:run(db,ids,'impact')
    assert error.value.status_code==404


def test_resource_all_linked_projects_and_unscoped_denial(evidence_db):
    db,ids,extra=evidence_db;svc=PrivateEvidenceSelection(db)
    db.add(IssueChangeRequestRelation(issue_id=extra['issue'],change_request_id=extra['foreign_change'],relation_type='RELATED'));db.commit()
    with pytest.raises(HTTPException) as error:svc.resource(actor_request(db,ids),'ISSUE',extra['issue'])
    assert error.value.status_code==404
    db.add(ProjectMembership(principal_id=ids['people']['approver'],project_id=ids['foreign_project'],role='CONTRIBUTOR'));db.commit()
    value=svc.resource(actor_request(db,ids),'ISSUE',extra['issue']);assert set(value['context']['project_ids'])=={str(ids['project']),str(ids['foreign_project'])}
    for kind in ['CUSTOMER','SUPPLIER','UNKNOWN']:
        with pytest.raises(HTTPException) as error:svc.resource(actor_request(db,ids),kind,uuid.uuid4())
        assert error.value.status_code==404


def test_each_scoped_resource_has_exact_reference(evidence_db):
    db,ids,extra=evidence_db;item=db.scalar(select(DvpItem).join(DvpPlan).where(DvpPlan.change_request_id==extra['change']))
    test=TestReleaseModel(test_release_no='EVI-TEST',release_id=ids['release'],snapshot_id=ids['snapshot'],purpose_scope='SOFTWARE_TEST');db.add(test);db.flush()
    execution=DvpExecution(dvp_item_id=item.id,execution_no=1,release_id=ids['release'],snapshot_id=ids['snapshot'],test_release_id=test.id,result='PASS');db.add(execution);db.commit()
    for kind,target in [('RELEASE',ids['release']),('SNAPSHOT',ids['snapshot']),('SCR',extra['change']),('DVP_ITEM',item.id),('TEST_RELEASE',test.id),('DVP_EXECUTION',execution.id)]:
        value=PrivateEvidenceSelection(db).resource(actor_request(db,ids),kind,target)
        assert value['context']['entity_id']==str(target) and value['context']['project_ids']==[str(ids['project'])]
    db.get(SoftwareChangeRequest,extra['change']).project_id=None;db.commit()
    with pytest.raises(HTTPException):PrivateEvidenceSelection(db).resource(actor_request(db,ids),'DVP_ITEM',item.id)


@pytest.mark.parametrize('query',['limit=0','limit=51','offset=-1','offset=100001','unknown=x'])
def test_route_bounds_and_private_noauth_headers(approval_client,query):
    client,headers,ids=approval_client
    response=client.get('/api/v1/evidence-selection-context/changes/any/criteria?'+query,headers=headers)
    assert response.status_code==422 and response.headers['cache-control']=='private, no-store'
    for method,path in [('get','/changes/any/criteria'),('head','/approvals/any/current-step'),('get','/resources/PROJECT/'+str(ids['project'])+'/')]:
        response=getattr(client,method)('/api/v1/evidence-selection-context'+path,follow_redirects=False)
        assert response.status_code==401 and response.headers['cache-control']=='private, no-store'


def test_postgres_current_role_revocation_blocks_then_denies(approval_pg):
    from test_private_distribution_selection import _assert_selector_waits_for_committed_writer
    from app.services.admin_lock import admin_write_gate
    engine,ids=approval_pg
    with Session(engine,expire_on_commit=False) as db:extra=seed(db,ids)
    def revoke(db):
        admin_write_gate(db)
        db.scalar(select(SecurityPrincipal).where(SecurityPrincipal.id==ids['people']['approver']).with_for_update())
        grant=db.scalar(select(ProjectMembership).where(ProjectMembership.id==extra['grants'][0]).with_for_update());grant.status='SUSPENDED'
    _assert_selector_waits_for_committed_writer(engine,revoke,lambda db:run(db,ids,'approval'),(404,'selection_target_not_found'))


def test_postgres_approval_closure_blocks_then_hides_actionable_step(approval_pg):
    from test_private_distribution_selection import _assert_selector_waits_for_committed_writer
    engine,ids=approval_pg
    with Session(engine,expire_on_commit=False) as db:extra=seed(db,ids)
    def close(db):
        approval=db.scalar(select(ApprovalRequest).where(ApprovalRequest.id==extra['approval']).with_for_update())
        step=db.scalar(select(ApprovalStep).where(ApprovalStep.id==extra['steps'][1]).with_for_update())
        approval.status='RETURNED';step.status='RETURNED'
    _assert_selector_waits_for_committed_writer(engine,close,lambda db:run(db,ids,'approval'),(409,'selection_context_ineligible'))


def test_waiting_first_step_and_no_assignee_policy(evidence_db):
    db,ids,extra=evidence_db
    db.get(ApprovalStep,extra['steps'][1]).status='WAITING';db.commit()
    value=run(db,ids,'approval');assert value['step']['step_id']==str(extra['steps'][1]) and value['step']['status']=='WAITING'


def test_candidate_sets_exclude_foreign_scr_and_issue_unlinked_software(evidence_db):
    db,ids,extra=evidence_db
    for kind in ('criteria','dvp'):
        value=PrivateEvidenceSelection(db).changes(actor_request(db,ids),'EVI-SCR-0',kind,limit=50)
        if kind=='criteria':allowed=set(db.scalars(select(AcceptanceCriterion.id).where(AcceptanceCriterion.change_request_id==extra['change'])))
        else:allowed=set(db.scalars(select(DvpItem.id).join(DvpPlan).where(DvpPlan.change_request_id==extra['change'])))
        key='criterion_id' if kind=='criteria' else 'dvp_item_id'
        assert {r[key] for r in value['items']}==allowed and len(allowed)==3
    from app.models.core import SoftwareProduct
    release=db.get(Release,ids['release']);original=db.get(SoftwareProduct,release.software_id)
    other=SoftwareProduct(supplier_id=original.supplier_id,code='EVI-OTHER',name='Other software');db.add(other);db.flush()
    db.get(SoftwareChangeRequest,extra['change']).software_id=other.id;db.commit()
    with pytest.raises(HTTPException) as error:run(db,ids,'impact')
    assert error.value.status_code==404


def test_unlinked_issue_and_unscoped_approval_hidden(evidence_db):
    db,ids,extra=evidence_db
    issue=Issue(issue_no='EVI-EMPTY',title='Empty',scope='APPLICATION',severity='MINOR');db.add(issue);db.commit()
    with pytest.raises(HTTPException) as error:PrivateEvidenceSelection(db).resource(actor_request(db,ids),'ISSUE',issue.id)
    assert error.value.status_code==404
    db.get(ApprovalRequest,extra['approval']).target_type='UNKNOWN';db.commit()
    with pytest.raises(HTTPException) as error:run(db,ids,'approval')
    assert error.value.status_code==404
