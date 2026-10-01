import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import { DeploymentDetail } from '../../../lib/production';

export const dynamic = 'force-dynamic';

function dateLabel(value: string | null) {
  return value ? new Date(value).toISOString().slice(0, 10) : '—';
}

type Provenance = {
  authorization: { authorization_no: string; status: string } | null;
  distribution: { distribution_no: string; status: string } | null;
  delivery: { package_no: string; revision: number; status: string; release_id: string; snapshot_id: string } | null;
  release_decisions: { decision_no: string; decision: string; approval_no: string | null }[];
};

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = '/api/v1/deployments/' + encodeURIComponent(id);
  const [deployment, provenance] = await Promise.all([apiGet<DeploymentDetail>(path), apiGet<Provenance>(path + '/provenance')]);
  if (!deployment) return <section className="panel"><h1>Deployment unavailable</h1><p className="muted">This deployment was not found or the API is unavailable. No substitute production data is shown.</p><Link href="/deployments">← All deployments</Link></section>;
  const changeover = deployment.changeovers[0];

  return <>
    <div className="top"><div><div className="eyebrow">DEPLOYMENT · {deployment.deployment_no}</div><h1>{deployment.project?.name || 'Project'} · {deployment.site?.name || 'Site'} / {deployment.line?.name || 'Line'}</h1><p className="muted">Production deployment trace for ASR {deployment.expected.version || '—'}</p></div><span className={'status ' + (deployment.status === 'MATCH' ? 'pass' : 'warning')}>{deployment.status}</span></div>
    <p><Link href={`/commands?${new URLSearchParams({operation: "actual", target: deployment.deployment_no})}`}>Prepare actual-software request →</Link> · <Link href={`/commands?${new URLSearchParams({operation: "batch", target: deployment.deployment_no})}`}>Prepare Batch request →</Link></p>
    <p><Link href={`/commands?${new URLSearchParams({operation: 'changeover', target: deployment.deployment_no})}`}>Prepare changeover history →</Link> · <Link href={`/production/changeovers?deployment_id=${deployment.id}`}>Review all recorded changeovers →</Link></p>
    <div className="grid2">
      <section className="panel"><h2>Authorization & actual</h2><div className="kv"><span>Authorization</span><b>{deployment.authorization?.authorization_no || '—'}</b><span>Production line UUID</span><b>{deployment.line?.id || 'Unavailable'}</b><span>Expected release UUID</span><b>{deployment.expected.release_id || 'Unavailable'}</b><span>Expected</span><b>ASR {deployment.expected.version || '—'} / {deployment.expected.snapshot_no || '—'}</b><span>Actual</span><b>{deployment.actual ? `ASR ${deployment.actual.version} / ${deployment.actual.snapshot_no}` : 'Not reported'}</b><span>Result</span><b>{deployment.status}</b><span>Actual report version</span><b>{deployment.actual_version ?? "Unavailable — refresh before preparing a report"}</b></div></section>
      <section className="panel"><h2>Changeover</h2>{changeover ? <div className="kv"><span>Record</span><b>{changeover.changeover_no}</b><span>From</span><b>ASR {changeover.from_version}</b><span>To</span><b>ASR {changeover.to_version}</b><span>Status</span><b>{changeover.status}</b></div> : <div className="notice">No software changeover recorded.</div>}</section>
    </div>
    <section className="panel"><h2>Batch history</h2><table><thead><tr><th>Batch</th><th>Start</th><th>Software</th><th>Snapshot</th><th>Authorization</th><th>Status</th></tr></thead><tbody>{deployment.batches.length ? deployment.batches.map(batch => <tr key={batch.id}><td><Link href={`/production/batches/${encodeURIComponent(batch.batch_no)}`}><b>{batch.batch_no}</b></Link></td><td>{dateLabel(batch.started_at)}</td><td>ASR {batch.release_version}</td><td>{batch.snapshot_no}</td><td>{deployment.authorization?.authorization_no || '—'}</td><td><span className={'status ' + (batch.status === 'ACTIVE' ? 'pass' : '')}>{batch.status}</span></td></tr>) : <tr><td colSpan={6}>No production batch recorded.</td></tr>}</tbody></table></section>
    <section className="panel"><h2>End-to-end provenance</h2>{provenance ? <>
      <div className="kv"><span>Release decisions</span><b>{provenance.release_decisions.length ? provenance.release_decisions.map(row => <span key={row.decision_no}>{row.approval_no ? <Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}>{row.approval_no}</Link> : 'Approval unavailable'} → {row.decision_no} ({row.decision})<br /></span>) : 'None recorded for the delivered release and snapshot'}</b>
      <span>Delivery</span><b>{provenance.delivery ? `${provenance.delivery.package_no} Rev${provenance.delivery.revision} · ${provenance.delivery.status}` : 'No linked delivery'}</b>
      <span>Distribution</span><b>{provenance.distribution ? `${provenance.distribution.distribution_no} · ${provenance.distribution.status}` : 'No linked distribution'}</b>
      <span>Authorization</span><b>{provenance.authorization ? `${provenance.authorization.authorization_no} · ${provenance.authorization.status}` : 'No linked authorization'}</b>
      <span>Deployment</span><b>{deployment.deployment_no} · {deployment.status}</b>
      <span>Changeovers</span><b>{deployment.changeovers.length ? deployment.changeovers.map(row => row.changeover_no).join(', ') : 'None recorded'}</b>
      <span>Batches</span><b>{deployment.batches.length ? deployment.batches.map(row => row.batch_no).join(', ') : 'None recorded'}</b></div>
    </> : <p className="muted">Provenance API unavailable.</p>}</section>
    <p className="datasource"><Link href="/deployments">← All deployments</Link></p>
  </>;
}
