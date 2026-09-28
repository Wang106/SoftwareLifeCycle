import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

export const dynamic = 'force-dynamic';

type AuthorizationDetail = {
  id: string;
  authorization_no: string;
  status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string } | null;
  customer: { id: string; code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  distribution: { id: string; distribution_no: string; status: string; package_no: string | null } | null;
  site_code: string;
  line_code: string;
  purpose: string;
  restriction_note: string | null;
  approved_at: string | null;
};

const fallback: AuthorizationDetail = {
  id: 'demo-pa-0081',
  authorization_no: 'PA-0081',
  status: 'APPROVED',
  release: { id: 'demo-asr', version: '2.3.4', type: 'APPLICATION' },
  snapshot: { id: 'demo-snap', snapshot_no: 'SNAP-008', content_hash: '5c8e7f4191af' },
  customer: { id: 'demo-customer', code: 'CUS-001', name: 'Customer A' },
  project: { id: 'demo-project', code: 'PRJ-X', name: 'Project X' },
  distribution: { id: 'demo-dist', distribution_no: 'DIST-0326', status: 'ACKNOWLEDGED', package_no: 'DP-0226' },
  site_code: 'FACTORY-A',
  line_code: 'LINE-2',
  purpose: 'PRODUCTION',
  restriction_note: 'PEX-0018: controlled initial production batch only while DVP-034 remains incomplete.',
  approved_at: null,
};

function displayCode(value: string) {
  return value.split('-').map(part => part.charAt(0) + part.slice(1).toLowerCase()).join(' ');
}

export default async function Page() {
  const apiData = await apiGet<AuthorizationDetail>('/api/v1/authorizations/PA-0081');
  const authorization = apiData || fallback;

  return <>
    <div className="top">
      <div>
        <div className="eyebrow">PRODUCTION GOVERNANCE · {authorization.authorization_no}</div>
        <h1>Production Authorization</h1>
        <p className="muted">Authorization is bound to the exact released snapshot and acknowledged distribution.</p>
      </div>
      <span className={'status ' + (authorization.status === 'APPROVED' ? 'pass' : 'warning')}>{authorization.status}</span>
    </div>

    <div className="grid2">
      <section className="panel">
        <h2>Authorized scope</h2>
        <div className="kv">
          <span>Customer</span><b>{authorization.customer?.name || '—'} · {authorization.customer?.code || '—'}</b>
          <span>Project</span><b>{authorization.project?.name || '—'} · {authorization.project?.code || '—'}</b>
          <span>Software</span><b>ASR {authorization.release?.version || '—'}</b>
          <span>Snapshot</span><b>{authorization.snapshot?.snapshot_no || '—'}</b>
          <span>Site</span><b>{displayCode(authorization.site_code)}</b>
          <span>Line</span><b>{displayCode(authorization.line_code)}</b>
        </div>
      </section>
      <section className="panel">
        <h2>Distribution prerequisite</h2>
        {authorization.distribution ? <div className="kv">
          <span>Delivery package</span><Link href="/distribution/deliveries/new"><b>{authorization.distribution.package_no || '—'}</b></Link>
          <span>Distribution</span><b>{authorization.distribution.distribution_no}</b>
          <span>Distribution status</span><b>{authorization.distribution.status}</b>
          <span>Purpose</span><b>{authorization.purpose}</b>
        </div> : <div className="notice">Legacy authorization: no distribution record is linked.</div>}
      </section>
    </div>

    <section className="panel">
      <h2>Restriction from PEX-0018</h2>
      <p>{authorization.restriction_note || 'No production restriction recorded.'}</p>
      <div className="notice">Authorization scope: controlled initial production batch only.</div>
    </section>

    <section className="panel">
      <h2>End-to-end authorization evidence</h2>
      <div className="impactpath">
        <b>APR-0121</b><i>→</i><b>RD-0081</b><i>→</i><b>{authorization.distribution?.package_no || 'DP pending'}</b><i>→</i><b>{authorization.distribution?.distribution_no || 'Distribution pending'}</b><i>→</i><b>{authorization.authorization_no}</b>
      </div>
      <code className="hash">{authorization.snapshot?.content_hash || '—'}</code>
    </section>

    <section className="panel">
      <h2>Expected vs actual software</h2>
      <table><thead><tr><th>Target</th><th>Expected</th><th>Actual</th><th>Status</th></tr></thead><tbody><tr>
        <td>{displayCode(authorization.site_code)} / {displayCode(authorization.line_code)}</td>
        <td>ASR {authorization.release?.version || '—'} · {authorization.snapshot?.snapshot_no || '—'}</td>
        <td>Not reported</td>
        <td><span className="status">UNKNOWN</span></td>
      </tr></tbody></table>
    </section>
    {!apiData && <p className="datasource">Demo fallback active · authorization API will load automatically when backend is configured.</p>}
  </>;
}
