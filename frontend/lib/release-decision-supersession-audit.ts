import {record,exactFields} from './first-command-transport';
import {validUuid} from './command-draft';
import {releaseDecisionSupersessionEvent,projectReleaseDecisionSupersessionReceipt,
  type ReleaseDecisionSupersessionCommand,type ReleaseDecisionSupersessionReceipt} from './release-decision-supersession-transport';
export function projectReleaseDecisionSupersessionAudit(value:unknown,c:ReleaseDecisionSupersessionCommand,principalId:string):ReleaseDecisionSupersessionReceipt|null{
  const d=record(value),p=record(d?.payload),q=record(p?.request),b=c.body,x=c.predecessor;
  if(!d||!p||!q||typeof d.id!=='string'||!validUuid(d.id)||!validUuid(principalId)||
    d.event_no!==releaseDecisionSupersessionEvent(c)||d.actor_principal_id!==principalId.toLowerCase()||
    d.event_type!=='RELEASE'||d.entity_type!=='RELEASE_DECISION'||d.entity_id!==b.request_id||
    d.entity_ref!==b.decision_no||d.action!=='DECISION_SUPERSEDED'||d.declared_actor_name!==b.decided_by||
    d.detail!==b.notes||p.actor_source!=='AUTHENTICATED_PRINCIPAL'||p.decision!==b.decision||
    p.readiness_status!==b.readiness_status||p.release_id!==x.release_id||p.snapshot_id!==x.snapshot_id||
    p.supersedes_id!==x.id||p.correction_reason!==b.correction_reason||!validUuid(p.approval_id as string)||
    p.approval_no!==c.target||typeof p.snapshot_no!=='string'||typeof p.content_hash!=='string'||
    !exactFields(q,['approval_no','decision_no','decided_by','readiness_status','decision','notes','supersedes_id','correction_reason'])||
    Object.entries({approval_no:c.target,decision_no:b.decision_no,decided_by:b.decided_by,readiness_status:b.readiness_status,
      decision:b.decision,notes:b.notes,supersedes_id:x.id,correction_reason:b.correction_reason}).some(([k,v])=>q[k]!==v))return null;
  return projectReleaseDecisionSupersessionReceipt({operation:c.operation,request_id:b.request_id,target:c.target,
    audit_event_no:releaseDecisionSupersessionEvent(c),result:{id:b.request_id,approval_id:p.approval_id,
      approval_no:c.target,decision_no:b.decision_no,decision:b.decision,readiness_status:b.readiness_status,
      release_id:x.release_id,snapshot_id:x.snapshot_id,snapshot_no:p.snapshot_no,content_hash:p.content_hash,
      supersedes_id:x.id,correction_reason:b.correction_reason}},c);
}
