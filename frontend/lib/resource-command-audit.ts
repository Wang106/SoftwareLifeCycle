import {record} from './first-command-transport';
import {validUuid} from './command-draft';
import {resourceDigest,resourceEvent,projectResourceReceipt,type ResourceCommand,type ResourceReceipt} from './resource-command-transport';
/** No current resource lookup or legacy-audit fallback: incomplete evidence remains unknown. */
export async function projectResourceAudit(value:unknown,command:ResourceCommand,principalId:string):Promise<ResourceReceipt|null> {
  const d=record(value),p=record(d?.payload),b=command.body;
  if(!d || !p || typeof d.id!=='string' || !validUuid(d.id) || !validUuid(principalId) ||
    d.event_no!==resourceEvent(command) || d.actor_principal_id!==principalId.toLowerCase() ||
    p.actor_source!=='AUTHENTICATED_PRINCIPAL' || d.event_type!=='RESOURCE_LINK' ||
    d.entity_type!=='RESOURCE_LINK' || d.action!=='REGISTER' || d.entity_id!==b.request_id ||
    d.entity_ref!==b.request_id || d.declared_actor_name!==b.actor_name || d.detail!==b.reason ||
    p.target_type!==b.entity_type || p.target_id!==command.target || p.location_kind!==b.location_kind ||
    p.request_digest_version!==1 || p.request_sha256!==await resourceDigest(command))return null;
  const {request_id,...original}=b;
  return projectResourceReceipt({operation:'resource',request_id,target:command.target,
    audit_event_no:resourceEvent(command),result:{id:request_id,entity_ref:p.target_ref,...original}},command);
}
