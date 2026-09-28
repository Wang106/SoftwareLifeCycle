import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import { DeploymentDetail, deploymentFallback } from '../../../lib/production';

export const dynamic = 'force-dynamic';

function dateLabel(value: string | null) {
  return value ? new Date(value).toISOString().slice(0, 10) : '—';
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const apiData = await apiGet<DeploymentDetail>('/api/v1/deployments/' + encodeURIComponent(id));
  const deployment = apiData || deploymentFallback;
  const changeover = deployment.changeovers[0];

  return <>
    <div className="top"><div><div className="eyebrow">DEPLOYMENT · {deployment.deployment_no}</div><h1>{deployment.project?.name || 'Project'} · {deployment.site?.name || 'Site'} / {deployment.line?.name || 'Line'}</h1><p className="muted">Production deployment trace for ASR {deployment.expected.version || '—'}</p></div><span className={'status ' + (deployment.status === 'MATCH' ? 'pass' : 'warning')}>{deployment.status}</span></div>
    <div className="grid2">
      <section className="panel"><h2>Authorization & actual</h2><div className="kv"><span>Authorization</span><b>{deployment.authorization?.authorization_no || '—'}</b><span>Expected</span><b>ASR {deployment.expected.version || '—'} / {deployment.expected.snapshot_no || '—'}</b><span>Actual</span><b>{deployment.actual ? `ASR ${deployment.actual.version} / ${deployment.actual.snapshot_no}` : 'Not reported'}</b><span>Result</span><b>{deployment.status}</b></div></section>
      <section className="panel"><h2>Changeover</h2>{changeover ? <div className="kv"><span>Record</span><b>{changeover.changeover_no}</b><span>From</span><b>ASR {changeover.from_version}</b><span>To</span><b>ASR {changeover.to_version}</b><span>Status</span><b>{changeover.status}</b></div> : <div className="notice">No software changeover recorded.</div>}</section>
    </div>
    <section className="panel"><h2>Batch history</h2><table><thead><tr><th>Batch</th><th>Start</th><th>Software</th><th>Snapshot</th><th>Authorization</th><th>Status</th></tr></thead><tbody>{deployment.batches.length ? deployment.batches.map(batch => <tr key={batch.id}><td><b>{batch.batch_no}</b></td><td>{dateLabel(batch.started_at)}</td><td>ASR {batch.release_version}</td><td>{batch.snapshot_no}</td><td>{deployment.authorization?.authorization_no || '—'}</td><td><span className={'status ' + (batch.status === 'ACTIVE' ? 'pass' : '')}>{batch.status}</span></td></tr>) : <tr><td colSpan={6}>No production batch recorded.</td></tr>}</tbody></table></section>
    <section className="panel"><h2>End-to-end provenance</h2><div className="impactpath"><Link href="/approvals/APR-0121"><b>APR-0121</b></Link><i>→</i><b>RD-0081</b><i>→</i><Link href="/distribution/deliveries/new"><b>DP-0226</b></Link><i>→</i><b>DIST-0326</b><i>→</i><Link href="/distribution/authorizations/new"><b>{deployment.authorization?.authorization_no || 'PA pending'}</b></Link><i>→</i><b>{deployment.deployment_no}</b><i>→</i><b>{changeover?.changeover_no || 'Changeover pending'}</b><i>→</i><b>{deployment.batches[0]?.batch_no || 'Batch pending'}</b></div></section>
    {!apiData && <p className="datasource">Demo fallback active · deployment API will load automatically when backend is configured.</p>}
  </>;
}
