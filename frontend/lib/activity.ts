export type AuditEvent = {
  id: string;
  event_no: string;
  event_type: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_ref: string;
  actor_name: string;
  summary: string;
  detail: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
};

export function eventHref(event: AuditEvent): string | null {
  if (event.entity_type === 'SOFTWARE_CHANGE_REQUEST') return `/changes/${encodeURIComponent(event.entity_ref)}`;
  if (event.entity_type === 'DVP_ITEM') return '/testing/dvp';
  if (event.entity_type === 'RELEASE_SNAPSHOT' || event.entity_type === 'RELEASE_DECISION') return '/releases/application';
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
