"""Original assignment receipts remain distinct from effective relationship history."""
import uuid
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from test_impact_assessments import context
from test_change_coverage import coverage_context, assignment
from app.api.change_coverage import assign_acceptance
from app.models.audit import AuditEvent
from app.models.acceptance import AcceptanceDvpLink
from app.services.change_coverage import report_coverage
from app.api.change_coverage_views import Selection, PageFilters, summary, group_summary, group_items_page, assignment_page
from app.api.dvp_catalog import RelationPage, dvp_relations, dvp_profile
from app.actor import ActorContext
from app.services.change_coverage import CoverageError, record_assignment
from dataclasses import replace
from test_command_audit import trusted_actor


def write(ctx, body):
    return assign_acceptance(ctx[4].request_no, body, Response(), ctx[0])


def test_replace_withdraw_and_reassign_preserve_original_history(coverage_context):
    ctx = coverage_context; db, _, _, _, scr, criterion, _, items = ctx
    original = assignment(criterion, items[0]); first = write(ctx, original)
    replacement = assignment(criterion, items[1], action='SUPERSEDE', supersedes_id=original.request_id)
    second = write(ctx, replacement)
    assert second['action'] == 'SUPERSEDE' and second['supersedes_id'] == first['id']
    assert write(ctx, original)['superseded_by_id'] == second['id']
    assert [r['id'] for r in report_coverage(db, scr.request_no)['acceptance_criteria'][0]['dvp_items']] == [str(items[1].id)]
    withdrawal = assignment(criterion, items[1], action='WITHDRAW', supersedes_id=replacement.request_id)
    third = write(ctx, withdrawal)
    assert third['action'] == 'WITHDRAW'
    assert report_coverage(db, scr.request_no)['summary']['acceptance']['assigned'] == 0
    assert write(ctx, replacement)['id'] == second['id']
    write(ctx, assignment(criterion, items[0]))
    assert report_coverage(db, scr.request_no)['summary']['acceptance']['assigned'] == 1
    assert len(db.scalars(select(AcceptanceDvpLink)).all()) == 4
    assert db.get(AcceptanceDvpLink, original.request_id).reason == original.reason
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-AC-{original.request_id}'))
    assert event.action == 'ASSIGN' and 'supersedes_id' not in event.payload_json


@pytest.mark.parametrize('action,predecessor', [('ASSIGN',uuid.uuid4()),('SUPERSEDE',None),('WITHDRAW',None),('UPDATE',None)])
def test_invalid_action_pair(coverage_context, action, predecessor):
    with pytest.raises(ValidationError):
        assignment(coverage_context[5], coverage_context[7][0], action=action, supersedes_id=predecessor)


@pytest.mark.parametrize('case', ['missing','self','stale','duplicate_target','same_target','wrong_withdraw_target','withdrawn'])
def test_invalid_relationship_change_conflicts(coverage_context, case):
    ctx = coverage_context; criterion, items = ctx[5],ctx[7]
    root = assignment(criterion, items[0]); write(ctx, root)
    body = assignment(criterion, items[1], action='SUPERSEDE', supersedes_id=root.request_id)
    if case == 'missing': body = body.model_copy(update={'supersedes_id':uuid.uuid4()})
    if case == 'self': body = body.model_copy(update={'supersedes_id':body.request_id})
    if case == 'stale': write(ctx, body); body = body.model_copy(update={'request_id':uuid.uuid4()})
    if case == 'duplicate_target': write(ctx, assignment(criterion, items[1]))
    if case == 'same_target': body = body.model_copy(update={'dvp_item_id':items[0].id})
    if case == 'wrong_withdraw_target': body = body.model_copy(update={'action':'WITHDRAW'})
    if case == 'withdrawn':
        withdrawal = assignment(criterion, items[0], action='WITHDRAW', supersedes_id=root.request_id); write(ctx, withdrawal)
        body = body.model_copy(update={'supersedes_id':withdrawal.request_id})
    with pytest.raises(HTTPException) as error: write(ctx, body)
    assert error.value.status_code == 409


