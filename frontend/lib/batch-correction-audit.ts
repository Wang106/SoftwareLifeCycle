import {record,exactFields} from './first-command-transport';
import {validUuid} from './command-draft';
import {productionTime} from './production-command-transport';
import {batchCorrectionEvent,projectBatchCorrectionReceipt,type BatchCorrectionCommand,type BatchCorrectionReceipt} from './batch-correction-transport';
const time = (v:unknown) => v === null?null:productionTime(v);
/** Match original immutable request, actor and batch; never infer success from current values. */
export function projectBatchCorrectionAudit(value:unknown,c:BatchCorrectionCommand,principalId:string):BatchCorrectionReceipt|null {
  const d=record(value),p=record(d?.payload),request=record(p?.request),before=record(p?.before),after=record(p?.after),b=c.body,ctx=c.context;
  if (!d || !p || !request || !before || !after || typeof d.id !== 'string' || !validUuid(d.id) || !validUuid(principalId) ||
      d.event_no !== batchCorrectionEvent(c) || d.actor_principal_id !== principalId.toLowerCase() || d.declared_actor_name !== null ||
      d.event_type !== 'PRODUCTION_BATCH' || d.entity_type !== 'PRODUCTION_BATCH' || d.entity_id !== ctx.batch_id ||
      d.entity_ref !== c.target.batch_no || d.action !== 'CORRECTED' || p.actor_source !== 'AUTHENTICATED_PRINCIPAL' ||
      p.correction_reason !== b.correction_reason || p.deployment_no !== c.target.deployment_no) return null;
  const expected={batch_no:c.target.batch_no,started_at:b.started_at,ended_at:b.ended_at,changeover_id:b.changeover_id,
    note:b.note,expected_revision:b.expected_revision,predecessor_id:b.predecessor_id,correction_reason:b.correction_reason};
  if (!exactFields(request,Object.keys(expected)) || Object.entries(expected).some(([k,v]) =>
      ['started_at','ended_at'].includes(k)?(request[k] !== null && !productionTime(request[k])) || time(request[k]) !== v:request[k] !== v)) return null;
  const expectedBefore={release_id:ctx.release_id,snapshot_id:ctx.snapshot_id,started_at:ctx.started_at,ended_at:ctx.ended_at,
    changeover_id:ctx.changeover_id,note:ctx.note};
  if (!exactFields(before,Object.keys(expectedBefore)) || Object.entries(expectedBefore).some(([k,v]) =>
      ['started_at','ended_at'].includes(k)?(before[k] !== null && !productionTime(before[k])) || time(before[k]) !== v:before[k] !== v)) return null;
  return projectBatchCorrectionReceipt({operation:c.operation,target:c.target,request_id:b.request_id,audit_event_no:batchCorrectionEvent(c),
    result:{batch_id:d.entity_id,batch_no:d.entity_ref,release_id:after.release_id,snapshot_id:after.snapshot_id,
      started_at:after.started_at,ended_at:after.ended_at,changeover_id:after.changeover_id,note:after.note,
      correction_reason:p.correction_reason,revision:b.expected_revision+1,predecessor_id:b.predecessor_id}},c);
}
