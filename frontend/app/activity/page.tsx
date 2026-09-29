import Link from 'next/link';

import { apiGet } from '../../lib/api';


type AuditEvent = {
  id: string;
  event_no: string;
  event_type: string;
  action: string;
  entity_type: string;
  entity_ref: string;
  actor_name: string;
  summary: string;
  detail: string | null;
  payload: Record<string, string | number | null>;
  occurred_at: string;
};


const fallbackEvents: AuditEvent[] = [
  { id: '9', event_no: 'EVT-0009', event_type: 'BATCH', action: 'STARTED', entity_type: 'PRODUCTION_BATCH', entity_ref: 'PB-1005-A', actor_name: 'Production Operator', summary: 'PB-1005-A started', detail: 'Initial controlled production batch started under PA-0081.', payload: { deployment_no: 'DEP-0081' }, occurred_at: '2026-09-28T10:17:00Z' },
  { id: '8', event_no: 'EVT-0008', event_type: 'DEPLOYMENT', action: 'SOFTWARE_MATCHED', entity_type: 'DEPLOYMENT', entity_ref: 'DEP-0081', actor_name: 'Production Operator', summary: 'DEP-0081 software matched', detail: 'Actual release and snapshot match the production authorization.', payload: {}, occurred_at: '2026-09-28T10:07:00Z' },
  { id: '7', event_no: 'EVT-0007', event_type: 'AUTHORIZATION', action: 'APPROVED', entity_type: 'SOFTWARE_AUTHORIZATION', entity_ref: 'PA-0081', actor_name: 'Quality Manager', summary: 'PA-0081 approved', detail: 'Controlled initial production was authorized for Factory A / Line 2.', payload: {}, occurred_at: '2026-09-28T09:57:00Z' },
  { id: '6', event_no: 'EVT-0006', event_type: 'DISTRIBUTION', action: 'ACKNOWLEDGED', entity_type: 'DISTRIBUTION', entity_ref: 'DIST-0326', actor_name: 'Customer A', summary: 'DIST-0326 acknowledged', detail: 'Customer A acknowledged DP-0226 revision 1.', payload: {}, occurred_at: '2026-09-28T09:47:00Z' },
  { id: '5', event_no: 'EVT-0005', event_type: 'RELEASE', action: 'DECISION_RECORDED', entity_type: 'RELEASE_DECISION', entity_ref: 'RD-0081', actor_name: 'Release Manager', summary: 'RD-0081 released ASR 2.3.4', detail: 'Release decision recorded with the PEX-0018 restriction.', payload: {}, occurred_at: '2026-09-28T09:37:00Z' },
  { id: '4', event_no: 'EVT-0004', event_type: 'APPROVAL', action: 'APPROVED', entity_type: 'APPROVAL_REQUEST', entity_ref: 'APR-0121', actor_name: 'Release Manager', summary: 'APR-0121 approved', detail: 'All four approval steps completed for SNAP-008.', payload: {}, occurred_at: '2026-09-28T09:27:00Z' },
  { id: '3', event_no: 'EVT-0003', event_type: 'SNAPSHOT', action: 'FROZEN', entity_type: 'RELEASE_SNAPSHOT', entity_ref: 'SNAP-008', actor_name: 'Release Manager', summary: 'SNAP-008 frozen', detail: 'Release content, artifact hashes and distribution policy were frozen.', payload: {}, occurred_at: '2026-09-28T09:17:00Z' },
  { id: '2', event_no: 'EVT-0002', event_type: 'TEST', action: 'EXECUTION_RECORDED', entity_type: 'DVP_ITEM', entity_ref: 'DVP-032', actor_name: 'Test System', summary: 'DVP-032 execution #2 passed', detail: 'Retest passed on TR-0061 against SNAP-008.', payload: {}, occurred_at: '2026-09-28T09:07:00Z' },
  { id: '1', event_no: 'EVT-0001', event_type: 'CHANGE', action: 'STATUS_CHANGED', entity_type: 'SOFTWARE_CHANGE_REQUEST', entity_ref: 'SCR-142', actor_name: 'Software Lead', summary: 'SCR-142 moved to IN TEST', detail: 'CP-001 and CP-002 entered formal verification.', payload: {}, occurred_at: '2026-09-28T08:57:00Z' },
];


function eventHref(event: AuditEvent): string | null {
  if (event.entity_type === 'SOFTWARE_CHANGE_REQUEST') return `/changes/${event.entity_ref}`;
  if (event.entity_type === 'DVP_ITEM') return '/testing/dvp';
  if (event.entity_type === 'RELEASE_SNAPSHOT' || event.entity_type === 'RELEASE_DECISION') return '/releases/demo/passport';
  if (event.entity_type === 'APPROVAL_REQUEST') return `/approvals/${event.entity_ref}`;
  if (event.entity_type === 'DISTRIBUTION') return '/distribution/deliveries/new';
  if (event.entity_type === 'SOFTWARE_AUTHORIZATION') return '/distribution/authorizations/new';
  if (event.entity_type === 'DEPLOYMENT') return `/deployments/${event.entity_ref}`;
  if (event.entity_type === 'PRODUCTION_BATCH' && event.payload.deployment_no) return `/deployments/${event.payload.deployment_no}`;
  return null;
}


function displayTime(value: string): string {
  return `${value.slice(0, 16).replace('T', ' ')} UTC`;
}


export default async function Page() {
  const apiEvents = await apiGet<AuditEvent[]>('/api/v1/activity?limit=50');
  const events = apiEvents && apiEvents.length ? apiEvents : fallbackEvents;
  const eventTypes = new Set(events.map(event => event.event_type)).size;
  const actors = new Set(events.map(event => event.actor_name)).size;

  return <>
    <div className="top">
      <div>
        <div className="eyebrow">AUDIT & ACTIVITY</div>
        <h1>Activity</h1>
        <p className="muted">Append-only domain history for formal lifecycle actions and operational events.</p>
      </div>
      <span className="badge">APPEND ONLY</span>
    </div>
    <div className="cards">
      <div className="card"><span className="muted">EVENTS</span><div className="metric">{events.length}</div><small>Latest formal records</small></div>
      <div className="card"><span className="muted">EVENT TYPES</span><div className="metric">{eventTypes}</div><small>Lifecycle domains</small></div>
      <div className="card"><span className="muted">ACTORS</span><div className="metric">{actors}</div><small>People and systems</small></div>
      <div className="card"><span className="muted">DATA SOURCE</span><div className="metric">{apiEvents ? 'API' : 'DEMO'}</div><small>FastAPI audit ledger</small></div>
    </div>
    <section className="panel">
      <div className="activitylist">{events.map(event => {
        const href = eventHref(event);
        const title = href ? <Link href={href}>{event.summary}</Link> : event.summary;
        return <div className="activityitem" key={event.event_no}>
          <time>{displayTime(event.occurred_at)}</time>
          <span className="activitytype">{event.event_type}</span>
          <div><b>{title}</b><small>{event.detail || event.action} · {event.actor_name} · {event.event_no}</small></div>
        </div>;
      })}</div>
    </section>
    <section className="panel">
      <h2>Audit principles</h2>
      <div className="grid2">
        <div className="notice">Formal records are append-only at database level. Corrections create a new event instead of rewriting history.</div>
        <div className="notice">Every event carries a stable number, actor, entity reference and timestamp for traceable review.</div>
      </div>
    </section>
    {!apiEvents && <p className="datasource">Demo fallback active · audit API will load automatically when the backend is configured.</p>}
  </>;
}
