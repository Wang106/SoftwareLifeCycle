
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import { DeploymentProfile } from '../../../lib/production';

export const dynamic = 'force-dynamic';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = '/api/v1/deployments/' + encodeURIComponent(id);
  const deployment = await apiGet<DeploymentProfile>(path + '/profile');
  if (!deployment) return <section className="panel"><h1><Localized>{"Deployment unavailable"}</Localized></h1><p className="muted"><Localized>{"This deployment was not found or the API is unavailable. No substitute production data is shown."}</Localized></p><Link href="/deployments"><Localized>{"← All deployments"}</Localized></Link></section>;
  const provenance = deployment.provenance;
  const delivery = provenance.delivery;
  const historyQuery = new URLSearchParams({ deployment_id: deployment.id });

  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"DEPLOYMENT · "}</Localized><Localized>{deployment.deployment_no}</Localized></div><h1><Localized>{deployment.project?.name || 'Project'}</Localized><Localized>{" · "}</Localized><Localized>{deployment.site?.name || 'Site'}</Localized><Localized>{" / "}</Localized><Localized>{deployment.line?.name || 'Line'}</Localized></h1><p className="muted"><Localized>{"Production deployment trace for ASR "}</Localized><Localized>{deployment.expected.version || '—'}</Localized></p></div><span className={'status ' + (deployment.status === 'MATCH' ? 'pass' : 'warning')}><Localized>{deployment.status}</Localized></span></div>
    <p><Link href={`/commands?${new URLSearchParams({operation: "actual", target: deployment.deployment_no})}`}><Localized>{"Prepare actual-software request →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/commands?${new URLSearchParams({operation: "batch", target: deployment.deployment_no})}`}><Localized>{"Prepare Batch request →"}</Localized></Link></p>
    <p><Link href={`/commands?${new URLSearchParams({operation: 'changeover', target: deployment.deployment_no})}`}><Localized>{"Prepare changeover history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/production/changeovers?deployment_id=${deployment.id}`}><Localized>{"Review all recorded changeovers →"}</Localized></Link></p>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Authorization & actual"}</Localized></h2><div className="kv"><span><Localized>{"Authorization"}</Localized></span><b><Localized>{deployment.authorization?.authorization_no || '—'}</Localized></b><span><Localized>{"Production line UUID"}</Localized></span><b><Localized>{deployment.line?.id || 'Unavailable'}</Localized></b><span><Localized>{"Expected release UUID"}</Localized></span><b><Localized>{deployment.expected.release_id || 'Unavailable'}</Localized></b><span><Localized>{"Expected"}</Localized></span><b><Localized>{"ASR "}</Localized><Localized>{deployment.expected.version || '—'}</Localized><Localized>{" / "}</Localized><Localized>{deployment.expected.snapshot_no || '—'}</Localized></b><span><Localized>{"Actual"}</Localized></span><b><Localized>{deployment.actual ? `ASR ${deployment.actual.version} / ${deployment.actual.snapshot_no}` : 'Not reported'}</Localized></b><span><Localized>{"Stored status"}</Localized></span><b><Localized>{deployment.status}</Localized></b><span><Localized>{"Software observation"}</Localized></span><b><Localized>{deployment.software_observation}</Localized></b><span><Localized>{"Actual report version"}</Localized></span><b><Localized>{deployment.actual_version ?? "Unavailable — refresh before preparing a report"}</Localized></b></div></section>
      <section className="panel"><h2><Localized>{"Recorded history"}</Localized></h2><p className="muted"><Localized>{deployment.notice}</Localized></p>
        <p><Link href={`/production/changeovers?${historyQuery}`}><Localized>{deployment.history_counts.changeovers}</Localized><Localized>{" recorded changeovers →"}</Localized></Link></p>
        <p><Link href={`/production/batches?${historyQuery}`}><Localized>{deployment.history_counts.batches}</Localized><Localized>{" recorded batches →"}</Localized></Link></p>
        <p className="muted"><Localized>{"History opens in paginated catalogs scoped to this exact deployment. Counts are not production permissions or remaining authorization capacity."}</Localized></p>
      </section>
    </div>
    <section className="panel"><h2><Localized>{"End-to-end provenance"}</Localized></h2><Localized>{provenance ? <>
      <div className="kv"><span><Localized>{"Release decision history"}</Localized></span><b><Localized>{delivery ? <Link href={`/release-decisions?${new URLSearchParams({release_id: delivery.release_id, snapshot_id: delivery.snapshot_id})}`}><Localized>{"Review decisions for exact delivered release/snapshot →"}</Localized></Link> : 'Delivery unavailable — no decision scope inferred'}</Localized></b>
      <span><Localized>{"Delivery"}</Localized></span><b><Localized>{provenance.delivery ? `${provenance.delivery.package_no} Rev${provenance.delivery.revision} · ${provenance.delivery.status}` : 'No linked delivery'}</Localized></b>
      <span><Localized>{"Distribution"}</Localized></span><b><Localized>{provenance.distribution ? `${provenance.distribution.distribution_no} · ${provenance.distribution.status}` : 'No linked distribution'}</Localized></b>
      <span><Localized>{"Authorization"}</Localized></span><b><Localized>{provenance.authorization ? `${provenance.authorization.authorization_no} · ${provenance.authorization.status}` : 'No linked authorization'}</Localized></b>
      <span><Localized>{"Deployment"}</Localized></span><b><Localized>{deployment.deployment_no}</Localized><Localized>{" · "}</Localized><Localized>{deployment.status}</Localized></b>
      <span><Localized>{"Changeovers"}</Localized></span><b><Localized>{deployment.history_counts.changeovers}</Localized></b>
      <span><Localized>{"Batches"}</Localized></span><b><Localized>{deployment.history_counts.batches}</Localized></b></div>
    </> : <p className="muted"><Localized>{"Provenance API unavailable."}</Localized></p>}</Localized></section>
    <p className="datasource"><Link href="/deployments"><Localized>{"← All deployments"}</Localized></Link></p>
  </>;
}
