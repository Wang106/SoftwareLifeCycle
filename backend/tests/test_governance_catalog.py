import uuid
import pytest
from sqlalchemy import select,event
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_impact_assessments import context
from app.main import app
from app.models.approval import ApprovalRequest,ApprovalStep,ApprovalAction,ReleaseDecision
from app.models.snapshot import ReleaseSnapshot
from app.api.governance_catalog import Filters,HistoryFilters,approval_catalog,decision_catalog,approval_profile,decision_profile,action_history
from app.api.dashboard import list_approvals

@pytest.fixture
def governance(context):
 db,_,release,snapshot,_=context
 newer=ReleaseSnapshot(snapshot_no='NEW',release_id=release.id,snapshot_number=2,content_hash='b'*64,status='FROZEN');db.add(newer);db.flush()
 approvals=[ApprovalRequest(approval_no='APR-1',target_type='RELEASE',target_id=release.id,snapshot_id=snapshot.id,status='APPROVED',submitted_by='Engineer'),ApprovalRequest(approval_no='APR-2',target_type='RELEASE',target_id=release.id,snapshot_id=newer.id,status='PENDING'),ApprovalRequest(approval_no='APR-SCR',target_type='SCR',target_id=release.id,status='PENDING')]
 db.add_all(approvals);db.flush()
 steps=[ApprovalStep(approval_request_id=a.id,step_order=1,role_name='Review',status='APPROVED') for a in approvals[:2]];db.add_all(steps);db.flush()
 actions=[ApprovalAction(approval_request_id=approvals[0].id,step_id=steps[0].id,actor_name='Engineer',action=action,comment='History') for action in ['APPROVED','RETURNED']];db.add_all(actions)
 decisions=[ReleaseDecision(decision_no='RD-1',release_id=release.id,snapshot_id=snapshot.id,approval_request_id=approvals[0].id,readiness_status='READY',decision='RELEASE',decided_by='Engineer'),ReleaseDecision(decision_no='RD-2',release_id=release.id,snapshot_id=newer.id,approval_request_id=approvals[1].id,readiness_status='BLOCKED',decision='HOLD',decided_by='Other')];db.add_all(decisions);db.commit()
 return db,release,snapshot,newer,approvals,steps,actions,decisions

def test_exact_decision_and_separate_profile_history(governance):
 db,release,snapshot,newer,approvals,steps,actions,decisions=governance
 row=decision_profile('RD-1',db);assert row['snapshot']['snapshot_no']==snapshot.snapshot_no and row['context_consistent'] and row['decision']=='RELEASE'
 assert decision_profile('RD-2',db)['snapshot']['snapshot_no']=='NEW'
 profile=approval_profile('APR-1',db);assert profile['action_total']==2 and profile['step_total']==1 and 'actions' not in profile
 assert profile['snapshot']['id']==str(snapshot.id) and profile['binding_state']=='CONSISTENT'
 history=action_history('APR-1',HistoryFilters(),db);assert history['total']==2 and history['state_counts']=={'APPROVED':1,'RETURNED':1}
 assert all(r['context_consistent'] for r in history['items'])
 approvals[0].status='RETURNED';db.commit();assert decision_profile('RD-1',db)['decision']=='RELEASE'

def test_counts_not_multiplied_and_unknown_target_not_resolved(governance):
 db,release,snapshot,newer,approvals,*_=governance
 rows=approval_catalog(Filters(),db);assert rows['total']==3 and rows['state_counts']=={'APPROVED':1,'PENDING':2}
 assert rows['items'][0]['step_count']==1 and rows['items'][0]['action_count']==2 and rows['items'][0]['decision_count']==1
 assert rows['items'][2]['release'] is None and rows['items'][2]['binding_state']=='UNVERIFIED_TARGET_TYPE'
 assert approval_catalog(Filters(release_id=release.id),db)['total']==2
 assert isinstance(list_approvals(db),list) and len(list_approvals(db))==3

