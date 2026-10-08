'use strict';
const key='34567890-1234-1234-1234-123456789abc',principal='12345678-1234-1234-1234-123456789abc',
 approval='23456789-1234-1234-1234-123456789abc',step='45678901-1234-1234-1234-123456789abc',
 release='56789012-1234-1234-1234-123456789abc',snapshot='67890123-1234-1234-1234-123456789abc',event='78901234-1234-1234-1234-123456789abc';
const command=operation=>({operation,target:'APR-原始',body:operation==='approval'?
 {request_id:key,expected_step_id:step,actor:'  Declared operator  ',action:'APPROVED',comment:'Original comment\n原文'}:
 {request_id:key,decision_no:'RD-原始',decided_by:'  Declared authority  ',readiness_status:'  DECLARED  ',decision:'  HOLD  ',notes:'Original notes\n原文'}});
const eventNo=c=>'EVT-'+(c.operation==='approval'?'AP':'RD')+'-'+c.body.request_id.replaceAll('-','');
function audit(c,actor=principal){const b=c.body,{request_id,...fields}=b;const e={id:event,event_no:eventNo(c),actor_principal_id:actor,
 payload:{actor_source:'AUTHENTICATED_PRINCIPAL',request:{approval_no:c.target,...fields}},token:'private',subject:'private'};
 return c.operation==='approval'?{...e,event_type:'APPROVAL',entity_type:'APPROVAL_REQUEST',action:b.action,entity_id:approval,entity_ref:c.target,
  payload:{...e.payload,approval_action_id:b.request_id,step_id:b.expected_step_id,step_order:1,role_name:'Reviewer',target_type:'RELEASE',target_id:release,
   snapshot_id:snapshot,before_status:'PENDING',after_status:b.action==='APPROVED'?'PENDING':b.action,before_step_status:'PENDING',after_step_status:b.action}}:
  {...e,event_type:'RELEASE',entity_type:'RELEASE_DECISION',action:'DECISION_RECORDED',entity_id:b.request_id,entity_ref:b.decision_no,
   payload:{...e.payload,approval_id:approval,approval_no:c.target,decision:b.decision,readiness_status:b.readiness_status,
    release_id:release,snapshot_id:snapshot,snapshot_no:'SNAP-0001-'+release.slice(0,8),content_hash:'a'.repeat(64)}};
}
function receipt(c){const e=audit(c),p=e.payload,b=c.body;return{operation:c.operation,request_id:b.request_id,target:c.target,audit_event_no:eventNo(c),result:
 c.operation==='approval'?{approval_id:approval,approval_no:c.target,approval_action_id:b.request_id,step_id:b.expected_step_id,action:b.action,
  step_status:b.action,approval_status:p.after_status,step_order:1,role_name:'Reviewer',target_type:'RELEASE',target_id:release,snapshot_id:snapshot}:
 {id:b.request_id,approval_id:approval,approval_no:c.target,decision_no:b.decision_no,decision:b.decision,readiness_status:b.readiness_status,
  release_id:release,snapshot_id:snapshot,snapshot_no:p.snapshot_no,content_hash:p.content_hash}};}
module.exports={key,principal,approval,step,release,snapshot,event,command,eventNo,audit,receipt};
