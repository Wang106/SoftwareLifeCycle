
import { Localized, LocalizedAttributes } from "../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Coverage = {
  change_points_total: number; change_points_covered: number; change_coverage: number;
  issues_total: number; issues_covered: number; issue_verification_coverage: number;
  required_dvp_total: number; current_snapshot_executed: number; dvp_execution_coverage: number;
  snapshot_match: boolean;
};
type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  base_release: { id: string; version: string; status: string } | null;
  snapshot: { snapshot_no: string; status: string; content_hash: string } | null;
  coverage: Coverage | null;
};
type Evidence = {
  snapshot_no: string | null;
  artifacts: { id: string; component_code: string; component_version: string | null; filename: string; artifact_type: string; sha256: string; classification: string; distribution_level: string; ai_access_policy: string }[];
  executions: { item_no: string; title: string; execution_no: number; result: string; executed_at: string }[];
  other_snapshot_executions: number;
};
type DownstreamSummary = {
  release_id: string;
  history_counts: { deliveries: number; distributions: number; authorizations: number; deployments: number; changeovers: number; batches: number };
  actual_release_observations: { same_release: number; different_release: number; not_reported: number };
  batch_release_observations: { same_release: number; different_release: number };
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const path = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}`;
  const [profile, evidence, summary] = await Promise.all([apiGet<Profile>(path), apiGet<Evidence>(`${path}/evidence`), apiGet<DownstreamSummary>(`${path}/downstream-summary`)]);
  if (!profile) return <section className="panel"><h1><Localized>{"Release unavailable"}</Localized></h1><p className="muted"><Localized>{"The release was not found or the API could not be reached."}</Localized></p><Link href="/releases/application"><Localized>{"Back to releases →"}</Localized></Link></section>;
  const c = profile.coverage;
  const downstream = summary?.release_id === profile.id ? summary : null;
  const productionScope = new URLSearchParams({authorization_release_id: profile.id});
  const history = downstream ? [
    {label: 'Delivery', count: downstream.history_counts.deliveries, href: `/distribution/deliveries?release_id=${profile.id}`},
    {label: 'Distribution', count: downstream.history_counts.distributions, href: `/distribution/distributions?release_id=${profile.id}`},
    {label: 'Authorization', count: downstream.history_counts.authorizations, href: `/distribution/authorizations?release_id=${profile.id}`},
    {label: 'Deployment', count: downstream.history_counts.deployments, href: `/deployments?${productionScope}`},
    {label: 'Changeover', count: downstream.history_counts.changeovers, href: `/production/changeovers?${productionScope}`},
    {label: 'Batch', count: downstream.history_counts.batches, href: `/production/batches?${productionScope}`},
  ] : [];
  return <>
    <p><Link href={`/commands?${new URLSearchParams({operation: "snapshot", target: profile.id})}`}><Localized>{"Prepare Snapshot request →"}</Localized></Link></p>
    <p><Link href={`/approvals?release_id=${profile.id}`}><Localized>{"Approval history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/release-decisions?release_id=${profile.id}`}><Localized>{"Release decision history →"}</Localized></Link></p>
    <p><Link href={`/deployments?${productionScope}`}><Localized>{"Deployment history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/production/batches?${productionScope}`}><Localized>{"Batch history →"}</Localized></Link></p>
    <p><Link href={`/distribution/deliveries?release_id=${profile.id}`}><Localized>{"Delivery history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/distribution/distributions?release_id=${profile.id}`}><Localized>{"Distribution history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/distribution/authorizations?release_id=${profile.id}`}><Localized>{"Production authorizations →"}</Localized></Link></p>
    <p><Link href={`/resources?entity_type=RELEASE&entity_id=${profile.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{"APPLICATION SOFTWARE RELEASE"}</Localized></div><h1><Localized>{"ASR "}</Localized><Localized>{profile.version}</Localized></h1><p className="muted"><Localized>{profile.customer?.name || 'No customer'}</Localized><Localized>{" · "}</Localized><Localized>{profile.project?.name || 'No project'}</Localized><Localized>{" · "}</Localized><Localized>{profile.software?.name || 'No software'}</Localized></p></div><span className={'status ' + (profile.status === 'READY' || profile.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{profile.status}</Localized></span></div>
    <div className="cards"><div className="card"><span className="muted"><Localized>{"SNAPSHOT"}</Localized></span><div className="metric"><Localized>{profile.snapshot?.snapshot_no || '—'}</Localized></div><small><Localized>{profile.snapshot?.status || 'No snapshot'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"CHANGE COVERAGE"}</Localized></span><div className="metric"><Localized>{c ? `${c.change_coverage}%` : '—'}</Localized></div><small><Localized>{c ? `${c.change_points_covered} / ${c.change_points_total} change points` : 'No snapshot'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"ISSUE COVERAGE"}</Localized></span><div className="metric"><Localized>{c ? `${c.issue_verification_coverage}%` : '—'}</Localized></div><small><Localized>{c ? `${c.issues_covered} / ${c.issues_total} issues` : 'No snapshot'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"DVP EXECUTION"}</Localized></span><div className="metric"><Localized>{c ? `${c.dvp_execution_coverage}%` : '—'}</Localized></div><small><Localized>{c ? `${c.current_snapshot_executed} / ${c.required_dvp_total} on current snapshot` : 'No snapshot'}</Localized></small></div></div>
    <div className="grid2"><section className="panel"><h2><Localized>{"Release identity"}</Localized></h2><div className="kv"><span><Localized>{"Software"}</Localized></span><b><Localized>{profile.software ? `${profile.software.name} · ${profile.software.code}` : '—'}</Localized></b><span><Localized>{"Customer"}</Localized></span><b><Localized>{profile.customer ? <Link href={`/customers/${encodeURIComponent(profile.customer.code)}`}><Localized>{profile.customer.name}</Localized></Link> : '—'}</Localized></b><span><Localized>{"Project"}</Localized></span><b><Localized>{profile.project ? <Link href={`/projects/${profile.project.id}`}><Localized>{profile.project.name}</Localized></Link> : '—'}</Localized></b><span><Localized>{"Standard Base"}</Localized></span><b><Localized>{profile.base_release ? <Link href={`/releases/standard/${encodeURIComponent(profile.base_release.id)}`}><Localized>{"SSR "}</Localized><Localized>{profile.base_release.version}</Localized></Link> : '—'}</Localized></b><span><Localized>{"Content Hash"}</Localized></span><code style={{overflowWrap: 'anywhere'}}>{profile.snapshot?.content_hash || '—'}</code></div><p><Link href={`/releases/application/${encodeURIComponent(profile.id)}/components`}><Localized>{"View component declarations →"}</Localized></Link></p><p><Link href={`/releases/application/${encodeURIComponent(profile.id)}/artifacts`}><Localized>{"View frozen artifact policy →"}</Localized></Link></p><p><Link href={`/releases/application/${encodeURIComponent(profile.id)}/passport`}><Localized>{"View software passport →"}</Localized></Link></p></section><section className="panel"><h2><Localized>{"Verification context"}</Localized></h2><p className="muted"><Localized>{c ? (c.snapshot_match ? 'Current snapshot has execution records.' : 'No execution recorded on the current snapshot.') : 'No snapshot is available for verification coverage.'}</Localized></p><p><Localized>{profile.release_notes || 'No release notes recorded.'}</Localized></p><Link href={`/releases/application/${encodeURIComponent(profile.id)}/readiness`}><Localized>{"View readiness gates →"}</Localized></Link></section></div>
    <p><Link href={`/releases/${encodeURIComponent(profile.id)}/snapshots`}><Localized>{"View snapshot history →"}</Localized></Link></p>
    <Localized>{evidence ? <>
      <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest · "}</Localized><Localized>{evidence.snapshot_no || 'No snapshot'}</Localized></h2><table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"Filename"}</Localized></th><th><Localized>{"Type"}</Localized></th><th><Localized>{"SHA-256"}</Localized></th><th><Localized>{"Classification"}</Localized></th><th><Localized>{"Distribution"}</Localized></th><th><Localized>{"AI Policy"}</Localized></th></tr></thead><tbody><Localized>{evidence.artifacts.map(row => <tr key={row.id}><td><Localized>{row.component_code}</Localized><Localized>{row.component_version ? ` · ${row.component_version}` : ''}</Localized></td><td><b><Localized>{row.filename}</Localized></b></td><td><Localized>{row.artifact_type}</Localized></td><td><code>{row.sha256.slice(0, 12)}…</code></td><td><Localized>{row.classification}</Localized></td><td><Localized>{row.distribution_level}</Localized></td><td><Localized>{row.ai_access_policy}</Localized></td></tr>)}</Localized></tbody></table><Localized>{evidence.artifacts.length === 0 && <p className="muted"><Localized>{"No frozen artifacts recorded."}</Localized></p>}</Localized></section>
      <section className="panel tablewrap"><h2><Localized>{"Latest DVP execution on current snapshot"}</Localized></h2><table><thead><tr><th><Localized>{"DVP"}</Localized></th><th><Localized>{"Test Item"}</Localized></th><th><Localized>{"Execution"}</Localized></th><th><Localized>{"Result"}</Localized></th><th><Localized>{"Executed"}</Localized></th></tr></thead><tbody><Localized>{evidence.executions.map(row => <tr key={row.item_no}><td><b><Localized>{row.item_no}</Localized></b></td><td><Localized>{row.title}</Localized></td><td><Localized>{"#"}</Localized><Localized>{row.execution_no}</Localized></td><td><span className={'status ' + (row.result === 'PASS' ? 'pass' : 'warning')}><Localized>{row.result}</Localized></span></td><td><Localized>{row.executed_at.slice(0, 16).replace('T', ' ')}</Localized></td></tr>)}</Localized></tbody></table><Localized>{evidence.executions.length === 0 && <p className="muted"><Localized>{"No DVP execution recorded on the current snapshot."}</Localized></p>}</Localized><Localized>{evidence.other_snapshot_executions > 0 && <p className="muted"><Localized>{evidence.other_snapshot_executions}</Localized><Localized>{" historical execution record(s) belong to other snapshots."}</Localized></p>}</Localized></section>
    </> : <p className="datasource"><Localized>{"Evidence API unavailable."}</Localized></p>}</Localized>
    <Localized>{downstream ? <section className="panel tablewrap"><h2><Localized>{"Downstream lifecycle trace"}</Localized></h2>
      <p className="muted"><Localized>{"Full counts include all statuses. Production history follows this release's authorizations, including inconsistent actual software and batch records."}</Localized></p>
      <table><thead><tr><th><Localized>{"Stage"}</Localized></th><th><Localized>{"Recorded count"}</Localized></th><th><Localized>{"History"}</Localized></th></tr></thead><tbody>
        <Localized>{history.map(row => <tr key={row.label}><td><Localized>{row.label}</Localized></td><td><Localized>{row.count}</Localized></td><td><Link href={row.href}><Localized>{"Browse scoped history →"}</Localized></Link></td></tr>)}</Localized>
      </tbody></table>
      <h3><Localized>{"Actual release observations"}</Localized></h3>
      <p><Localized>{"Same release: "}</Localized><Localized>{downstream.actual_release_observations.same_release}</Localized><Localized>{" · Different release: "}</Localized><Localized>{downstream.actual_release_observations.different_release}</Localized><Localized>{" · No actual release reported: "}</Localized><Localized>{downstream.actual_release_observations.not_reported}</Localized></p>
      <h3><Localized>{"Batch release observations"}</Localized></h3>
      <p><Localized>{"Same release: "}</Localized><Localized>{downstream.batch_release_observations.same_release}</Localized><Localized>{" · Different release: "}</Localized><Localized>{downstream.batch_release_observations.different_release}</Localized></p>
      <p className="muted"><Localized>{"These compare release UUIDs only. They do not establish snapshot matches, physical flashing, approval or permission. Counts are read observations, not a consistent write receipt or reserved capacity."}</Localized></p>
      <Localized>{Object.values(downstream.history_counts).every(count => count === 0) && <p className="muted"><Localized>{"No downstream records linked to this release."}</Localized></p>}</Localized>
    </section> : <p className="datasource"><Localized>{"Downstream summary unavailable. Counts are unknown; no unbounded fallback is used."}</Localized></p>}</Localized>
    <p className="datasource"><Link href="/releases/application"><Localized>{"← All application releases"}</Localized></Link></p>
  </>;
}