@pytest.mark.parametrize('tamper', ['action','payload','detail','missing'])
def test_correction_retry_requires_its_exact_atomic_audit(coverage_context,tamper):
    ctx = coverage_context; db = ctx[0]
    root = assignment(ctx[5],ctx[7][0]); write(ctx,root)
    body = assignment(ctx[5],ctx[7][1],action='SUPERSEDE',supersedes_id=root.request_id); write(ctx,body)
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f'EVT-AC-{body.request_id}'))
    if tamper == 'missing': db.delete(event)
    elif tamper == 'payload': event.payload_json = None
    elif tamper == 'action': event.action = 'ASSIGN'
    else: event.detail = 'Other'
    db.commit()
    with pytest.raises(HTTPException) as error: write(ctx,body)
    assert error.value.status_code == 409


def test_all_readers_exclude_old_and_withdrawn_relations_but_page_complete_history(coverage_context):
    ctx=coverage_context;db,_,release,snapshot,scr,criterion,_,items=ctx
    original=assignment(criterion,items[0]);write(ctx,original)
    body=assignment(criterion,items[1],action='SUPERSEDE',supersedes_id=original.request_id);write(ctx,body)
    pins=summary(scr.request_no,Selection(release_id=release.id),db)
    filters=PageFilters(**{k:pins[k] for k in ('change_id','release_id','snapshot_id')},limit=1)
    assert group_summary(scr.request_no,'acceptance',criterion.id,filters,db)['assignment_count']==2
    assert group_items_page(scr.request_no,'acceptance',criterion.id,filters,db)['items'][0]['id']==str(items[1].id)
    assert dvp_profile(items[0].id,db)['relation_counts']['criteria']==0
    assert dvp_relations(items[1].id,'criteria',RelationPage(dvp_item_id=items[1].id),db)['total']==1
    first=assignment_page(scr.request_no,criterion.id,filters,db)
    assert first['total']==2 and first['items'][0]['superseded_by_id']==str(body.request_id)
    assert first['items'][0]['effective'] is False
    second=assignment_page(scr.request_no,criterion.id,filters.model_copy(update={'offset':1}),db)
    assert second['items'][0]['supersedes_id']==str(original.request_id) and second['items'][0]['effective'] is True
    write(ctx,assignment(criterion,items[1],action='WITHDRAW',supersedes_id=body.request_id))
    assert summary(scr.request_no,Selection(release_id=release.id),db)['summary']['acceptance']['assigned']==0
    assert dvp_relations(items[1].id,'criteria',RelationPage(dvp_item_id=items[1].id),db)['total']==0
    assert group_items_page(scr.request_no,'acceptance',criterion.id,filters,db)['total']==0
    assert assignment_page(scr.request_no,criterion.id,filters,db)['total']==3


@pytest.mark.parametrize('field',['action','supersedes_id','reason','dvp_item_id','actor_name'])
def test_changed_retry_conflicts(coverage_context,field):
    ctx=coverage_context;root=assignment(ctx[5],ctx[7][0]);write(ctx,root)
    body=assignment(ctx[5],ctx[7][1],action='SUPERSEDE',supersedes_id=root.request_id);write(ctx,body)
    value=uuid.uuid4() if field in ('supersedes_id','dvp_item_id') else 'WITHDRAW' if field=='action' else 'Changed'
    with pytest.raises(HTTPException) as error: write(ctx,body.model_copy(update={field:value}))
    assert error.value.status_code==409


def test_correction_retry_binds_authenticated_principal_and_declaration(coverage_context):
    ctx=coverage_context;db=ctx[0];root=assignment(ctx[5],ctx[7][0]);write(ctx,root)
    body=assignment(ctx[5],ctx[7][1],action='SUPERSEDE',supersedes_id=root.request_id)
    actor=replace(trusted_actor(db,'acceptance-correction','Trusted'),declared_name=body.actor_name)
    record_assignment(db,ctx[4].request_no,body,actor);db.commit()
    for changed in [replace(actor,principal_id=uuid.uuid4()),replace(actor,name='Other'),
        replace(actor,declared_name='Changed'),replace(actor,source='REQUEST_DECLARED')]:
        with pytest.raises(CoverageError): record_assignment(db,ctx[4].request_no,body,changed)
        db.rollback()


