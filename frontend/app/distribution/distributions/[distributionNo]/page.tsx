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
  if (!record) return <section className="panel"><h1>Distribution unavailable</h1>
    <p className="muted">This distribution was not found or the API is unavailable.</p>
    <Link href="/distribution/distributions">← All distributions</Link></section>;

  return <>
    <div className="top"><div><div className="eyebrow">DISTRIBUTION</div><h1>{record.distribution_no}</h1>
      <p className="muted">Recipient acknowledgment and linked production authorizations.</p></div>
      <span className={'status ' + (record.status === 'ACKNOWLEDGED' ? 'pass' : 'warning')}>{record.status}</span></div>
    <div className="grid2">
      <section className="panel"><h2>Package and recipient</h2><div className="kv">
        <span>Distribution UUID</span><b>{record.id}</b>
        <span>Delivery</span><b>{record.delivery ? <Link href={`/distribution/deliveries/${encodeURIComponent(record.delivery.package_no)}/${record.delivery.revision}`}>{record.delivery.package_no} Rev{record.delivery.revision}</Link> : 'Missing delivery link'}</b>
        <span>Release version</span><b>{record.release_version || '—'}</b>
        <span>Snapshot</span><b>{record.snapshot_no || '—'}</b>
        <span>Recipient</span><b>{record.recipient_type} · {record.recipient_code}</b>
        <span>Purpose</span><b>{record.delivery?.purpose || '—'}</b>
      </div></section>
      <section className="panel"><h2>Delivery timeline</h2><div className="kv">
        <span>Sent</span><b>{displayTime(record.sent_at)}</b>
        <span>Acknowledged</span><b>{displayTime(record.acknowledged_at)}</b>
        <span>Note</span><b>{record.note || '—'}</b>
      </div></section>
    </div>
    <section className="panel tablewrap"><h2>Linked production authorizations</h2>
      <p><Link href={`/commands?${new URLSearchParams({operation: 'authorization', target: record.id})}`}>Prepare draft authorization for this distribution →</Link></p>
      <p><Link href={`/distribution/authorizations?${new URLSearchParams({distribution_id: record.id})}`}>{record.history_counts.authorizations} recorded authorizations →</Link></p>
      <p className="muted">{record.notice}</p>
      <p className="muted">Acknowledgment alone does not authorize production use.</p>
    </section>
    <p className="datasource"><Link href="/distribution/distributions">← All distributions</Link></p>
  <p><Link href={`/activity?${new URLSearchParams({entity_type: 'DISTRIBUTION', entity_id: record.id})}`}>Recorded audit events →</Link></p></>;
}
