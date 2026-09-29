import Link from 'next/link';
import { apiGet } from '../../lib/api';
import { DeploymentDetail } from '../../lib/production';

export const dynamic = 'force-dynamic';

export default async function Page() {
  const apiRows = await apiGet<DeploymentDetail[]>('/api/v1/deployments');
  const rows = apiRows || [];
  const matched = rows.filter(row => row.status === 'MATCH').length;
  const batchCount = rows.reduce((total, row) => total + row.batches.length, 0);

  return <>
    <div className="top"><div><div className="eyebrow">PRODUCTION TRACEABILITY</div><h1>Deployments & Batches</h1><p className="muted">Actual software use after release, distribution and authorization.</p></div><Link href="/production/batches">Batch catalog →</Link></div>
    <div className="cards">
      <div className="card"><span className="muted">ACTIVE DEPLOYMENTS</span><div className="metric">{rows.length}</div></div>
      <div className="card"><span className="muted">SOFTWARE MATCH</span><div className="metric">{matched} / {rows.length}</div></div>
      <div className="card"><span className="muted">MISMATCH / PENDING</span><div className="metric">{rows.length - matched}</div></div>
      <div className="card"><span className="muted">BATCHES</span><div className="metric">{batchCount}</div></div>
    </div>
    <section className="panel tablewrap"><table><thead><tr><th>Deployment</th><th>Project</th><th>Site / Line</th><th>Authorized</th><th>Actual</th><th>Status</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}>
      <td><Link href={'/deployments/' + row.deployment_no}><b>{row.deployment_no}</b></Link></td>
      <td>{row.project?.name || '—'}</td>
      <td>{row.site?.name || '—'} / {row.line?.name || '—'}</td>
      <td>ASR {row.expected.version || '—'} · {row.expected.snapshot_no || '—'}</td>
      <td>{row.actual ? `ASR ${row.actual.version} · ${row.actual.snapshot_no}` : 'Not reported'}</td>
      <td><span className={'status ' + (row.status === 'MATCH' ? 'pass' : 'warning')}>{row.status}</span></td>
    </tr>)}</tbody></table>{apiRows?.length === 0 && <p className="muted">No deployments recorded.</p>}</section>
    {!apiRows && <p className="datasource">Deployment API unavailable. No substitute records are shown.</p>}
  </>;
}