def test_foreign_criterion_predecessor_conflicts(coverage_context):
    from app.models.change import AcceptanceCriterion
    ctx=coverage_context;db=ctx[0];root=assignment(ctx[5],ctx[7][0]);write(ctx,root)
    other=AcceptanceCriterion(change_request_id=ctx[4].id,criterion_no='OTHER',description='Other')
    db.add(other);db.commit()
    with pytest.raises(HTTPException) as error:
        write(ctx,assignment(other,ctx[7][1],action='SUPERSEDE',supersedes_id=root.request_id))
    assert error.value.status_code==409


@pytest.mark.parametrize('action',['SUPERSEDE','WITHDRAW'])
@pytest.mark.parametrize('grant',['valid','missing','wrong_role','suspended','foreign_project'])
def test_corrections_retain_exact_active_contributor_authorization(coverage_context,monkeypatch,action,grant):
    from app import authorization
    from app.models.core import Customer,Project
    from app.models.security import ProjectMembership,SecurityPrincipal
    from test_authorization import authenticated_request
    ctx=coverage_context;db=ctx[0];root=assignment(ctx[5],ctx[7][0]);write(ctx,root)
    actor=trusted_actor(db,'correction-authority','Trusted engineer')
    customer=Customer(code='C-CORRECT',name='Customer');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='CORRECT',name='Project')
    foreign=Project(customer_id=customer.id,project_code='FOREIGN',name='Foreign');db.add_all([project,foreign]);db.flush()
    ctx[4].project_id=project.id
    if grant!='missing': db.add(ProjectMembership(principal_id=actor.principal_id,
        project_id=foreign.id if grant=='foreign_project' else project.id,
        role='REVIEWER' if grant=='wrong_role' else 'CONTRIBUTOR',status='SUSPENDED' if grant=='suspended' else 'ACTIVE'))
    db.commit();request=authenticated_request(db.get(SecurityPrincipal,actor.principal_id))
    monkeypatch.setattr(authorization.settings,'auth_mode','oidc')
    body=assignment(ctx[5],ctx[7][0 if action=='WITHDRAW' else 1],action=action,supersedes_id=root.request_id)
    if grant=='valid':
        result=assign_acceptance(ctx[4].request_no,body,Response(),db,request)
        assert result['actor_name']=='Trusted engineer'
        event=db.scalar(select(AuditEvent).where(AuditEvent.event_no==f'EVT-AC-{body.request_id}'))
        assert event.actor_principal_id==actor.principal_id and event.declared_actor_name==body.actor_name
    else:
        with pytest.raises(authorization.AuthorizationError): assign_acceptance(ctx[4].request_no,body,Response(),db,request)
        assert db.get(AcceptanceDvpLink,body.request_id) is None


def test_long_history_keeps_fixed_sql_and_scalar_bounded_pages(coverage_context):
    from sqlalchemy import event
    ctx=coverage_context;db=ctx[0];root=assignment(ctx[5],ctx[7][0]);write(ctx,root)
    number=ctx[4].request_no;criterion=ctx[5].id;item_ids=[i.id for i in ctx[7]];statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    def probe():
        db.expunge_all();statements.clear()
        pins=summary(number,Selection(),db);filters=PageFilters(**{k:pins[k] for k in ('change_id','release_id','snapshot_id')},limit=1)
        history=assignment_page(number,criterion,filters,db)
        current=group_items_page(number,'acceptance',criterion,filters,db)
        assert not db.identity_map and len(history['items'])==len(current['items'])==1
        return history,current,list(statements)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        _,_,before=probe();previous=root.request_id
        for n in range(120):
            identifier=uuid.uuid4()
            db.add(AcceptanceDvpLink(id=identifier,criterion_id=criterion,dvp_item_id=item_ids[(n+1)%2],
                actor_name='Engineer',reason='Correction',action='SUPERSEDE',supersedes_id=previous));db.flush();previous=identifier
        db.commit();history,current,after=probe()
        assert before==after and history['total']==121 and current['total']==1
        assert history['items'][0]['effective'] is False
    finally: event.remove(db.bind,'before_cursor_execute',capture)
