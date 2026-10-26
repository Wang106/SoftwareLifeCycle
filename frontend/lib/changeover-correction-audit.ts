import {record,exactFields} from './first-command-transport';
import {validUuid} from './command-draft';
import {productionTime} from './production-command-transport';
import {changeoverCorrectionEvent,projectChangeoverCorrectionReceipt,type ChangeoverCorrectionCommand,type ChangeoverCorrectionReceipt} from './changeover-correction-transport';
/** Original immutable audit only: parent, actor, exact request and before/after facts. */
export function projectChangeoverCorrectionAudit(value:unknown,c:ChangeoverCorrectionCommand,principalId:string):ChangeoverCorrectionReceipt|null {
  const d=record(value),p=record(d?.payload),request=record(p?.request),before=record(p?.before),after=record(p?.after),b=c.body,ctx=c.context;
  if (!d || !p || !request || !before || !after || typeof d.id !== 'string' || !validUuid(d.id) || !validUuid(principalId) ||
      d.event_no !== changeoverCorrectionEvent(c) || d.actor_principal_id !== principalId.toLowerCase() || d.declared_actor_name !== null ||
      d.event_type !== 'CHANGEOVER' || d.entity_type !== 'SOFTWARE_CHANGEOVER' || d.entity_id !== ctx.changeover_id ||
      d.entity_ref !== c.target.changeover_no || d.action !== 'CORRECTED' || p.actor_source !== 'AUTHENTICATED_PRINCIPAL' ||
      p.correction_reason !== b.correction_reason || p.deployment_no !== c.target.deployment_no) return null;
  const expected={changeover_no:c.target.changeover_no,from_release_id:b.from_release_id,changed_at:b.changed_at,
    note:b.note,expected_revision:b.expected_revision,predecessor_id:b.predecessor_id,correction_reason:b.correction_reason};
  if (!exactFields(request,Object.keys(expected)) || Object.entries(expected).some(([k,v]) =>
      k === 'changed_at'?productionTime(request[k]) !== v:request[k] !== v)) return null;
  const expectedBefore={from_release_id:ctx.from_release_id,to_release_id:ctx.to_release_id,changed_at:ctx.changed_at,note:ctx.note};
  if (!exactFields(before,Object.keys(expectedBefore)) || Object.entries(expectedBefore).some(([k,v]) =>
      k === 'changed_at'?(before[k] === null ? null : productionTime(before[k])) !== v || (before[k] !== null && !productionTime(before[k])):before[k] !== v)) return null;
  return projectChangeoverCorrectionReceipt({operation:c.operation,target:c.target,request_id:b.request_id,audit_event_no:changeoverCorrectionEvent(c),
    result:{changeover_id:d.entity_id,changeover_no:d.entity_ref,from_release_id:after.from_release_id,to_release_id:after.to_release_id,
      changed_at:after.changed_at,note:after.note,correction_reason:p.correction_reason,
      revision:b.expected_revision+1,predecessor_id:b.predecessor_id}},c);
}
