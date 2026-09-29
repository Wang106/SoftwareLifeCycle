import Link from 'next/link';

import { apiGet } from '../../../lib/api';
import { AuditEvent, displayTime, eventHref } from '../../../lib/activity';

export default async function Page({ params }: { params: Promise<{ event_no: string }> }) {
  const { event_no } = await params;
  const event = await apiGet<AuditEvent>(`/api/v1/activity/${encodeURIComponent(event_no)}`);
  const href = event && eventHref(event);
  return <>
    <div className="top"><div><div className="eyebrow">AUDIT & ACTIVITY</div><h1>{event?.event_no || 'Audit event'}</h1>
      <p className="muted">Formal append-only event record</p></div><Link href="/activity">← Back to activity</Link></div>
    {event ? <section className="panel">
      <h2>{event.summary}</h2>
      <p>{event.detail || event.action}</p>
      <dl className="auditdetail">
        <div><dt>Event type</dt><dd>{event.event_type} · {event.action}</dd></div>
        <div><dt>Entity</dt><dd>{event.entity_type} · {event.entity_ref}{href && <> · <Link href={href}>View record →</Link></>}</dd></div>
        <div><dt>Actor</dt><dd>{event.actor_name}</dd></div>
        <div><dt>Occurred at</dt><dd>{displayTime(event.occurred_at)}</dd></div>
        <div><dt>Recorded at</dt><dd>{displayTime(event.created_at)}</dd></div>
        <div><dt>Entity ID</dt><dd>{event.entity_id || '—'}</dd></div>
      </dl>
      <h3>Structured details</h3>
      <pre className="auditpayload">{JSON.stringify(event.payload || {}, null, 2)}</pre>
    </section> : <section className="panel"><h2>Event unavailable</h2><p className="muted">The record could not be found or the audit API is unavailable.</p></section>}
  </>;
}
