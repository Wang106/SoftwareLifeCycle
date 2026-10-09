import { record, exactFields } from './first-command-transport';
import { productionEvent, projectProductionReceipt, type ProductionCommand, type ProductionReceipt } from './production-command-transport';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const id = (value:unknown):string|null => typeof value === 'string' && uuid.test(value) ? value.toLowerCase() : null;
function backendTime(value:string|null):string|null {
  if (value === null) return null;
  const iso = new Date(value).toISOString();
  return iso.endsWith('.000Z') ? iso.slice(0,-5)+'+00:00' : iso.slice(0,-1)+'000+00:00';
}
/** Existing TestRelease audit uses original fields/declaration/detail, not a fabricated request fingerprint. */
export function projectProductionAudit(value:unknown, command:ProductionCommand, principalId:string):ProductionReceipt|null {
  const d = record(value), p = record(d?.payload), b = command.body;
  if (!d || !p || !id(d.id) || !id(principalId) || d.event_no !== productionEvent(command) ||
      id(d.actor_principal_id) !== principalId.toLowerCase() || p.actor_source !== 'AUTHENTICATED_PRINCIPAL' ||
      id(d.entity_id) !== b.request_id) return null;
  let result: Record<string,unknown>;
  if (command.operation === 'test-release') {
    if (d.event_type !== 'TEST_RELEASE' || d.entity_type !== 'TEST_RELEASE' || d.action !== 'CREATE_DRAFT' ||
        d.entity_ref !== b.test_release_no || d.declared_actor_name !== b.actor_name || d.detail !== b.reason ||
        p.release_id !== command.target || p.snapshot_id !== b.snapshot_id || p.purpose_scope !== b.purpose_scope) return null;
    result = { id:b.request_id, test_release_no:d.entity_ref, status:p.status, release_id:p.release_id,
      snapshot_id:p.snapshot_id, snapshot_no:p.snapshot_no, purpose_scope:p.purpose_scope, actor_name:d.declared_actor_name, reason:d.detail };
  } else {
    const request = record(p.request);
    const expected: Record<string,unknown> = command.operation === 'deployment' ?
      { deployment_no:b.deployment_no, authorization_id:command.target, production_line_id:b.production_line_id } :
      { deployment_no:command.target, changeover_no:b.changeover_no, from_release_id:b.from_release_id,
        changed_at:backendTime(b.changed_at), note:b.note };
    if (!request || !exactFields(request,Object.keys(expected)) ||
        !Object.entries(expected).every(([k,v])=>request[k]===v) || d.declared_actor_name !== null) return null;
    if (command.operation === 'deployment') {
      if (d.event_type !== 'DEPLOYMENT' || d.entity_type !== 'DEPLOYMENT' || d.action !== 'CREATED' || d.entity_ref !== b.deployment_no) return null;
      result = { id:b.request_id, deployment_no:d.entity_ref, status:p.status, authorization_id:p.authorization_id,
        production_line_id:p.production_line_id, expected_release_id:p.expected_release_id, expected_snapshot_id:p.expected_snapshot_id };
    } else {
      if (d.event_type !== 'CHANGEOVER' || d.entity_type !== 'SOFTWARE_CHANGEOVER' || d.action !== 'COMPLETED' || d.entity_ref !== b.changeover_no) return null;
      result = { id:b.request_id, changeover_no:d.entity_ref, status:p.status, deployment_id:p.deployment_id,
        deployment_no:p.deployment_no, authorization_id:p.authorization_id, from_release_id:p.from_release_id,
        to_release_id:p.to_release_id, changed_at:d.occurred_at, note:request.note };
    }
  }
  return projectProductionReceipt({ operation:command.operation, request_id:b.request_id, target:command.target,
    audit_event_no:productionEvent(command), result },command);
}
