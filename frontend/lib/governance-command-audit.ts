import { record, exactFields } from './first-command-transport';
import { governanceEvent, projectGovernanceReceipt, type GovernanceCommand, type GovernanceReceipt } from './governance-command-transport';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const id = (value: unknown): string | null => typeof value === 'string' && uuid.test(value) ? value.toLowerCase() : null;
/** The declared actor, step and all request fields must match the original trusted actor-bound audit. */
export function projectGovernanceAudit(value: unknown, command: GovernanceCommand, principalId: string): GovernanceReceipt | null {
  const d = record(value), p = record(d?.payload), request = record(p?.request), b = command.body;
  if (!d || !p || !request || !id(d.id) || !id(principalId) || d.event_no !== governanceEvent(command) ||
      id(d.actor_principal_id) !== principalId.toLowerCase() || p.actor_source !== 'AUTHENTICATED_PRINCIPAL') return null;
  const { request_id, ...fields } = b;
  const expected = { approval_no:command.target, ...fields };
  if (!exactFields(request,Object.keys(expected)) || !Object.entries(expected).every(([key,item]) => request[key] === item)) return null;
  let result: Record<string, unknown>;
  if (command.operation === 'approval') {
    if (d.event_type !== 'APPROVAL' || d.entity_type !== 'APPROVAL_REQUEST' || d.action !== b.action ||
        d.entity_ref !== command.target || !id(d.entity_id) || p.approval_action_id !== request_id ||
        p.step_id !== b.expected_step_id || p.after_step_status !== b.action) return null;
    result = { approval_id:id(d.entity_id), approval_no:command.target, approval_action_id:request_id,
      step_id:p.step_id, action:d.action, step_status:p.after_step_status, approval_status:p.after_status,
      step_order:p.step_order, role_name:p.role_name, target_type:p.target_type, target_id:p.target_id, snapshot_id:p.snapshot_id };
  } else {
    if (d.event_type !== 'RELEASE' || d.entity_type !== 'RELEASE_DECISION' || d.action !== 'DECISION_RECORDED' ||
        id(d.entity_id) !== request_id || d.entity_ref !== b.decision_no || p.approval_no !== command.target ||
        p.decision !== b.decision || p.readiness_status !== b.readiness_status) return null;
    result = { id:request_id, approval_id:p.approval_id, approval_no:p.approval_no, decision_no:d.entity_ref,
      decision:p.decision, readiness_status:p.readiness_status, release_id:p.release_id,
      snapshot_id:p.snapshot_id, snapshot_no:p.snapshot_no, content_hash:p.content_hash };
  }
  return projectGovernanceReceipt({ operation:command.operation, request_id, target:command.target,
    audit_event_no:governanceEvent(command), result },command);
}
