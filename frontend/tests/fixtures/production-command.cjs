'use strict';
const key='34567890-1234-1234-1234-123456789abc',principal='12345678-1234-1234-1234-123456789abc',
 authorization='23456789-1234-1234-1234-123456789abc',deployment='45678901-1234-1234-1234-123456789abc',
 release='56789012-1234-1234-1234-123456789abc',snapshot='67890123-1234-1234-1234-123456789abc',
 line='78901234-1234-1234-1234-123456789abc',from='89012345-1234-1234-1234-123456789abc',event='11111111-1234-1234-1234-123456789abc';
const command=operation=>({operation,target:operation==='test-release'?release:operation==='deployment'?authorization:'DEP-原始',
 body:operation==='test-release'?{request_id:key,release_id:release,snapshot_id:snapshot,test_release_no:'TR-原始',purpose_scope:'SOFTWARE_TEST',actor_name:'Declared operator',reason:'Original reason\n原文'}:
 operation==='deployment'?{request_id:key,authorization_id:authorization,production_line_id:line,deployment_no:'DEP-新建'}:
 {request_id:key,changeover_no:'CO-原始',from_release_id:from,changed_at:null,note:'Original note\n原文'}});
const eventNo=c=>c.operation==='test-release'?'EVT-TR-'+c.body.request_id:'EVT-'+(c.operation==='deployment'?'DPLOY':'CO')+'-'+c.body.request_id.replaceAll('-','');
const backendTime=value=>value===null?null:value.endsWith('.000Z')?value.slice(0,-5)+'+00:00':value.slice(0,-1)+'000+00:00';
function audit(c,actor=principal){const b=c.body,{request_id,...request}=b,
 p={actor_source:'AUTHENTICATED_PRINCIPAL'},e={id:event,event_no:eventNo(c),entity_id:request_id,actor_principal_id:actor,declared_actor_name:null,token:'private',subject:'private'};
 return c.operation==='test-release'?{...e,event_type:'TEST_RELEASE',entity_type:'TEST_RELEASE',action:'CREATE_DRAFT',entity_ref:b.test_release_no,
  declared_actor_name:b.actor_name,detail:b.reason,payload:{...p,release_id:release,snapshot_id:snapshot,snapshot_no:'SNAP-0001-'+release.slice(0,8),purpose_scope:b.purpose_scope,status:'DRAFT'}}:
 c.operation==='deployment'?{...e,event_type:'DEPLOYMENT',entity_type:'DEPLOYMENT',action:'CREATED',entity_ref:b.deployment_no,payload:{...p,request,
  authorization_id:authorization,production_line_id:line,expected_release_id:release,expected_snapshot_id:snapshot,status:'PENDING'}}:
 {...e,event_type:'CHANGEOVER',entity_type:'SOFTWARE_CHANGEOVER',action:'COMPLETED',entity_ref:b.changeover_no,
  occurred_at:b.changed_at||'2026-10-09T02:00:00.123456Z',payload:{...p,request:{deployment_no:c.target,...Object.fromEntries(Object.entries(request).map(([k,v])=>[k,k==='changed_at'?backendTime(v):v]))},
  deployment_id:deployment,deployment_no:c.target,authorization_id:authorization,from_release_id:b.from_release_id,to_release_id:release,status:'COMPLETED'}};
}
function receipt(c){const b=c.body,a=audit(c),p=a.payload;return{operation:c.operation,request_id:b.request_id,target:c.target,audit_event_no:eventNo(c),result:
 c.operation==='test-release'?{id:b.request_id,test_release_no:b.test_release_no,status:'DRAFT',release_id:p.release_id,snapshot_id:p.snapshot_id,snapshot_no:p.snapshot_no,
  purpose_scope:b.purpose_scope,actor_name:b.actor_name,reason:b.reason}:
 c.operation==='deployment'?{id:b.request_id,deployment_no:b.deployment_no,status:'PENDING',authorization_id:p.authorization_id,production_line_id:p.production_line_id,
  expected_release_id:p.expected_release_id,expected_snapshot_id:p.expected_snapshot_id}:
 {id:b.request_id,changeover_no:b.changeover_no,status:'COMPLETED',deployment_id:p.deployment_id,deployment_no:c.target,authorization_id:p.authorization_id,
  from_release_id:b.from_release_id,to_release_id:p.to_release_id,changed_at:b.changed_at?b.changed_at.slice(0,-1)+'000Z':a.occurred_at,note:b.note}};}
module.exports={key,principal,authorization,deployment,release,snapshot,line,from,event,command,eventNo,audit,receipt};
