const principal='11111111-1111-4111-8111-111111111111';
const release='22222222-2222-4222-8222-222222222222';
const snapshot='33333333-3333-4333-8333-333333333333';
const predecessor='44444444-4444-4444-8444-444444444444';
const approval='55555555-5555-4555-8555-555555555555';
function command(){return{operation:'release-decision-supersession',target:'APR-2026-0099',body:{
 request_id:'66aa6666-6666-4666-8666-666666666666',decision_no:'RD-0099',decided_by:'Release Authority / 发布权威',
 readiness_status:'CONDITIONALLY_READY',decision:'HOLD',notes:'Await corrected evidence / 等待更正证据',
 supersedes_id:predecessor,correction_reason:'Earlier readiness was incomplete / 早期就绪声明不完整'},
 predecessor:{id:predecessor,release_id:release,snapshot_id:snapshot,decision_no:'RD-0081',decision:'APPROVE',readiness_status:'READY'}};}
const eventNo=c=>'EVT-RD-'+c.body.request_id.replaceAll('-','');
function receipt(c){return{operation:c.operation,request_id:c.body.request_id,target:c.target,audit_event_no:eventNo(c),result:{
 id:c.body.request_id,approval_id:approval,approval_no:c.target,decision_no:c.body.decision_no,decision:c.body.decision,
 readiness_status:c.body.readiness_status,release_id:release,snapshot_id:snapshot,snapshot_no:'SNAP-0081',content_hash:'a'.repeat(64),
 supersedes_id:predecessor,correction_reason:c.body.correction_reason,predecessor_decision_no:c.predecessor.decision_no}};}
function audit(c){return{id:'77777777-7777-4777-8777-777777777777',event_no:eventNo(c),event_type:'RELEASE',action:'DECISION_SUPERSEDED',
 entity_type:'RELEASE_DECISION',entity_id:c.body.request_id,entity_ref:c.body.decision_no,actor_principal_id:principal,
 declared_actor_name:c.body.decided_by,detail:c.body.notes,payload:{decision:c.body.decision,readiness_status:c.body.readiness_status,
 release_id:release,snapshot_id:snapshot,snapshot_no:'SNAP-0081',content_hash:'a'.repeat(64),approval_id:approval,approval_no:c.target,
 supersedes_id:predecessor,correction_reason:c.body.correction_reason,actor_source:'AUTHENTICATED_PRINCIPAL',request:{
 approval_no:c.target,decision_no:c.body.decision_no,decided_by:c.body.decided_by,readiness_status:c.body.readiness_status,
 decision:c.body.decision,notes:c.body.notes,supersedes_id:predecessor,correction_reason:c.body.correction_reason}}};}
module.exports={principal,release,snapshot,predecessor,approval,command,eventNo,receipt,audit};
