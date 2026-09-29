import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type AuthorizationDetail = {
  id: string; authorization_no: string; status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string } | null;
  customer: { id: string; code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  distribution: { id: string; distribution_no: string; status: string; package_no: string | null; package_revision: number | null } | null;
  site_code: string; line_code: string; purpose: string;
  batch_limit: number | null; restriction_note: string | null; approved_at: string | null;
  deployments: { deployment_no: string; status: string; actual_release_matches: boolean | null; actual_snapshot_matches: boolean | null }[];
  batches: { batch_no: string; status: string }[];
};

export default async function Page({ params }: { params: Promise<{ authorizationNo: string }> }) {
  const { authorizationNo } = await params;
  const authorization = await apiGet<AuthorizationDetail>(`/api/v1/authorizations/${encodeURIComponent(authorizationNo)}`);
  if (!authorization) return <section className="panel"><h1>Authorization unavailable</h1>
    <p className="muted">This authorization was not found or the API is unavailable.</p>
    <Link href="/distribution/authorizations">← All authorizations</Link></section>;

  const distribution = authorization.distribution;
  const deliveryHref = distribution?.package_no && distribution.package_revision
    ? `/distribution/deliveries/${encodeURIComponent(distribution.package_no)}/${distribution.package_revision}` : null;
  return <>
    <div className="top"><div><div className="eyebrow">PRODUCTION GOVERNANCE</div><h1>{authorization.authorization_no}</h1>
      <p className="muted">Authorization for a specified release, snapshot, customer, site and line.</p></div>
      <span className={'status ' + (authorization.status === 'APPROVED' ? 'pass' : 'warning')}>{authorization.status}</span></div>
    <div className="grid2">
      <section className="panel"><h2>Authorized scope</h2><div className="kv">
        <span>Customer</span><b>{authorization.customer ? `${authorization.customer.name} · ${authorization.customer.code}` : '—'}</b>
        <span>Project</span><b>{authorization.project ? `${authorization.project.name} · ${authorization.project.code}` : '—'}</b>
        <span>Release</span><b>{authorization.release ? <Link href={authorization.release.type === 'APPLICATION' ? `/releases/application/${authorization.release.id}` : '/releases/application'}>{authorization.release.type} {authorization.release.version}</Link> : '—'}</b>
        <span>Snapshot</span><b>{authorization.snapshot?.snapshot_no || '—'}</b>
        <span>Site / line</span><b>{authorization.site_code} / {authorization.line_code}</b>
        <span>Purpose</span><b>{authorization.purpose}</b>
      </div></section>
      <section className="panel"><h2>Distribution prerequisite</h2>
        {distribution ? <div className="kv">
          <span>Delivery</span><b>{deliveryHref ? <Link href={deliveryHref}>{distribution.package_no} Rev{distribution.package_revision}</Link> : 'Missing delivery link'}</b>
          <span>Distribution</span><b><Link href={`/distribution/distributions/${encodeURIComponent(distribution.distribution_no)}`}>{distribution.distribution_no}</Link></b>
          <span>Distribution status</span><b>{distribution.status}</b>
        </div> : <p className="muted">No distribution linked to this authorization.</p>}
        <code className="hash">{authorization.snapshot?.content_hash || 'No snapshot hash'}</code>
      </section>
    </div>
    <section className="panel"><h2>Restrictions and batch usage</h2>
      <p>{authorization.restriction_note || 'No restriction note recorded.'}</p>
      <div className="kv"><span>Approved at</span><b>{authorization.approved_at ? new Date(authorization.approved_at).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : '—'}</b>
        <span>Batch limit</span><b>{authorization.batch_limit ?? 'No limit recorded'}</b>
        <span>Recorded batches</span><b>{authorization.batches.length}</b>
        <span>Unfilled slots (count only)</span><b>{authorization.batch_limit === null ? 'No limit recorded' : Math.max(0, authorization.batch_limit - authorization.batches.length)}</b>
      </div>
    </section>
    <section className="panel tablewrap"><h2>Actual deployments</h2>
      {authorization.deployments.length ? <table><thead><tr><th>Deployment</th><th>Status</th><th>Actual release matches</th><th>Actual snapshot matches</th></tr></thead>
        <tbody>{authorization.deployments.map(row => <tr key={row.deployment_no}>
          <td><Link href={`/deployments/${encodeURIComponent(row.deployment_no)}`}><b>{row.deployment_no}</b></Link></td>
          <td>{row.status}</td><td>{row.actual_release_matches === null ? 'Not reported' : row.actual_release_matches ? 'Yes' : 'No'}</td>
          <td>{row.actual_snapshot_matches === null ? 'Not reported' : row.actual_snapshot_matches ? 'Yes' : 'No'}</td>
        </tr>)}</tbody></table> : <p className="muted">No deployment recorded for this authorization.</p>}
    </section>
    <section className="panel"><h2>Production batches</h2>
      {authorization.batches.length ? <div className="searchresults">{authorization.batches.map(row => <div key={row.batch_no}><b>{row.batch_no}</b><span> · {row.status}</span></div>)}</div>
        : <p className="muted">No production batch recorded.</p>}
    </section>
    <p className="datasource"><Link href="/distribution/authorizations">← All authorizations</Link></p>
  </>;
}
