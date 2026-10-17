import {record} from './first-command-transport';
import {validUuid} from './command-draft';
import {evidenceReferenceDigest} from './evidence-command-transport';
import {impactWithdrawalEvent,projectImpactWithdrawalReceipt,type ImpactWithdrawalCommand,type ImpactWithdrawalReceipt} from './impact-withdrawal-transport';

export async function projectImpactWithdrawalAudit(value:unknown,c:ImpactWithdrawalCommand,principalId:string):Promise<ImpactWithdrawalReceipt|null>{
  const d=record(value),p=record(d?.payload),b=c.body;
  if(!d||!p||typeof d.id!=='string'||!validUuid(d.id)||!validUuid(principalId)||d.event_no!==impactWithdrawalEvent(c)||
    d.actor_principal_id!==principalId.toLowerCase()||d.event_type!=='ISSUE_IMPACT'||d.entity_type!=='Issue'||d.entity_ref!==c.target||
    d.action!=='WITHDRAW'||d.declared_actor_name!==b.actor_name||d.detail!==b.reason||p.actor_source!=='AUTHENTICATED_PRINCIPAL'||
    p.assessment_id!==b.request_id||p.release_id!==b.release_id||p.snapshot_id!==b.snapshot_id||p.decision!==null||
    p.supersedes_id!==b.supersedes_id||p.previous_decision!==c.predecessor.decision||p.correction_reason!==b.correction_reason||
    p.after_withdrawal_id!==null||p.history_action!=='WITHDRAW'||typeof p.context_seq!=='number'||!Number.isSafeInteger(p.context_seq)||p.context_seq<1||
    p.evidence_ref_digest_version!==1||p.evidence_ref_sha256!==await evidenceReferenceDigest(null)||typeof p.snapshot_no!=='string')return null;
  return projectImpactWithdrawalReceipt({operation:c.operation,request_id:b.request_id,target:c.target,audit_event_no:impactWithdrawalEvent(c),result:{id:b.request_id,action:'WITHDRAW',context_seq:p.context_seq,after_withdrawal_id:null,decision:null,evidence_ref:null,superseded_by_id:null,release_id:b.release_id,snapshot_id:b.snapshot_id,supersedes_id:b.supersedes_id,actor_name:b.actor_name,reason:b.reason,correction_reason:b.correction_reason,previous_decision:p.previous_decision,issue_id:d.entity_id,issue_no:c.target,snapshot_no:p.snapshot_no}},c);
}
