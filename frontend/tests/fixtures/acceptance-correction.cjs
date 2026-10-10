const base=require('./evidence-command.cjs');
const predecessor='89012345-1234-1234-1234-123456789abc',replacement='90123456-1234-1234-1234-123456789abc';
function command(action='SUPERSEDE',previous='ASSIGN'){
 const c=base.command('acceptance');return{operation:'acceptance-correction',target:c.target,
 body:{...c.body,dvp_item_id:action==='WITHDRAW'?base.dvp:replacement,action,supersedes_id:predecessor},
 predecessor:{id:predecessor,criterion_id:base.criterion,dvp_item_id:base.dvp,action:previous}};
}
function audit(c,actor=base.principal){const e=base.audit({...c,operation:'acceptance'},actor);
 e.action=c.body.action;Object.assign(e.payload,{supersedes_id:c.body.supersedes_id,previous_dvp_item_id:c.predecessor.dvp_item_id,previous_action:c.predecessor.action});return e;}
function receipt(c){const r=base.receipt({...c,operation:'acceptance'});
 r.operation=c.operation;Object.assign(r.result,{previous_dvp_item_id:c.predecessor.dvp_item_id,previous_action:c.predecessor.action});return r;}
module.exports={...base,predecessor,replacement,command,audit,receipt};

