
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';

import { apiGet } from '../../../lib/api';
import { AuditEvent, displayTime, eventHref } from '../../../lib/activity';

export default async function Page({ params }: { params: Promise<{ event_no: string }> }) {
  const { event_no } = await params;
  const event = await apiGet<AuditEvent>(`/api/v1/activity/${encodeURIComponent(event_no)}`);
  const href = event && eventHref(event);
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"AUDIT & ACTIVITY"}</Localized></div><h1><Localized>{event?.event_no || 'Audit event'}</Localized></h1>
      <p className="muted"><Localized>{"Formal append-only event record"}</Localized></p></div><Link href="/activity"><Localized>{"← Back to activity"}</Localized></Link></div>
    <Localized>{event ? <section className="panel">
      <h2><Localized>{event.summary}</Localized></h2>
      <p><Localized>{event.detail || event.action}</Localized></p>
      <dl className="auditdetail">
        <div><dt><Localized>{"Event type"}</Localized></dt><dd><Localized>{event.event_type}</Localized><Localized>{" · "}</Localized><Localized>{event.action}</Localized></dd></div>
        <div><dt><Localized>{"Entity"}</Localized></dt><dd><Localized>{event.entity_type}</Localized><Localized>{" · "}</Localized><Localized>{event.entity_ref}</Localized><Localized>{href && <><Localized>{" · "}</Localized><Link href={href}><Localized>{"View record →"}</Localized></Link></>}</Localized></dd></div>
        <div><dt><Localized>{"Actor"}</Localized></dt><dd><Localized>{event.actor_name}</Localized></dd></div>
        <div><dt><Localized>{"Occurred at"}</Localized></dt><dd><Localized>{displayTime(event.occurred_at)}</Localized></dd></div>
        <div><dt><Localized>{"Recorded at"}</Localized></dt><dd><Localized>{displayTime(event.created_at)}</Localized></dd></div>
        <div><dt><Localized>{"Entity ID"}</Localized></dt><dd><Localized>{event.entity_id || '—'}</Localized></dd></div>
      </dl>
      <p><Link href={`/activity?${new URLSearchParams({ entity_type: event.entity_type, ...(event.entity_id ? { entity_id: event.entity_id } : { entity_ref: event.entity_ref }) })}`}><Localized>{"History for this recorded entity →"}</Localized></Link></p>
      <p className="muted"><Localized>{"The actor name is a recorded declaration, not a verified identity. Links use the recorded reference; a missing business object does not remove this event."}</Localized></p>
      <h3><Localized>{"Structured details"}</Localized></h3>
      <pre className="auditpayload">{JSON.stringify(event.payload || {}, null, 2)}</pre>
    </section> : <section className="panel"><h2><Localized>{"Event unavailable"}</Localized></h2><p className="muted"><Localized>{"The record could not be found or the audit API is unavailable."}</Localized></p></section>}</Localized>
  </>;
}
