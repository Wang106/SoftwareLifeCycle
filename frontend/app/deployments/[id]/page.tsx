import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import { DeploymentProfile } from '../../../lib/production';

export const dynamic = 'force-dynamic';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = '/api/v1/deployments/' + encodeURIComponent(id);
  const deployment = await apiGet<DeploymentProfile>(path + '/profile');
  if (!deployment) return <section className="panel"><h1>Deployment unavailable</h1><p className="muted">This deployment was not found or the API is unavailable. No substitute production data is shown.</p><Link href="/deployments">← All deployments</Link></section>;
  const provenance = deployment.provenance;
  const delivery = provenance.delivery;
  const historyQuery = new URLSearchParams({ deployment_id: deployment.id });

  return <>
    <div className="top"><div><div className="eyebrow">DEPLOYMENT · {deployment.deployment_no}</div><h1>{deployment.project?.name || 'Project'} · {deployment.site?.name || 'Site'} / {deployment.line?.name || 'Line'}</h1><p className="muted">Production deployment trace for ASR {deployment.expected.version || '—'}</p></div><span className={'status ' + (deployment.status === 'MATCH' ? 'pass' : 'warning')}>{deployment.status}</span></div>
    <p><Link href={`/commands?${new URLSearchParams({operation: "actual", target: deployment.deployment_no})}`}>Prepare actual-software request →</Link> · <Link href={`/commands?${new URLSearchParams({operation: "batch", target: deployment.deployment_no})}`}>Prepare Batch request →</Link></p>
    <p><Link href={`/commands?${new URLSearchParams({operation: 'changeover', target: deployment.deployment_no})}`}>Prepare changeover history →</Link> · <Link href={`/production/changeovers?deployment_id=${deployment.id}`}>Review all recorded changeovers →</Link></p>
    <div className="grid2">
      <section className="panel"><h2>Authorization & actual</h2><div className="kv"><span>Authorization</span><b>{deployment.authorization?.authorization_no || '—'}</b><span>Production line UUID</span><b>{deployment.line?.id || 'Unavailable'}</b><span>Expected release UUID</span><b>{deployment.expected.release_id || 'Unavailable'}</b><span>Expected</span><b>ASR {deployment.expected.version || '—'} / {deployment.expected.snapshot_no || '—'}</b><span>Actual</span><b>{deployment.actual ? `ASR ${deployment.actual.version} / ${deployment.actual.snapshot_no}` : 'Not reported'}</b><span>Stored status</span><b>{deployment.status}</b><span>Software observation</span><b>{deployment.software_observation}</b><span>Actual report version</span><b>{deployment.actual_version ?? "Unavailable — refresh before preparing a report"}</b></div></section>
      <section className="panel"><h2>Recorded history</h2><p className="muted">{deployment.notice}</p>
        <p><Link href={`/production/changeovers?${historyQuery}`}>{deployment.history_counts.changeovers} recorded changeovers →</Link></p>
        <p><Link href={`/production/batches?${historyQuery}`}>{deployment.history_counts.batches} recorded batches →</Link></p>
        <p className="muted">History opens in paginated catalogs scoped to this exact deployment. Counts are not production permissions or remaining authorization capacity.</p>
      </section>
    </div>
    <section className="panel"><h2>End-to-end provenance</h2>{provenance ? <>
      <div className="kv"><span>Release decision history</span><b>{delivery ? <Link href={`/release-decisions?${new URLSearchParams({release_id: delivery.release_id, snapshot_id: delivery.snapshot_id})}`}>Review decisions for exact delivered release/snapshot →</Link> : 'Delivery unavailable — no decision scope inferred'}</b>
      <span>Delivery</span><b>{provenance.delivery ? `${provenance.delivery.package_no} Rev${provenance.delivery.revision} · ${provenance.delivery.status}` : 'No linked delivery'}</b>
      <span>Distribution</span><b>{provenance.distribution ? `${provenance.distribution.distribution_no} · ${provenance.distribution.status}` : 'No linked distribution'}</b>
      <span>Authorization</span><b>{provenance.authorization ? `${provenance.authorization.authorization_no} · ${provenance.authorization.status}` : 'No linked authorization'}</b>
      <span>Deployment</span><b>{deployment.deployment_no} · {deployment.status}</b>
      <span>Changeovers</span><b>{deployment.history_counts.changeovers}</b>
      <span>Batches</span><b>{deployment.history_counts.batches}</b></div>
    </> : <p className="muted">Provenance API unavailable.</p>}</section>
    <p className="datasource"><Link href="/deployments">← All deployments</Link></p>
  </>;
}
