import {record} from './first-command-transport';
import {validUuid} from './command-draft';
import {evidenceEvent,evidenceReferenceDigest,projectEvidenceReceipt,type EvidenceCommand,type EvidenceReceipt} from './evidence-command-transport';
/** Bind original actor, target, body and actual historical payload; no current-object fallback. */
export async function projectEvidenceAudit(value:unknown,command:EvidenceCommand,principalId:string):Promise<EvidenceReceipt|null> {
  const d=record(value),p=record(d?.payload),b=command.body;
  if(!d || !p || typeof d.id!=='string' || !validUuid(d.id) || !validUuid(principalId) ||
    d.event_no!==evidenceEvent(command) || d.actor_principal_id!==principalId.toLowerCase() ||
    p.actor_source!=='AUTHENTICATED_PRINCIPAL' || d.entity_ref!==command.target ||
    d.declared_actor_name!==b.actor_name || d.detail!==b.reason)return null;
  let context:Record<string,unknown>;
  if(command.operation==='impact') {
    if(d.event_type!=='ISSUE_IMPACT' || d.entity_type!=='Issue' || d.action!=='ASSESS' ||
      p.assessment_id!==b.request_id || p.release_id!==b.release_id || p.snapshot_id!==b.snapshot_id ||
      p.decision!==b.decision || p.evidence_ref_digest_version!==1 ||
      p.evidence_ref_sha256!==await evidenceReferenceDigest(b.evidence_ref))return null;
    context={issue_id:d.entity_id,issue_no:command.target,snapshot_no:p.snapshot_no};
  } else {
    if(d.event_type!=='ACCEPTANCE_DVP' || d.entity_type!=='SoftwareChangeRequest' || d.action!=='ASSIGN' ||
      p.assignment_id!==b.request_id || p.criterion_id!==b.criterion_id || p.dvp_item_id!==b.dvp_item_id)return null;
    context={change_request_id:d.entity_id,request_no:command.target};
  }
  const {request_id,...original}=b;
  return projectEvidenceReceipt({operation:command.operation,request_id,target:command.target,
    audit_event_no:evidenceEvent(command),result:{id:request_id,...original,...context}},command);
}
