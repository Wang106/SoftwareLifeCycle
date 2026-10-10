import {record} from './first-command-transport';
import {validUuid} from './command-draft';
import {evidenceReferenceDigest} from './evidence-command-transport';
import {impactCorrectionEvent,projectImpactCorrectionReceipt,type ImpactCorrectionCommand,type ImpactCorrectionReceipt} from './impact-correction-transport';
/** Original authenticated supersession, including predecessor and nullable evidence digest. */
export async function projectImpactCorrectionAudit(value:unknown,c:ImpactCorrectionCommand,principalId:string):Promise<ImpactCorrectionReceipt|null> {
 const d=record(value),p=record(d?.payload),b=c.body;
 if(!d||!p||typeof d.id!=='string'||!validUuid(d.id)||!validUuid(principalId)||
   d.event_no!==impactCorrectionEvent(c)||d.actor_principal_id!==principalId.toLowerCase()||
   d.event_type!=='ISSUE_IMPACT'||d.entity_type!=='Issue'||d.entity_ref!==c.target||
   d.action!=='SUPERSEDE'||d.declared_actor_name!==b.actor_name||d.detail!==b.reason||
   p.actor_source!=='AUTHENTICATED_PRINCIPAL'||p.assessment_id!==b.request_id||p.release_id!==b.release_id||
   p.snapshot_id!==b.snapshot_id||p.decision!==b.decision||p.supersedes_id!==b.supersedes_id||
   p.previous_decision!==c.predecessor.decision||p.correction_reason!==b.correction_reason||
   p.evidence_ref_digest_version!==1||p.evidence_ref_sha256!==await evidenceReferenceDigest(b.evidence_ref))return null;
 const {request_id,...original}=b;
 return projectImpactCorrectionReceipt({operation:c.operation,request_id,target:c.target,audit_event_no:impactCorrectionEvent(c),
   result:{id:request_id,...original,previous_decision:p.previous_decision,issue_id:d.entity_id,
     issue_no:c.target,snapshot_no:p.snapshot_no}},c);
}

