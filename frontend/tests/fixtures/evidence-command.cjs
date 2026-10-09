const {createHash}=require('node:crypto');
const key='34567890-1234-1234-1234-123456789abc',principal='12345678-1234-1234-1234-123456789abc',entity='56789012-1234-1234-1234-123456789abc',event='11111111-1234-1234-1234-123456789abc',
 release='23456789-1234-1234-1234-123456789abc',snapshot='45678901-1234-1234-1234-123456789abc',criterion='67890123-1234-1234-1234-123456789abc',dvp='78901234-1234-1234-1234-123456789abc';
const command=(operation='impact')=>({operation,target:operation==='impact'?'ISSUE-原始':'SCR-原始',body:{request_id:key,actor_name:'Declared engineer',reason:'Original reason\n原文',...(operation==='impact'?{release_id:release,snapshot_id:snapshot,decision:'NEEDS_REVIEW',evidence_ref:'//server/share/原始证据.pdf'}:{criterion_id:criterion,dvp_item_id:dvp})}});
const eventNo=c=>(c.operation==='impact'?'EVT-IMPACT-':'EVT-AC-')+c.body.request_id;
const digest=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
function audit(c,actor=principal){const b=c.body;return{id:event,event_no:eventNo(c),entity_id:entity,entity_ref:c.target,actor_principal_id:actor,declared_actor_name:b.actor_name,detail:b.reason,
 event_type:c.operation==='impact'?'ISSUE_IMPACT':'ACCEPTANCE_DVP',entity_type:c.operation==='impact'?'Issue':'SoftwareChangeRequest',action:c.operation==='impact'?'ASSESS':'ASSIGN',
 payload:{actor_source:'AUTHENTICATED_PRINCIPAL',...(c.operation==='impact'?{assessment_id:b.request_id,release_id:b.release_id,snapshot_id:b.snapshot_id,snapshot_no:'SNAP-原始',decision:b.decision,evidence_ref_digest_version:1,evidence_ref_sha256:digest(b.evidence_ref)}:{assignment_id:b.request_id,criterion_id:b.criterion_id,dvp_item_id:b.dvp_item_id})},token:'private'};}
function receipt(c){const {request_id,...original}=c.body;return{operation:c.operation,request_id,target:c.target,audit_event_no:eventNo(c),result:{id:request_id,...original,...(c.operation==='impact'?{issue_id:entity,issue_no:c.target,snapshot_no:'SNAP-原始'}:{change_request_id:entity,request_no:c.target})}};}
module.exports={key,principal,entity,event,release,snapshot,criterion,dvp,command,eventNo,digest,audit,receipt};
