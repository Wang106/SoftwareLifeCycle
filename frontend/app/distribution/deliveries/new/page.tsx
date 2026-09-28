import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

export const dynamic = 'force-dynamic';

type DeliveryDetail = {
  id: string;
  package_no: string;
  revision: number;
  status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string; status: string } | null;
  recipient: { type: string; code: string; name: string };
  purpose: string;
  created_by: string | null;
  items: {
    snapshot_artifact_id: string;
    filename: string;
    artifact_type: string;
    sha256: string;
    distribution_level: string;
    policy_decision: string;
    control_reference: string | null;
  }[];
  distributions: {
    id: string;
    distribution_no: string;
    status: string;
    sent_at: string | null;
    acknowledged_at: string | null;
  }[];
};

const fallback: DeliveryDetail = {
  id: 'demo-dp-0226',
  package_no: 'DP-0226',
  revision: 1,
  status: 'DISTRIBUTED',
  release: { id: 'demo-asr', version: '2.3.4', type: 'APPLICATION' },
  snapshot: { id: 'demo-snap', snapshot_no: 'SNAP-008', content_hash: '5c8e7f4191af', status: 'FROZEN' },
  recipient: { type: 'CUSTOMER', code: 'CUS-001', name: 'Customer A' },
  purpose: 'PRODUCTION',
  created_by: 'Release Manager',
  items: [
    { snapshot_artifact_id: 'hex', filename: 'CustomerA_BMS.hex', artifact_type: 'HEX', sha256: 'e3b0c44298fc', distribution_level: 'EXTERNAL', policy_decision: 'ALLOW', control_reference: null },
    { snapshot_artifact_id: 'a2l', filename: 'CustomerA_BMS.a2l', artifact_type: 'A2L', sha256: 'ca978112ca1b', distribution_level: 'CONTROLLED_EXTERNAL', policy_decision: 'APPROVAL_REQUIRED', control_reference: 'APR-0121' },
    { snapshot_artifact_id: 'dbc', filename: 'CustomerA.dbc', artifact_type: 'DBC', sha256: '3a6eb0790f39', distribution_level: 'EXTERNAL', policy_decision: 'ALLOW', control_reference: null },
  ],
  distributions: [{ id: 'demo-dist', distribution_no: 'DIST-0326', status: 'ACKNOWLEDGED', sent_at: null, acknowledged_at: null }],
};

export default async function Page() {
  const apiData = await apiGet<DeliveryDetail>('/api/v1/deliveries/DP-0226');
  const delivery = apiData || fallback;
  const allowed = delivery.items.filter(item => item.policy_decision === 'ALLOW').length;
  const approvalRequired = delivery.items.filter(item => item.policy_decision === 'APPROVAL_REQUIRED').length;
  const distribution = delivery.distributions[0];

  return <>
    <div className="top">
      <div>
        <div className="eyebrow">DISTRIBUTION · {delivery.package_no}</div>
        <h1>Delivery Package Rev{delivery.revision}</h1>
        <p className="muted">Recipient-specific content selected only from the released frozen snapshot.</p>
      </div>
      <span className={'status ' + (delivery.status === 'DISTRIBUTED' ? 'pass' : 'warning')}>{delivery.status}</span>
    </div>

    <div className="grid2">
      <section className="panel">
        <h2>Delivery context</h2>
        <div className="kv">
          <span>Recipient</span><b>{delivery.recipient.name} · {delivery.recipient.code}</b>
          <span>Purpose</span><b>{delivery.purpose}</b>
          <span>Release</span><b>ASR {delivery.release?.version || '—'}</b>
          <span>Snapshot</span><b>{delivery.snapshot?.snapshot_no || '—'} · {delivery.snapshot?.status || '—'}</b>
          <span>Created by</span><b>{delivery.created_by || '—'}</b>
        </div>
      </section>
      <section className="panel">
        <h2>Frozen policy result</h2>
        <div className="kv">
          <span>Included artifacts</span><b>{delivery.items.length}</b>
          <span>Allowed</span><b>{allowed}</b>
          <span>Approval required</span><b>{approvalRequired}</b>
          <span>Control reference</span><b>{approvalRequired ? 'APR-0121' : 'Not required'}</b>
        </div>
        <code className="hash">{delivery.snapshot?.content_hash || '—'}</code>
      </section>
    </div>

    <section className="panel tablewrap">
      <table>
        <thead><tr><th>Artifact</th><th>Type</th><th>Frozen SHA-256</th><th>Distribution level</th><th>Policy decision</th><th>Control</th></tr></thead>
        <tbody>{delivery.items.map(item => <tr key={item.snapshot_artifact_id}>
          <td><b>{item.filename}</b></td>
          <td>{item.artifact_type}</td>
          <td><code>{item.sha256.slice(0, 12)}…</code></td>
          <td>{item.distribution_level.replaceAll('_', ' ')}</td>
          <td><span className={'status ' + (item.policy_decision === 'ALLOW' ? 'pass' : 'warning')}>{item.policy_decision.replaceAll('_', ' ')}</span></td>
          <td>{item.control_reference || 'Policy rule'}</td>
        </tr>)}</tbody>
      </table>
    </section>

    <section className="panel">
      <h2>Distribution record</h2>
      {distribution ? <div className="kv">
        <span>Distribution</span><b>{distribution.distribution_no}</b>
        <span>Status</span><b>{distribution.status}</b>
        <span>Package</span><b>{delivery.package_no} Rev{delivery.revision}</b>
        <span>Recipient</span><b>{delivery.recipient.name}</b>
      </div> : <div className="notice">No distribution record has been created for this package.</div>}
    </section>

    <div className="nextbar">
      <span>{distribution?.distribution_no || 'Distribution pending'} does not itself authorize production use.</span>
      <Link className="button" href="/distribution/authorizations/new">Open PA-0081 →</Link>
    </div>
    {!apiData && <p className="datasource">Demo fallback active · distribution API will load automatically when backend is configured.</p>}
  </>;
}
