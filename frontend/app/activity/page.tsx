import Link from 'next/link';

import { apiGet } from '../../lib/api';
import { AuditEvent, displayTime, eventHref } from '../../lib/activity';

type Filters = { event_type?: string; entity_type?: string; entity_ref?: string; limit?: string };

export default async function Page({ searchParams }: { searchParams: Promise<Filters> }) {
  const params = await searchParams;
  const eventType = (params.event_type || '').trim().slice(0, 50).toUpperCase();
  const entityType = (params.entity_type || '').trim().slice(0, 80).toUpperCase();
  const entityRef = (params.entity_ref || '').trim().slice(0, 120);
  const limit = [50, 100, 200].includes(Number(params.limit)) ? Number(params.limit) : 50;
  const query = new URLSearchParams({ limit: String(limit) });
  if (eventType) query.set('event_type', eventType);
  if (entityType) query.set('entity_type', entityType);
  if (entityRef) query.set('entity_ref', entityRef);
  const events = await apiGet<AuditEvent[]>(`/api/v1/activity?${query}`);
  const eventTypes = new Set(events?.map(event => event.event_type)).size;
  const actors = new Set(events?.map(event => event.actor_name)).size;

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
      <div className="card"><span className="muted">EVENTS</span><div className="metric">{events?.length ?? '—'}</div><small>Matching records, up to {limit}</small></div>
      <div className="card"><span className="muted">EVENT TYPES</span><div className="metric">{events ? eventTypes : '—'}</div><small>In current results</small></div>
      <div className="card"><span className="muted">ACTORS</span><div className="metric">{events ? actors : '—'}</div><small>In current results</small></div>
      <div className="card"><span className="muted">DATA SOURCE</span><div className="metric">{events ? 'API' : '—'}</div><small>FastAPI audit ledger</small></div>
    </div>
    <section className="panel">
      <h2>Filter activity</h2>
      <form className="activityfilters" action="/activity" method="get">
        <label>Event type<input name="event_type" maxLength={50} defaultValue={eventType} placeholder="e.g. DEPLOYMENT" /></label>
        <label>Entity type<input name="entity_type" maxLength={80} defaultValue={entityType} placeholder="e.g. DEPLOYMENT" /></label>
        <label>Entity reference<input name="entity_ref" maxLength={120} defaultValue={entityRef} placeholder="e.g. DEP-0081" /></label>
        <label>Limit<select name="limit" defaultValue={limit}><option value="50">50</option><option value="100">100</option><option value="200">200</option></select></label>
        <button type="submit">Apply</button><Link href="/activity">Clear</Link>
      </form>
    </section>
    <section className="panel">
      <h2>Audit events</h2>
      {events?.length ? <div className="activitylist">{events.map(event => {
        const href = eventHref(event);
        return <div className="activityitem" key={event.event_no}>
          <time>{displayTime(event.occurred_at)}</time>
          <span className="activitytype">{event.event_type}</span>
          <div><b><Link href={`/activity/${encodeURIComponent(event.event_no)}`}>{event.summary}</Link></b>
            <small>{event.detail || event.action} · {event.actor_name} · {event.event_no}</small>
            {href && <small><Link href={href}>View {event.entity_ref} →</Link></small>}
          </div>
        </div>;
      })}</div> : <p className="muted">{events ? 'No audit events match these filters.' : 'Audit API unavailable. Connect the backend to view formal history.'}</p>}
      {events?.length === limit && <p className="muted">Showing the first {limit} records. Narrow the filters to find older events.</p>}
    </section>
    <section className="panel">
      <h2>Audit principles</h2>
      <div className="grid2">
        <div className="notice">Formal records are append-only at database level. Corrections create a new event instead of rewriting history.</div>
        <div className="notice">Every event carries a stable number, actor, entity reference and timestamp for traceable review.</div>
      </div>
    </section>
  </>;
}