@pytest.mark.parametrize('route,total',[(approval_catalog,3),(decision_catalog,2)])
def test_catalog_filters_and_paging(governance,route,total):
 db,release,snapshot,newer,approvals,*_=governance
 page=route(Filters(limit=1),db);second=route(Filters(limit=1,offset=1),db)
 assert page['total']==second['total']==total and page['state_counts']==second['state_counts'] and page['items'][0]['id']!=second['items'][0]['id']
 assert route(Filters(snapshot_id=snapshot.id),db)['total']==1 and route(Filters(approval_id=approvals[0].id),db)['total']==1
 assert route(Filters(q='%_'),db)['total']==0 and route(Filters(offset=100),db)['items']==[]
 assert route(Filters(state='ABSENT'),db)['total']==0

def test_literal_search(governance):
 db,_,_,_,approvals,*_=governance;approvals[0].approval_no='APR-%_';db.commit()
 assert approval_catalog(Filters(q='%_'),db)['total']==1 and decision_catalog(Filters(q='%_'),db)['total']==1
 assert approval_catalog(Filters(q='%missing'),db)['total']==0

def test_action_filters_pages_and_bad_step_binding(governance):
 db,_,_,_,approvals,steps,actions,_=governance
 first=action_history('APR-1',HistoryFilters(limit=1),db);second=action_history('APR-1',HistoryFilters(limit=1,offset=1),db)
 assert first['total']==second['total']==2 and first['items'][0]['id']!=second['items'][0]['id'] and second['next_offset'] is None
 assert action_history('APR-1',HistoryFilters(action='APPROVED'),db)['total']==1
 actions[0].step_id=steps[1].id;db.commit()
 row=action_history('APR-1',HistoryFilters(action='APPROVED'),db)['items'][0];assert not row['context_consistent']
 actions[0].step_id=uuid.uuid4();db.commit();assert not action_history('APR-1',HistoryFilters(action='APPROVED'),db)['items'][0]['context_consistent']
 actions[0].step_id=None;db.commit();assert action_history('APR-1',HistoryFilters(action='APPROVED'),db)['items'][0]['context_consistent']

@pytest.mark.parametrize('case',['approval_snapshot','decision_snapshot','target_type','missing_release','draft_snapshot'])
def test_mismatched_binding_preserved(governance,case):
 db,release,snapshot,newer,approvals,steps,actions,decisions=governance
 if case=='approval_snapshot':approvals[0].snapshot_id=newer.id
 elif case=='decision_snapshot':decisions[0].snapshot_id=newer.id
 elif case=='target_type':approvals[0].target_type='SCR'
 elif case=='missing_release':decisions[0].release_id=uuid.uuid4()
 else:snapshot.status='DRAFT'
 db.commit();row=decision_profile('RD-1',db);assert not row['context_consistent'] and row['decision_no']=='RD-1'
 assert decision_catalog(Filters(),db)['total']==2

def test_bounded_steps_and_empty_actions(governance):
 db,_,_,_,approvals,*_=governance
 db.add_all([ApprovalStep(approval_request_id=approvals[2].id,step_order=n,role_name='Review') for n in range(201)]);db.commit()
 row=approval_profile('APR-SCR',db);assert row['step_total']==201 and len(row['steps'])==200 and row['steps_truncated']
 assert action_history('APR-SCR',HistoryFilters(),db)['items']==[]

def test_missing_profiles_and_history(governance):
 db,*_=governance
 for call in [lambda:approval_profile('NONE',db),lambda:decision_profile('NONE',db),lambda:action_history('NONE',HistoryFilters(),db)]:
  with pytest.raises(HTTPException) as error:call()
  assert error.value.status_code==404

def test_metadata_query_count_is_batched(governance):
 db,*_=governance;calls=[]
 def record(*args):calls.append(args[2])
 event.listen(db.bind,'before_cursor_execute',record)
 try:
  approval_catalog(Filters(limit=1),db);first=len(calls);calls.clear();approval_catalog(Filters(limit=100),db);assert len(calls)==first==6
 finally:event.remove(db.bind,'before_cursor_execute',record)

@pytest.mark.parametrize('path',['approvals?limit=0','decisions?limit=101','approvals?release_id=bad','decisions?unknown=yes','approvals/APR-1/actions?offset=-1','approvals/APR-1/actions?unknown=yes'])
def test_http_validation(path):
 with TestClient(app) as client:response=client.get('/api/v1/governance/'+path)
 assert response.status_code==422,response.text
