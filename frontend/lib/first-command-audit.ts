import { record, exactFields, firstCommandEvent, projectFirstReceipt, type FirstCommand, type FirstReceipt } from './first-command-transport';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function id(value: unknown): string | null { return typeof value === 'string' && uuid.test(value) ? value.toLowerCase() : null; }
function backendTime(value: string | number | null): string | null {
  if (value === null) return null;
  const iso = new Date(value as string).toISOString();
  return iso.endsWith('.000Z') ? iso.slice(0, -5) + '+00:00' : iso.slice(0, -1) + '000+00:00';
}
/** Match the existing backend's atomically committed request fingerprint, never current detail. */
export function projectFirstAudit(value: unknown, command: FirstCommand, principalId: string): FirstReceipt | null {
  const d = record(value), p = record(d?.payload), request = record(p?.request), b = command.body;
  if (!d || !p || !request || !id(d.id) || d.event_no !== firstCommandEvent(command) ||
      id(d.actor_principal_id) !== principalId.toLowerCase() || p.actor_source !== 'AUTHENTICATED_PRINCIPAL') return null;
  const expected: Record<string, unknown> = command.operation === 'snapshot' ? { release_id: command.target } :
    command.operation === 'actual' ? { deployment_no: command.target, actual_release_id: b.actual_release_id,
      actual_snapshot_id: b.actual_snapshot_id, deployed_at: backendTime(b.deployed_at),
      expected_version: b.expected_version, correction_reason: b.correction_reason } :
    { deployment_no: command.target, batch_no: b.batch_no, changeover_id: b.changeover_id,
      started_at: backendTime(b.started_at), note: b.note };
  if (!exactFields(request, Object.keys(expected)) || !Object.entries(expected).every(([key, item]) => request[key] === item)) return null;
  let result: Record<string, unknown>;
  if (command.operation === 'snapshot') {
    if (d.event_type !== 'SNAPSHOT' || d.entity_type !== 'RELEASE_SNAPSHOT' || d.action !== 'FROZEN' ||
        id(d.entity_id) !== b.request_id || p.release_id !== command.target) return null;
    result = { id: b.request_id, release_id: command.target, status: 'FROZEN', snapshot_no: d.entity_ref,
      snapshot_number: p.snapshot_number, content_hash: p.content_hash };
  } else if (command.operation === 'actual') {
    const before = record(p.before), after = record(p.after);
    if (d.event_type !== 'DEPLOYMENT' || d.entity_type !== 'DEPLOYMENT' ||
        !['ACTUAL_REPORTED', 'ACTUAL_CORRECTED'].includes(d.action as string) ||
        d.entity_ref !== command.target || !id(d.entity_id) || !before || !after ||
        before.actual_version !== b.expected_version || p.correction_reason !== b.correction_reason) return null;
    result = { id: id(d.entity_id), deployment_no: command.target, status: after.status,
      actual_release_id: after.actual_release_id, actual_snapshot_id: after.actual_snapshot_id,
      actual_version: after.actual_version };
  } else {
    if (d.event_type !== 'PRODUCTION_BATCH' || d.entity_type !== 'PRODUCTION_BATCH' || d.action !== 'STARTED' ||
        id(d.entity_id) !== b.request_id || d.entity_ref !== b.batch_no || p.deployment_no !== command.target ||
        !id(p.deployment_id) || !id(p.authorization_id) || p.changeover_id !== b.changeover_id) return null;
    result = { id: b.request_id, batch_no: b.batch_no, deployment_no: command.target, status: p.status,
      release_id: p.release_id, snapshot_id: p.snapshot_id };
  }
  return projectFirstReceipt({ operation: command.operation, request_id: b.request_id, target: command.target,
    audit_event_no: firstCommandEvent(command), result }, command);
}
