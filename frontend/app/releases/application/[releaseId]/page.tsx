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
  base_release: { version: string; status: string } | null;
  snapshot: { snapshot_no: string; status: string; content_hash: string } | null;
  coverage: Coverage | null;
};
type Evidence = {
  snapshot_no: string | null;
  artifacts: { id: string; component_code: string; component_version: string | null; filename: string; artifact_type: string; sha256: string; classification: string; distribution_level: string; ai_access_policy: string }[];
  executions: { item_no: string; title: string; execution_no: number; result: string; executed_at: string }[];
  other_snapshot_executions: number;
};
type Downstream = {
  deliveries: { id: string; package_no: string; revision: number; status: string; snapshot_no: string | null; recipient_code: string }[];
  distributions: { id: string; distribution_no: string; status: string; package_no: string; package_revision: number; recipient_code: string }[];
  authorizations: { id: string; authorization_no: string; status: string; snapshot_no: string | null; distribution_no: string | null; site_code: string; line_code: string; batch_limit: number | null }[];
  deployments: { id: string; deployment_no: string; status: string; authorization_no: string; expected_snapshot_no: string | null; actual_snapshot_no: string | null; actual_release_matches: boolean | null }[];
  changeovers: { id: string; changeover_no: string; status: string; deployment_no: string }[];
  batches: { id: string; batch_no: string; status: string; deployment_no: string; snapshot_no: string | null; release_matches: boolean }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const path = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}`;
  const [profile, evidence, downstream] = await Promise.all([apiGet<Profile>(path), apiGet<Evidence>(`${path}/evidence`), apiGet<Downstream>(`${path}/downstream`)]);
  if (!profile) return <section className="panel"><h1>Release unavailable</h1><p className="muted">The release was not found or the API could not be reached.</p><Link href="/releases/application">Back to releases →</Link></section>;
  const c = profile.coverage;
  return <>
    <div className="top"><div><div className="eyebrow">APPLICATION SOFTWARE RELEASE</div><h1>ASR {profile.version}</h1><p className="muted">{profile.customer?.name || 'No customer'} · {profile.project?.name || 'No project'} · {profile.software?.name || 'No software'}</p></div><span className={'status ' + (profile.status === 'READY' || profile.status === 'RELEASED' ? 'pass' : 'warning')}>{profile.status}</span></div>
    <div className="cards"><div className="card"><span className="muted">SNAPSHOT</span><div className="metric">{profile.snapshot?.snapshot_no || '—'}</div><small>{profile.snapshot?.status || 'No snapshot'}</small></div><div className="card"><span className="muted">CHANGE COVERAGE</span><div className="metric">{c ? `${c.change_coverage}%` : '—'}</div><small>{c ? `${c.change_points_covered} / ${c.change_points_total} change points` : 'No snapshot'}</small></div><div className="card"><span className="muted">ISSUE COVERAGE</span><div className="metric">{c ? `${c.issue_verification_coverage}%` : '—'}</div><small>{c ? `${c.issues_covered} / ${c.issues_total} issues` : 'No snapshot'}</small></div><div className="card"><span className="muted">DVP EXECUTION</span><div className="metric">{c ? `${c.dvp_execution_coverage}%` : '—'}</div><small>{c ? `${c.current_snapshot_executed} / ${c.required_dvp_total} on current snapshot` : 'No snapshot'}</small></div></div>
    <div className="grid2"><section className="panel"><h2>Release identity</h2><div className="kv"><span>Software</span><b>{profile.software ? `${profile.software.name} · ${profile.software.code}` : '—'}</b><span>Customer</span><b>{profile.customer ? <Link href={`/customers/${encodeURIComponent(profile.customer.code)}`}>{profile.customer.name}</Link> : '—'}</b><span>Project</span><b>{profile.project ? <Link href={`/projects/${profile.project.id}`}>{profile.project.name}</Link> : '—'}</b><span>Standard Base</span><b>{profile.base_release ? `SSR ${profile.base_release.version}` : '—'}</b><span>Content Hash</span><code style={{overflowWrap: 'anywhere'}}>{profile.snapshot?.content_hash || '—'}</code></div></section><section className="panel"><h2>Verification context</h2><p className="muted">{c ? (c.snapshot_match ? 'Current snapshot has execution records.' : 'No execution recorded on the current snapshot.') : 'No snapshot is available for verification coverage.'}</p><p>{profile.release_notes || 'No release notes recorded.'}</p>{profile.version === '2.3.4' && <Link href="/releases/demo">Open detailed demo workspace →</Link>}</section></div>
    {evidence ? <>
      <section className="panel tablewrap"><h2>Frozen artifact manifest · {evidence.snapshot_no || 'No snapshot'}</h2><table><thead><tr><th>Component</th><th>Filename</th><th>Type</th><th>SHA-256</th><th>Classification</th><th>Distribution</th><th>AI Policy</th></tr></thead><tbody>{evidence.artifacts.map(row => <tr key={row.id}><td>{row.component_code}{row.component_version ? ` · ${row.component_version}` : ''}</td><td><b>{row.filename}</b></td><td>{row.artifact_type}</td><td><code>{row.sha256.slice(0, 12)}…</code></td><td>{row.classification}</td><td>{row.distribution_level}</td><td>{row.ai_access_policy}</td></tr>)}</tbody></table>{evidence.artifacts.length === 0 && <p className="muted">No frozen artifacts recorded.</p>}</section>
      <section className="panel tablewrap"><h2>Latest DVP execution on current snapshot</h2><table><thead><tr><th>DVP</th><th>Test Item</th><th>Execution</th><th>Result</th><th>Executed</th></tr></thead><tbody>{evidence.executions.map(row => <tr key={row.item_no}><td><b>{row.item_no}</b></td><td>{row.title}</td><td>#{row.execution_no}</td><td><span className={'status ' + (row.result === 'PASS' ? 'pass' : 'warning')}>{row.result}</span></td><td>{row.executed_at.slice(0, 16).replace('T', ' ')}</td></tr>)}</tbody></table>{evidence.executions.length === 0 && <p className="muted">No DVP execution recorded on the current snapshot.</p>}{evidence.other_snapshot_executions > 0 && <p className="muted">{evidence.other_snapshot_executions} historical execution record(s) belong to other snapshots.</p>}</section>
    </> : <p className="datasource">Evidence API unavailable.</p>}
    {downstream ? <section className="panel tablewrap"><h2>Downstream lifecycle trace</h2><p className="muted">Records linked to this release. Actual software and batch matches are shown separately from planned links.</p>
      <table><thead><tr><th>Stage</th><th>Record</th><th>Parent / context</th><th>Snapshot / actual</th><th>Status</th></tr></thead><tbody>
        {downstream.deliveries.map(row => <tr key={row.id}><td>Delivery</td><td><Link href={`/distribution/deliveries/${encodeURIComponent(row.package_no)}/${row.revision}`}><b>{row.package_no} Rev{row.revision}</b></Link></td><td>{row.recipient_code}</td><td>{row.snapshot_no || '—'}</td><td>{row.status}</td></tr>)}
        {downstream.distributions.map(row => <tr key={row.id}><td>Distribution</td><td><Link href={`/distribution/distributions/${encodeURIComponent(row.distribution_no)}`}><b>{row.distribution_no}</b></Link></td><td>{row.package_no} Rev{row.package_revision} · {row.recipient_code}</td><td>—</td><td>{row.status}</td></tr>)}
        {downstream.authorizations.map(row => <tr key={row.id}><td>Authorization</td><td><Link href={`/distribution/authorizations/${encodeURIComponent(row.authorization_no)}`}><b>{row.authorization_no}</b></Link></td><td>{row.distribution_no || 'No distribution'} · {row.site_code}/{row.line_code}</td><td>{row.snapshot_no || '—'}</td><td>{row.status}</td></tr>)}
        {downstream.deployments.map(row => <tr key={row.id}><td>Deployment</td><td><Link href={`/deployments/${encodeURIComponent(row.deployment_no)}`}><b>{row.deployment_no}</b></Link></td><td>{row.authorization_no}</td><td>Expected {row.expected_snapshot_no || '—'} · Actual {row.actual_snapshot_no || 'pending'}{row.actual_release_matches === false ? ' (different release)' : ''}</td><td>{row.status}</td></tr>)}
        {downstream.changeovers.map(row => <tr key={row.id}><td>Changeover</td><td><b>{row.changeover_no}</b></td><td>{row.deployment_no}</td><td>—</td><td>{row.status}</td></tr>)}
        {downstream.batches.map(row => <tr key={row.id}><td>Batch</td><td><b>{row.batch_no}</b></td><td>{row.deployment_no}</td><td>{row.snapshot_no || '—'}{!row.release_matches ? ' (different release)' : ''}</td><td>{row.status}</td></tr>)}
      </tbody></table>{Object.values(downstream).every(rows => rows.length === 0) && <p className="muted">No downstream records linked to this release.</p>}</section> : <p className="datasource">Downstream trace API unavailable.</p>}
    <p className="datasource"><Link href="/releases/application">← All application releases</Link></p>
  </>;
}
