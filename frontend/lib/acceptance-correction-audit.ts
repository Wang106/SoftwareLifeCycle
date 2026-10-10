import {record} from './first-command-transport';
import {validUuid} from './command-draft';
import {acceptanceCorrectionEvent,projectAcceptanceCorrectionReceipt,type AcceptanceCorrectionCommand,type AcceptanceCorrectionReceipt} from './acceptance-correction-transport';
/** Only the original actor-bound audit, including predecessor evidence, confirms a correction. */
export async function projectAcceptanceCorrectionAudit(value:unknown,c:AcceptanceCorrectionCommand,principalId:string):Promise<AcceptanceCorrectionReceipt|null> {
 const d=record(value),p=record(d?.payload),b=c.body;
 if(!d || !p || typeof d.id!=='string' || !validUuid(d.id) || !validUuid(principalId) ||
   d.event_no!==acceptanceCorrectionEvent(c) || d.actor_principal_id!==principalId.toLowerCase() ||
   d.event_type!=='ACCEPTANCE_DVP' || d.entity_type!=='SoftwareChangeRequest' || d.entity_ref!==c.target ||
   d.action!==b.action || d.declared_actor_name!==b.actor_name || d.detail!==b.reason ||
   p.actor_source!=='AUTHENTICATED_PRINCIPAL' || p.assignment_id!==b.request_id ||
   p.criterion_id!==b.criterion_id || p.dvp_item_id!==b.dvp_item_id || p.supersedes_id!==b.supersedes_id ||
   p.previous_dvp_item_id!==c.predecessor.dvp_item_id || p.previous_action!==c.predecessor.action)return null;
 const {request_id,...original}=b;
 return projectAcceptanceCorrectionReceipt({operation:c.operation,request_id,target:c.target,audit_event_no:acceptanceCorrectionEvent(c),
   result:{id:request_id,...original,previous_dvp_item_id:p.previous_dvp_item_id,previous_action:p.previous_action,
     change_request_id:d.entity_id,request_no:c.target}},c);
}

