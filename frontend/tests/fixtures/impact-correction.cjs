const base=require('./evidence-command.cjs');
const predecessor='89012345-1234-1234-1234-123456789abc';
function command(decision='NEEDS_REVIEW',previous='AFFECTED'){
 const c=base.command('impact');return{operation:'impact-correction',target:c.target,
 body:{...c.body,decision,supersedes_id:predecessor,correction_reason:'Correct original judgment\n更正理由'},
 predecessor:{id:predecessor,release_id:base.release,snapshot_id:base.snapshot,decision:previous}};
}
const eventNo=c=>'EVT-IMPACT-'+c.body.request_id;
function audit(c,actor=base.principal){const e=base.audit({...c,operation:'impact'},actor);e.action='SUPERSEDE';
 Object.assign(e.payload,{supersedes_id:c.body.supersedes_id,previous_decision:c.predecessor.decision,correction_reason:c.body.correction_reason});return e;}
function receipt(c){const r=base.receipt({...c,operation:'impact'});r.operation=c.operation;
 Object.assign(r.result,{previous_decision:c.predecessor.decision});return r;}
module.exports={...base,predecessor,command,eventNo,audit,receipt};

