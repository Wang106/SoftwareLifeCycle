const base=require('./impact-correction.cjs');
function command(previous='AFFECTED'){
 const c=base.command('NEEDS_REVIEW',previous);return{operation:'impact-withdrawal',target:c.target,
  body:{request_id:c.body.request_id,actor_name:c.body.actor_name,reason:'Withdraw disputed interpretation\n撤销说明',release_id:c.body.release_id,snapshot_id:c.body.snapshot_id,supersedes_id:c.body.supersedes_id,correction_reason:'Independent review required\n复核原因'},
  predecessor:{...c.predecessor,decision:previous}};
}
const eventNo=c=>'EVT-IMPACT-'+c.body.request_id;
function audit(c,actor=base.principal){const e=base.audit(base.command('NEEDS_REVIEW',c.predecessor.decision),actor);e.action='WITHDRAW';e.detail=c.body.reason;e.declared_actor_name=c.body.actor_name;Object.assign(e.payload,{assessment_id:c.body.request_id,release_id:c.body.release_id,snapshot_id:c.body.snapshot_id,supersedes_id:c.body.supersedes_id,previous_decision:c.predecessor.decision,decision:null,correction_reason:c.body.correction_reason,actor_source:'AUTHENTICATED_PRINCIPAL',history_action:'WITHDRAW',context_seq:3,after_withdrawal_id:null,evidence_ref_digest_version:1,evidence_ref_sha256:require('node:crypto').createHash('sha256').update('null').digest('hex'),snapshot_no:'SNAP-IMPACT-1'});return e;}
function receipt(c){return{operation:c.operation,request_id:c.body.request_id,target:c.target,audit_event_no:eventNo(c),result:{id:c.body.request_id,action:'WITHDRAW',context_seq:3,after_withdrawal_id:null,decision:null,evidence_ref:null,superseded_by_id:null,issue_id:base.entity,issue_no:c.target,snapshot_no:'SNAP-IMPACT-1',release_id:c.body.release_id,snapshot_id:c.body.snapshot_id,supersedes_id:c.body.supersedes_id,actor_name:c.body.actor_name,reason:c.body.reason,correction_reason:c.body.correction_reason,previous_decision:c.predecessor.decision}};}
module.exports={...base,command,eventNo,audit,receipt};
