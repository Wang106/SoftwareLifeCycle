import { record, exactFields } from './first-command-transport';
import { distributionEvent, projectDistributionReceipt, type DistributionCommand, type DistributionReceipt } from './distribution-command-transport';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const id = (value: unknown): string | null => typeof value === 'string' && uuid.test(value) ? value.toLowerCase() : null;
/** Fingerprint and receipt both bind the exact original actor, revision, recipient and authorization scope. */
export function projectDistributionAudit(value: unknown, command: DistributionCommand, principalId: string): DistributionReceipt | null {
  const d = record(value), p = record(d?.payload), request = record(p?.request), b = command.body;
  if (!d || !p || !request || !id(d.id) || !id(principalId) || d.event_no !== distributionEvent(command) ||
      id(d.actor_principal_id) !== principalId.toLowerCase() || p.actor_source !== 'AUTHENTICATED_PRINCIPAL') return null;
  const { request_id, ...expected } = b;
  if (!exactFields(request,Object.keys(expected)) || !Object.entries(expected).every(([key,item]) =>
      Array.isArray(item) ? Array.isArray(request[key]) && JSON.stringify(request[key]) === JSON.stringify(item) : request[key] === item)) return null;
  const number = command.operation === 'delivery' ? b.package_no : command.operation === 'distribution' ? b.distribution_no : b.authorization_no;
  const eventType = command.operation === 'delivery' ? 'DELIVERY' : command.operation === 'distribution' ? 'DISTRIBUTION' : 'AUTHORIZATION';
  const entityType = command.operation === 'delivery' ? 'DELIVERY_PACKAGE' : command.operation === 'distribution' ? 'DISTRIBUTION' : 'SOFTWARE_AUTHORIZATION';
  if (d.event_type !== eventType || d.entity_type !== entityType || d.action !== 'CREATED' ||
      id(d.entity_id) !== request_id || d.entity_ref !== number) return null;
  const common = { id:request_id, status:p.status, release_id:p.release_id, snapshot_id:p.snapshot_id };
  const result = command.operation === 'delivery' ? { ...common, package_no:d.entity_ref, revision:p.revision,
    snapshot_no:p.snapshot_no, decision_no:p.decision_no, approval_no:p.approval_no, recipient_type:p.recipient_type,
    recipient_code:p.recipient_code, purpose:p.purpose, snapshot_artifact_ids:p.snapshot_artifact_ids } :
    command.operation === 'distribution' ? { ...common, distribution_no:d.entity_ref, delivery_package_id:p.delivery_package_id,
      package_no:p.package_no, revision:p.revision, recipient_type:p.recipient_type, recipient_code:p.recipient_code } :
    { ...common, authorization_no:d.entity_ref, distribution_id:p.distribution_id, distribution_no:p.distribution_no,
      delivery_package_id:p.delivery_package_id, package_no:p.package_no, revision:p.revision,
      customer_id:p.customer_id, project_id:p.project_id, site_code:p.site_code, line_code:p.line_code, purpose:p.purpose,
      batch_limit:p.batch_limit, restriction_note:request.restriction_note };
  return projectDistributionReceipt({ operation:command.operation, request_id, target:command.target,
    audit_event_no:distributionEvent(command), result },command);
}
