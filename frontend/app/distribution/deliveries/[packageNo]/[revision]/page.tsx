import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type DeliveryDetail = {
  id: string; package_no: string; revision: number; status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string; status: string } | null;
  recipient: { type: string; code: string; name: string };
  purpose: string; created_by: string | null;
  items: { snapshot_artifact_id: string; filename: string; artifact_type: string; sha256: string;
    distribution_level: string; policy_decision: string; control_reference: string | null }[];
  distributions: { id: string; distribution_no: string; status: string; sent_at: string | null; acknowledged_at: string | null }[];
};

export default async function Page({ params }: { params: Promise<{ packageNo: string; revision: string }> }) {
  const { packageNo, revision } = await params;
  const number = Number(revision);
  const delivery = Number.isSafeInteger(number) && number > 0
    ? await apiGet<DeliveryDetail>(`/api/v1/deliveries/${encodeURIComponent(packageNo)}/revisions/${number}`)
    : null;
  if (!delivery) return <section className="panel"><h1>Delivery unavailable</h1>
    <p className="muted">This package revision was not found or the delivery API is unavailable.</p>
    <Link href="/distribution/deliveries">← All deliveries</Link></section>;

  const allowed = delivery.items.filter(item => item.policy_decision === 'ALLOW').length;
  const approvalRequired = delivery.items.filter(item => item.policy_decision === 'APPROVAL_REQUIRED').length;
  const controls = [...new Set(delivery.items.map(item => item.control_reference).filter(Boolean))];
  return <>
    <div className="top"><div><div className="eyebrow">DELIVERY · {delivery.package_no}</div>
      <h1>Delivery Package Rev{delivery.revision}</h1>
      <p className="muted">Artifacts and policy decisions recorded for this exact revision.</p></div>
      <span className={'status ' + (delivery.status === 'DISTRIBUTED' ? 'pass' : 'warning')}>{delivery.status}</span></div>
    <div className="grid2">
      <section className="panel"><h2>Delivery context</h2><div className="kv">
        <span>Exact package UUID</span><b>{delivery.id}</b>
        <span>Recipient type</span><b>{delivery.recipient.type}</b>
        <span>Recipient</span><b>{delivery.recipient.name} · {delivery.recipient.code}</b>
        <span>Purpose</span><b>{delivery.purpose}</b>
        <span>Release</span><b>{delivery.release ? <Link href={delivery.release.type === 'APPLICATION' ? `/releases/application/${delivery.release.id}` : '/releases/application'}>{delivery.release.type} {delivery.release.version}</Link> : '—'}</b>
        <span>Snapshot</span><b>{delivery.snapshot?.snapshot_no || '—'} · {delivery.snapshot?.status || '—'}</b>
        <span>Created by</span><b>{delivery.created_by || '—'}</b>
      </div></section>
      <section className="panel"><h2>Frozen policy result</h2><div className="kv">
        <span>Included artifacts</span><b>{delivery.items.length}</b>
        <span>Allowed</span><b>{allowed}</b>
        <span>Approval required</span><b>{approvalRequired}</b>
        <span>Control references</span><b>{controls.length ? controls.join(', ') : 'None recorded'}</b>
      </div><code className="hash">{delivery.snapshot?.content_hash || '—'}</code></section>
    </div>
    <section className="panel tablewrap"><h2>Frozen artifact manifest</h2>
      <table><thead><tr><th>Artifact</th><th>Type</th><th>SHA-256</th><th>Distribution level</th><th>Policy decision</th><th>Control</th></tr></thead>
        <tbody>{delivery.items.map(item => <tr key={item.snapshot_artifact_id}>
          <td><b>{item.filename}</b><div className="muted">Snapshot artifact UUID: {item.snapshot_artifact_id}</div></td><td>{item.artifact_type}</td><td><code>{item.sha256}</code></td>
          <td>{item.distribution_level.replaceAll('_', ' ')}</td>
          <td><span className={'status ' + (item.policy_decision === 'ALLOW' ? 'pass' : 'warning')}>{item.policy_decision.replaceAll('_', ' ')}</span></td>
          <td>{item.control_reference || '—'}</td>
        </tr>)}</tbody></table>
      {delivery.items.length === 0 && <p className="muted">No artifacts recorded for this package revision.</p>}
    </section>
    <section className="panel"><h2>Distribution records</h2>
      <p><Link href={`/commands?${new URLSearchParams({operation: 'distribution', target: delivery.id})}`}>Prepare distribution for this exact package revision →</Link></p>
      <p className="muted">Copy the exact recipient values above; this entry does not preselect or certify a recipient.</p>
      {delivery.distributions.length ? <table><thead><tr><th>Distribution</th><th>Status</th><th>Sent</th><th>Acknowledged</th></tr></thead>
        <tbody>{delivery.distributions.map(row => <tr key={row.id}><td><Link href={`/distribution/distributions/${encodeURIComponent(row.distribution_no)}`}><b>{row.distribution_no}</b></Link></td><td>{row.status}</td>
          <td>{row.sent_at ? row.sent_at.slice(0, 16).replace('T', ' ') : '—'}</td>
          <td>{row.acknowledged_at ? row.acknowledged_at.slice(0, 16).replace('T', ' ') : '—'}</td></tr>)}</tbody></table>
        : <p className="muted">No distribution record for this package revision.</p>}
      <p className="muted">Distribution does not itself authorize production use.</p>
    </section>
    <p className="datasource"><Link href="/distribution/deliveries">← All deliveries</Link></p>
  <p><Link href={`/activity?${new URLSearchParams({entity_type: 'DELIVERY_PACKAGE', entity_id: delivery.id})}`}>Recorded audit events →</Link></p></>;
}
