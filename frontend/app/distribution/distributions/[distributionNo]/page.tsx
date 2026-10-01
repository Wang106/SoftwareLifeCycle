
import { Localized, LocalizedAttributes } from "../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type DistributionDetail = {
  id: string; distribution_no: string; status: string; recipient_type: string; recipient_code: string;
  sent_at: string | null; acknowledged_at: string | null; note: string | null;
  delivery: { id: string; package_no: string; revision: number; purpose: string } | null;
  release_version: string | null; snapshot_no: string | null;
  history_counts: { authorizations: number };
  notice: string;
};

function displayTime(value: string | null): string {
  return value ? `${new Date(value).toISOString().slice(0, 16).replace('T', ' ')} UTC` : '—';
}

export default async function Page({ params }: { params: Promise<{ distributionNo: string }> }) {
  const { distributionNo } = await params;
  const record = await apiGet<DistributionDetail>(`/api/v1/distributions/${encodeURIComponent(distributionNo)}/profile`);
  if (!record) return <section className="panel"><h1><Localized>{"Distribution unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"This distribution was not found or the API is unavailable."}</Localized></p>
    <Link href="/distribution/distributions"><Localized>{"← All distributions"}</Localized></Link></section>;

  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"DISTRIBUTION"}</Localized></div><h1><Localized>{record.distribution_no}</Localized></h1>
      <p className="muted"><Localized>{"Recipient acknowledgment and linked production authorizations."}</Localized></p></div>
      <span className={'status ' + (record.status === 'ACKNOWLEDGED' ? 'pass' : 'warning')}><Localized>{record.status}</Localized></span></div>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Package and recipient"}</Localized></h2><div className="kv">
        <span><Localized>{"Distribution UUID"}</Localized></span><b><Localized>{record.id}</Localized></b>
        <span><Localized>{"Delivery"}</Localized></span><b><Localized>{record.delivery ? <Link href={`/distribution/deliveries/${encodeURIComponent(record.delivery.package_no)}/${record.delivery.revision}`}><Localized>{record.delivery.package_no}</Localized><Localized>{" Rev"}</Localized><Localized>{record.delivery.revision}</Localized></Link> : 'Missing delivery link'}</Localized></b>
        <span><Localized>{"Release version"}</Localized></span><b><Localized>{record.release_version || '—'}</Localized></b>
        <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{record.snapshot_no || '—'}</Localized></b>
        <span><Localized>{"Recipient"}</Localized></span><b><Localized>{record.recipient_type}</Localized><Localized>{" · "}</Localized><Localized>{record.recipient_code}</Localized></b>
        <span><Localized>{"Purpose"}</Localized></span><b><Localized>{record.delivery?.purpose || '—'}</Localized></b>
      </div></section>
      <section className="panel"><h2><Localized>{"Delivery timeline"}</Localized></h2><div className="kv">
        <span><Localized>{"Sent"}</Localized></span><b><Localized>{displayTime(record.sent_at)}</Localized></b>
        <span><Localized>{"Acknowledged"}</Localized></span><b><Localized>{displayTime(record.acknowledged_at)}</Localized></b>
        <span><Localized>{"Note"}</Localized></span><b><Localized>{record.note || '—'}</Localized></b>
      </div></section>
    </div>
    <section className="panel tablewrap"><h2><Localized>{"Linked production authorizations"}</Localized></h2>
      <p><Link href={`/commands?${new URLSearchParams({operation: 'authorization', target: record.id})}`}><Localized>{"Prepare draft authorization for this distribution →"}</Localized></Link></p>
      <p><Link href={`/distribution/authorizations?${new URLSearchParams({distribution_id: record.id})}`}><Localized>{record.history_counts.authorizations}</Localized><Localized>{" recorded authorizations →"}</Localized></Link></p>
      <p className="muted"><Localized>{record.notice}</Localized></p>
      <p className="muted"><Localized>{"Acknowledgment alone does not authorize production use."}</Localized></p>
    </section>
    <p className="datasource"><Link href="/distribution/distributions"><Localized>{"← All distributions"}</Localized></Link></p>
  <p><Link href={`/activity?${new URLSearchParams({entity_type: 'DISTRIBUTION', entity_id: record.id})}`}><Localized>{"Recorded audit events →"}</Localized></Link></p></>;
}
