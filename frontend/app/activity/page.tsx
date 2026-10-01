
import { Localized, LocalizedAttributes } from "../../components/localized";
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
        <div className="eyebrow"><Localized>{"AUDIT & ACTIVITY"}</Localized></div>
        <h1><Localized>{"Activity"}</Localized></h1>
        <p className="muted"><Localized>{"Append-only domain history for formal lifecycle actions and operational events."}</Localized></p>
      </div>
      <span className="badge"><Localized>{"APPEND ONLY"}</Localized></span>
    </div>
    <div className="cards">
      <div className="card"><span className="muted"><Localized>{"EVENTS"}</Localized></span><div className="metric"><Localized>{catalog?.total ?? '—'}</Localized></div><small><Localized>{"All matching records"}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"EVENT TYPES"}</Localized></span><div className="metric"><Localized>{catalog ? Object.keys(catalog.event_type_counts).length : '—'}</Localized></div><small><Localized>{"Across matching history"}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"PAGE RECORDS"}</Localized></span><div className="metric"><Localized>{events?.length ?? '—'}</Localized></div><small><Localized>{"Offset "}</Localized><Localized>{offset}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"DATA SOURCE"}</Localized></span><div className="metric"><Localized>{events ? 'API' : '—'}</Localized></div><small><Localized>{"FastAPI audit ledger"}</Localized></small></div>
    </div>
    <section className="panel">
      <h2><Localized>{"Filter activity"}</Localized></h2>
      <form className="activityfilters" action="/activity" method="get">
        <label><Localized>{"Event type"}</Localized><LocalizedAttributes><input name="event_type" maxLength={50} defaultValue={eventType} placeholder="e.g. DEPLOYMENT" /></LocalizedAttributes></label>
        <label><Localized>{"Entity type"}</Localized><LocalizedAttributes><input name="entity_type" maxLength={80} defaultValue={entityType} placeholder="e.g. DEPLOYMENT" /></LocalizedAttributes></label>
        <label><Localized>{"Entity reference"}</Localized><LocalizedAttributes><input name="entity_ref" maxLength={120} defaultValue={entityRef} placeholder="e.g. DEP-0081" /></LocalizedAttributes></label>
        <label><Localized>{"Search"}</Localized><LocalizedAttributes><input name="q" maxLength={200} defaultValue={query.get('q') || ''} placeholder="Number, summary or actor" /></LocalizedAttributes></label>
        <label><Localized>{"Actor (exact)"}</Localized><input name="actor_name" maxLength={120} defaultValue={query.get('actor_name') || ''} /></label>
        <label><Localized>{"Action (exact)"}</Localized><input name="action" maxLength={80} defaultValue={query.get('action') || ''} /></label>
        <label><Localized>{"Entity UUID"}</Localized><input name="entity_id" defaultValue={query.get('entity_id') || ''} /></label>
        <label><Localized>{"Occurred from (inclusive)"}</Localized><LocalizedAttributes><input name="occurred_from" defaultValue={query.get('occurred_from') || ''} placeholder="2026-09-29T00:00:00Z" /></LocalizedAttributes></label>
        <label><Localized>{"Occurred before (exclusive)"}</Localized><LocalizedAttributes><input name="occurred_before" defaultValue={query.get('occurred_before') || ''} placeholder="2026-09-30T00:00:00Z" /></LocalizedAttributes></label>
        <label><Localized>{"Limit"}</Localized><select name="limit" defaultValue={limit}><option value="50"><Localized>{"50"}</Localized></option><option value="100"><Localized>{"100"}</Localized></option><option value="200"><Localized>{"200"}</Localized></option></select></label>
        <button type="submit"><Localized>{"Apply"}</Localized></button><Link href="/activity"><Localized>{"Clear"}</Localized></Link>
      </form>
    </section>
    <section className="panel">
      <h2><Localized>{"Audit events"}</Localized></h2>
      <Localized>{events?.length ? <div className="activitylist"><Localized>{events.map(event => {
        const href = eventHref(event);
        return <div className="activityitem" key={event.event_no}>
          <time><Localized>{displayTime(event.occurred_at)}</Localized></time>
          <span className="activitytype"><Localized>{event.event_type}</Localized></span>
          <div><b><Link href={`/activity/${encodeURIComponent(event.event_no)}`}><Localized>{event.summary}</Localized></Link></b>
            <small><Localized>{event.detail || event.action}</Localized><Localized>{" · "}</Localized><Localized>{event.actor_name}</Localized><Localized>{" · "}</Localized><Localized>{event.event_no}</Localized></small>
            <Localized>{href && <small><Link href={href}><Localized>{"View "}</Localized><Localized>{event.entity_ref}</Localized><Localized>{" →"}</Localized></Link></small>}</Localized>
          </div>
        </div>;
      })}</Localized></div> : <p className="muted"><Localized>{events ? 'No audit events match these filters.' : 'Audit API unavailable or filters invalid. Use timezone-qualified timestamps and ensure the start precedes the end.'}</Localized></p>}</Localized>
      <Localized>{catalog && <><p className="muted"><Localized>{Object.entries(catalog.event_type_counts).map(([name, count]) => `${name}: ${count}`).join(' · ') || 'No matching event types'}</Localized></p>
        <div className="actions"><Localized>{offset > 0 && <Link href={pageHref(Math.max(0, offset - limit))}><Localized>{"← Previous"}</Localized></Link>}</Localized>
          <Localized>{catalog.next_offset !== null && catalog.next_offset <= 100000 && <Link href={pageHref(catalog.next_offset)}><Localized>{"Next →"}</Localized></Link>}</Localized></div></>}</Localized>
    </section>
    <section className="panel">
      <h2><Localized>{"Audit principles"}</Localized></h2>
      <div className="grid2">
        <div className="notice"><Localized>{"Formal records are append-only at database level. Corrections create a new event instead of rewriting history."}</Localized></div>
        <div className="notice"><Localized>{"Actor names are recorded declarations, not verified user identities. Directory rows show summaries; exact profiles preserve the full recorded payload."}</Localized></div>
      </div>
    </section>
  </>;
}
