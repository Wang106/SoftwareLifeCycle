export type AuditEvent = {
  id: string;
  event_no: string;
  event_type: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_ref: string;
  related_release_id?: string | null;
  actor_name: string;
  summary: string;
  detail?: string | null;
  payload?: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
};

export function eventHref(event: AuditEvent): string | null {
  if (event.entity_type === 'RESOURCE_LINK' && event.entity_id) return `/resources/${encodeURIComponent(event.entity_id)}`;
  if (event.entity_type === 'TEST_RELEASE') return `/testing/releases/${encodeURIComponent(event.entity_ref)}`;
  if (['SOFTWARE_CHANGE_REQUEST', 'SoftwareChangeRequest'].includes(event.entity_type)) return `/changes/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'DVP_ITEM')
    return event.entity_id ? `/testing/dvp/${encodeURIComponent(event.entity_id)}` : '/testing/dvp';
  if (event.entity_type === 'RELEASE_SNAPSHOT') return `/snapshots/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'RELEASE_DECISION') return `/release-decisions/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'Issue' || event.entity_type === 'ISSUE') return `/issues/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'DELIVERY_PACKAGE') return `/distribution/deliveries/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'APPROVAL_REQUEST') return `/approvals/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'DISTRIBUTION') return `/distribution/distributions/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'SOFTWARE_AUTHORIZATION') return `/distribution/authorizations/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'DEPLOYMENT') return `/deployments/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'PRODUCTION_BATCH') return `/production/batches/${encodeURIComponent(event.entity_ref)}`;
  return null;
}

export function displayTime(value: string): string {
  return `${value.slice(0, 16).replace('T', ' ')} UTC`;
}
