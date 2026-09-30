import Link from 'next/link';

import { apiGet } from '../../lib/api';
import { AuditEvent, displayTime, eventHref } from '../../lib/activity';

type Filters = Record<string, string | undefined>;
type Catalog = { items: AuditEvent[]; total: number; event_type_counts: Record<string, number>; next_offset: number | null };

export default async function Page({ searchParams }: { searchParams: Promise<Filters> }) {
  const params = await searchParams;
  const eventType = (params.event_type || '').trim().slice(0, 50).toUpperCase();
  const entityType = (params.entity_type || '').trim().slice(0, 80);
  const entityRef = (params.entity_ref || '').trim().slice(0, 120);
  const limit = [50, 100, 200].includes(Number(params.limit)) ? Number(params.limit) : 50;
  const query = new URLSearchParams({ limit: String(limit) });
  if (eventType) query.set('event_type', eventType);
  if (entityType) query.set('entity_type', entityType);
  if (entityRef) query.set('entity_ref', entityRef);
  const offset = /^\d+$/.test(params.offset || '') && Number(params.offset) <= 100000 ? Number(params.offset) : 0;
  query.set('offset', String(offset));
  for (const [name, length] of [['q', 200], ['actor_name', 120], ['action', 80]] as const) {
    const value = (params[name] || '').trim().slice(0, length);
    if (value) query.set(name, value);
  }
  const entityId = params.entity_id || '';
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(entityId)) query.set('entity_id', entityId);
  for (const name of ['occurred_from', 'occurred_before']) {
    const value = params[name] || '';
    if (value && value.length <= 40) query.set(name, value);
  }
  const catalog = await apiGet<Catalog>(`/api/v1/audit/events?${query}`);
  const events = catalog?.items;
  const pageHref = (value: number) => { const next = new URLSearchParams(query); next.set('offset', String(value)); return `/activity?${next}`; };

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
      <div className="card"><span className="muted">EVENTS</span><div className="metric">{catalog?.total ?? '—'}</div><small>All matching records</small></div>
      <div className="card"><span className="muted">EVENT TYPES</span><div className="metric">{catalog ? Object.keys(catalog.event_type_counts).length : '—'}</div><small>Across matching history</small></div>
      <div className="card"><span className="muted">PAGE RECORDS</span><div className="metric">{events?.length ?? '—'}</div><small>Offset {offset}</small></div>
      <div className="card"><span className="muted">DATA SOURCE</span><div className="metric">{events ? 'API' : '—'}</div><small>FastAPI audit ledger</small></div>
    </div>
    <section className="panel">
      <h2>Filter activity</h2>
      <form className="activityfilters" action="/activity" method="get">
        <label>Event type<input name="event_type" maxLength={50} defaultValue={eventType} placeholder="e.g. DEPLOYMENT" /></label>
        <label>Entity type<input name="entity_type" maxLength={80} defaultValue={entityType} placeholder="e.g. DEPLOYMENT" /></label>
        <label>Entity reference<input name="entity_ref" maxLength={120} defaultValue={entityRef} placeholder="e.g. DEP-0081" /></label>
        <label>Search<input name="q" maxLength={200} defaultValue={query.get('q') || ''} placeholder="Number, summary or actor" /></label>
        <label>Actor (exact)<input name="actor_name" maxLength={120} defaultValue={query.get('actor_name') || ''} /></label>
        <label>Action (exact)<input name="action" maxLength={80} defaultValue={query.get('action') || ''} /></label>
        <label>Entity UUID<input name="entity_id" defaultValue={query.get('entity_id') || ''} /></label>
        <label>Occurred from (inclusive)<input name="occurred_from" defaultValue={query.get('occurred_from') || ''} placeholder="2026-09-29T00:00:00Z" /></label>
        <label>Occurred before (exclusive)<input name="occurred_before" defaultValue={query.get('occurred_before') || ''} placeholder="2026-09-30T00:00:00Z" /></label>
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
      })}</div> : <p className="muted">{events ? 'No audit events match these filters.' : 'Audit API unavailable or filters invalid. Use timezone-qualified timestamps and ensure the start precedes the end.'}</p>}
      {catalog && <><p className="muted">{Object.entries(catalog.event_type_counts).map(([name, count]) => `${name}: ${count}`).join(' · ') || 'No matching event types'}</p>
        <div className="actions">{offset > 0 && <Link href={pageHref(Math.max(0, offset - limit))}>← Previous</Link>}
          {catalog.next_offset !== null && catalog.next_offset <= 100000 && <Link href={pageHref(catalog.next_offset)}>Next →</Link>}</div></>}
    </section>
    <section className="panel">
      <h2>Audit principles</h2>
      <div className="grid2">
        <div className="notice">Formal records are append-only at database level. Corrections create a new event instead of rewriting history.</div>
        <div className="notice">Actor names are recorded declarations, not verified user identities. Directory rows show summaries; exact profiles preserve the full recorded payload.</div>
      </div>
    </section>
  </>;
}
