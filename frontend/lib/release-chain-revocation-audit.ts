import {record,exactFields} from './first-command-transport';
import {validUuid} from './command-draft';
import {releaseChainRevocationEvent,releaseChainRevocationAction,projectReleaseChainRevocationReceipt,
  type ReleaseChainRevocationCommand,type ReleaseChainRevocationReceipt} from './release-chain-revocation-transport';
export function projectReleaseChainRevocationAudit(value:unknown,c:ReleaseChainRevocationCommand,principalId:string):ReleaseChainRevocationReceipt|null{
  const d=record(value),p=record(d?.payload),q=record(p?.request),e=record(q?.expected_context),
    rc=record(p?.review_context),b=c.body,x=b.expected_context;
  if(!d||!p||!q||!e||!rc||typeof d.id!=='string'||!validUuid(d.id)||!validUuid(principalId)||
    d.event_no!==releaseChainRevocationEvent(c)||d.actor_principal_id!==principalId.toLowerCase()||
    d.event_type!=='RELEASE_CHAIN_REVOCATION'||d.entity_type!==c.target_kind||d.entity_id!==c.target_id||
    d.entity_ref!=='RCR-'+b.request_id.replaceAll('-','')||d.action!==releaseChainRevocationAction(c)||
    d.declared_actor_name!==null||d.detail!==b.reason||p.actor_source!=='AUTHENTICATED_PRINCIPAL'||
    p.revocation_id!==b.request_id||p.release_id!==x.release_id||p.snapshot_id!==x.snapshot_id||
    p.release_decision_id!==x.release_decision_id||p.reason!==b.reason||p.protocol_version!==1||
    !exactFields(q,['target_kind','target_id','reason','expected_context'])||q.target_kind!==c.target_kind||
    q.target_id!==c.target_id||q.reason!==b.reason||
    Object.entries(x).some(([k,v])=>e[k]!==v)||Object.entries(x).some(([k,v])=>rc[k]!==v))return null;
  return projectReleaseChainRevocationReceipt({operation:c.operation,request_id:b.request_id,target_kind:c.target_kind,
    target_id:c.target_id,audit_event_no:releaseChainRevocationEvent(c),result:{id:b.request_id,
      revocation_no:'RCR-'+b.request_id.replaceAll('-',''),target_kind:c.target_kind,release_id:x.release_id,
      snapshot_id:x.snapshot_id,release_decision_id:x.release_decision_id,reason:b.reason}},c);
}
